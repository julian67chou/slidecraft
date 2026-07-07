"""
PPTX Renderer v2 — enhanced with background images, gradients, shadows,
smart text scaling, CJK font detection, tables, and page numbers.

Renders slides from design tokens + SlideSpec into editable .pptx files.
"""
import yaml
import os
import re
import math
import platform
from pathlib import Path
from urllib.parse import unquote
from typing import Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree


# ─── Constants ───────────────────────────────────────────────────────────
EMU_PER_PT = 91440
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.5)
CONTENT_X = Inches(0.7)
CONTENT_W = Inches(11.933)
CHAR_W_FACTOR = 0.52  # rough EMU-per-pt-per-char for scaling estimation


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def rgb(hexstr: str) -> RGBColor:
    """Parse hex color string to RGBColor. Handles #rgb and #rrggbb."""
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load_tokens(theme_path: str) -> dict:
    with open(theme_path) as f:
        return yaml.safe_load(f)


def _font_name(tokens: dict) -> str:
    """Return configured PPTX font, with fallback to CJK-safe font."""
    configured = tokens.get("typography", {}).get("family", {}).get("pptx", None)
    if configured and configured != "Inter":
        # Use the theme's explicit PPTX font if set
        return configured
    return _detect_cjk_font()


def _detect_cjk_font() -> str:
    """Choose a CJK-friendly font based on platform."""
    system = platform.system()
    if system == "Windows":
        return "Microsoft JhengHei"
    elif system == "Darwin":
        return "PingFang TC"
    else:
        return "Noto Sans CJK TC"


def _pt(tokens: dict, level: str = "body") -> int:
    return tokens.get("typography", {}).get(level, {}).get("pt", 18)


def _color(tokens: dict, key: str, sub: str = None) -> str:
    c = tokens.get("colors", {})
    if sub:
        return c.get(key, {}).get(sub, "#333333")
    return c.get(key, "#333333")


def _alpha_hex(hex_color: str, alpha: float) -> str:
    """Apply alpha to a hex color. alpha 0.0-1.0. Produces #rrggbb (PPTX ignores alpha on fills)."""
    return hex_color  # PPTX doesn't use alpha in hex fills; use transparency instead


# ═══════════════════════════════════════════════════════════════════════════
# CSS Gradient Parser
# ═══════════════════════════════════════════════════════════════════════════

class GradientStop:
    __slots__ = ("pos", "color", "alpha")

    def __init__(self, pos: float, color: str, alpha: float = 1.0):
        self.pos = max(0.0, min(1.0, pos))
        self.color = color
        self.alpha = max(0.0, min(1.0, alpha))


def parse_css_gradient(grad_str: str) -> tuple[list[GradientStop], int]:
    """
    Parse a CSS linear-gradient string into GradientStops + angle (degrees).

    Supports:
      linear-gradient(angle, rgba(r,g,b,a) pos%, rgba(r,g,b,a) pos%)
      linear-gradient(to bottom, #hex pos%, #hex pos%)
      linear-gradient(#hex pos%, #hex pos%)
    Returns ([], 0) on failure.
    """
    if not grad_str or "linear-gradient" not in grad_str:
        return [], 0

    # Extract linear-gradient content with nested paren support
    # Find the position of 'linear-gradient(' and track paren depth
    lg_idx = grad_str.find("linear-gradient(")
    if lg_idx < 0:
        lg_idx = grad_str.find("linear-gradient (")
    if lg_idx < 0:
        return [], 0

    start = grad_str.index("(", lg_idx) + 1
    depth = 1
    end = start
    while end < len(grad_str) and depth > 0:
        if grad_str[end] == "(":
            depth += 1
        elif grad_str[end] == ")":
            depth -= 1
        end += 1
    inner = grad_str[start:end - 1]

    # Split intelligently: find commas NOT inside parentheses
    depth = 0
    parts = []
    current = []
    for ch in inner:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())

    if len(parts) < 2:
        return [], 0

    # Parse angle from first part
    angle = 0
    first = parts[0].strip()
    angle_m = re.match(r'([+-]?\d+)deg', first)
    if angle_m:
        angle = int(angle_m.group(1))
        parts = parts[1:]
    elif "to " in first:
        dir_map = {
            "bottom": 90, "right": 0, "left": 180, "top": 270,
            "bottom right": 45, "bottom left": 135,
            "top right": 315, "top left": 225,
        }
        for k, v in dir_map.items():
            if k in first:
                angle = v
                break
        parts = parts[1:]

    stops = []
    for part in parts:
        part = part.strip()

        # rgba(r,g,b,a) pos%
        rgba_m = re.match(
            r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)\s+([\d.]+)%',
            part,
        )
        if rgba_m:
            r, g, b, a, pos = rgba_m.groups()
            stops.append(GradientStop(
                pos=float(pos) / 100,
                color=f"#{int(r):02x}{int(g):02x}{int(b):02x}",
                alpha=float(a),
            ))
            continue

        # rgba without position (assume 0 or 100)
        rgba_np = re.match(
            r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)', part
        )
        if rgba_np:
            r, g, b, a = rgba_np.groups()
            pos = 0.0 if not stops else 1.0
            stops.append(GradientStop(pos, f"#{int(r):02x}{int(g):02x}{int(b):02x}", float(a)))
            continue

        # #rrggbb pos%
        hex_m = re.match(r'(#[0-9a-fA-F]{6})\s+([\d.]+)%', part)
        if hex_m:
            h, pos = hex_m.groups()
            stops.append(GradientStop(float(pos) / 100, h, 1.0))
            continue

        # #rgb pos%
        hex_s = re.match(r'(#[0-9a-fA-F]{3})\s+([\d.]+)%', part)
        if hex_s:
            h, pos = hex_s.groups()
            full = "#" + "".join(c * 2 for c in h.lstrip("#"))
            stops.append(GradientStop(float(pos) / 100, full, 1.0))
            continue

        # bare #hex (assign 0 or 100 position)
        bare = re.match(r'(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})', part)
        if bare:
            h = bare.group(1)
            if len(h) == 4:
                h = "#" + "".join(c * 2 for c in h.lstrip("#"))
            stops.append(GradientStop(0.0 if not stops else 1.0, h, 1.0))

    return stops, angle


# ═══════════════════════════════════════════════════════════════════════════
# Shape Fill Utilities
# ═══════════════════════════════════════════════════════════════════════════

def _apply_gradient_fill(shape, stops: list[GradientStop], angle: int = 0):
    """Apply a linear gradient to a shape's fill via XML."""
    if not stops:
        return

    spPr = shape._element.spPr

    # Create solidFill as fallback if gradient fails
    def _fallback_solid():
        for el in spPr.findall(qn("a:solidFill")):
            spPr.remove(el)
        for el in spPr.findall(qn("a:gradFill")):
            spPr.remove(el)
        sf = etree.SubElement(spPr, qn("a:solidFill"))
        sc = etree.SubElement(sf, qn("a:srgbClr"))
        sc.set("val", stops[0].color.lstrip("#"))

    # Remove existing fills
    for tag in ("a:solidFill", "a:gradFill", "a:blipFill", "a:noFill"):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)

    try:
        # Build gradient XML
        gradFill = etree.SubElement(spPr, qn("a:gradFill"))
        lin = etree.SubElement(gradFill, qn("a:lin"))
        # angle in 1/60000ths of a degree
        lin.set("ang", str((angle * 60000) % 21600000))
        lin.set("scaled", "0")

        gsLst = etree.SubElement(gradFill, qn("a:gsLst"))
        for s in stops:
            gs = etree.SubElement(gsLst, qn("a:gs"))
            gs.set("pos", str(int(s.pos * 100000)))
            sc = etree.SubElement(gs, qn("a:srgbClr"))
            sc.set("val", s.color.lstrip("#"))
    except Exception:
        _fallback_solid()


def _add_shadow(shape, blur_pt: int = 4, dist_pt: int = 2, opacity_1000: int = 20000):
    """
    Add outer shadow to a shape via XML manipulation.
    - opacity_1000: 0–100000 where 20000 ≈ 20%
    """
    spPr = shape._element.spPr
    for el in spPr.findall(qn("a:effectLst")):
        spPr.remove(el)

    effectLst = etree.SubElement(spPr, qn("a:effectLst"))
    outerShdw = etree.SubElement(effectLst, qn("a:outerShdw"))
    outerShdw.set("blurRad", str(blur_pt * EMU_PER_PT))
    outerShdw.set("dist", str(dist_pt * EMU_PER_PT))
    outerShdw.set("dir", "2700000")
    outerShdw.set("algn", "bl")
    outerShdw.set("rotWithShape", "0")
    srgbClr = etree.SubElement(outerShdw, qn("a:srgbClr"))
    srgbClr.set("val", "000000")
    alpha = etree.SubElement(srgbClr, qn("a:alpha"))
    alpha.set("val", str(opacity_1000))


# ═══════════════════════════════════════════════════════════════════════════
# Smart Text Scaling
# ═══════════════════════════════════════════════════════════════════════════

def _smart_pt(text: str, box_w: int, box_h: int, max_pt: int = 32,
              min_pt: int = 8) -> int:
    """
    Estimate the largest font pt that fits text into box_w × box_h (in EMU).
    Rough heuristic — multi-line, CJK-aware.
    """
    if not text:
        return max_pt

    # Count CJK vs ASCII characters
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f")
    ascii_ = len(text) - cjk
    est_w = cjk * 1.8 + ascii_ * 1.0

    if est_w == 0:
        return max_pt

    # How many chars at max_pt fit per line?
    char_w = max_pt * EMU_PER_PT * CHAR_W_FACTOR / 12
    if char_w <= 0:
        return max_pt
    chars_per_line = box_w / char_w
    if chars_per_line <= 0:
        return max_pt

    lines = math.ceil(est_w / chars_per_line)
    line_h = max_pt * EMU_PER_PT * 1.4  # rough line height
    needed_h = lines * line_h

    if needed_h <= box_h * 1.05:
        return max_pt

    scale = (box_h * 0.9) / needed_h
    result = int(max_pt * scale)
    return max(min_pt, result)


# ═══════════════════════════════════════════════════════════════════════════
# Shape Primitives
# ═══════════════════════════════════════════════════════════════════════════

def add_textbox(slide, left, top, width, height, text,
                size_pt=18, color="#333333", bold=False,
                align=PP_ALIGN.LEFT, font_name=None, smart_scale=False):
    """Add a single-paragraph textbox. If smart_scale=True, auto-shrink font."""
    if not text:
        return None

    font = font_name or _detect_cjk_font()

    if smart_scale:
        size_pt = _smart_pt(str(text), width, height, size_pt)

    txBox = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = str(text)
    run.font.size = Pt(size_pt)
    run.font.color.rgb = rgb(color)
    run.font.bold = bold
    run.font.name = font
    return txBox


def add_multiline_textbox(slide, left, top, width, height, lines,
                          size_pt=18, color="#333333", bold=False,
                          align=PP_ALIGN.LEFT, font_name=None,
                          line_spacing: float = 1.3, smart_scale=False):
    """Add a textbox with multiple paragraphs (one per line)."""
    if not lines:
        return None

    font = font_name or _detect_cjk_font()
    full_text = "\n".join(lines)

    if smart_scale:
        size_pt = _smart_pt(full_text, width, height, size_pt)

    txBox = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(4)
        run = p.add_run()
        run.text = str(line)
        run.font.size = Pt(size_pt)
        run.font.color.rgb = rgb(color)
        run.font.bold = bold
        run.font.name = font
    return txBox


def add_rect(slide, left, top, width, height, fill_color=None,
             gradient_stops: list = None, gradient_angle: int = 0,
             shadow=False):
    """Add a filled rectangle, optionally with gradient or shadow."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height)
    )
    shape.line.fill.background()

    if gradient_stops:
        _apply_gradient_fill(shape, gradient_stops, gradient_angle)
    elif fill_color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(fill_color)
    else:
        shape.fill.background()

    if shadow:
        _add_shadow(shape, blur_pt=4, dist_pt=2, opacity_1000=15000)

    return shape


def add_rounded_rect(slide, left, top, width, height,
                     fill_color="#FFFFFF", shadow=False):
    """Add a rounded rectangle card."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height)
    )
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill_color)
    try:
        shape.adjustments[0] = 0.04
    except Exception:
        pass

    if shadow:
        _add_shadow(shape, blur_pt=4, dist_pt=2, opacity_1000=12000)

    return shape


def add_image(slide, image_path, left, top, width, height, fit="cover"):
    """
    Add an image to the slide.
    fit="cover": image fills the box (may crop)
    fit="contain": image fits entirely within the box (may letterbox)
    """
    if not image_path or not os.path.exists(image_path):
        return False

    decoded = unquote(image_path)
    actual = decoded if os.path.exists(decoded) else image_path
    if not os.path.exists(actual):
        return False

    if fit == "cover":
        # Just add picture — it scales from top-left, so use shape clip
        # Simple approach: add picture at exact dimensions
        pic = slide.shapes.add_picture(actual, Emu(left), Emu(top), Emu(width), Emu(height))
        return True
    else:
        # contain: calculate aspect-ratio-preserving dimensions
        from PIL import Image
        with Image.open(actual) as img:
            orig_w, orig_h = img.size
        if orig_w == 0 or orig_h == 0:
            return False
        scale = min(width / orig_w, height / orig_h)
        final_w = int(orig_w * scale)
        final_h = int(orig_h * scale)
        offset_x = left + (width - final_w) // 2
        offset_y = top + (height - final_h) // 2
        pic = slide.shapes.add_picture(actual, Emu(offset_x), Emu(offset_y),
                                        Emu(final_w), Emu(final_h))
        return True


def add_slide_number(slide, num: int, total: int, color="#888888",
                     font_name=None):
    """Add a small page number in the bottom-right corner."""
    font = font_name or _detect_cjk_font()
    text = f"{num} / {total}"
    add_textbox(slide, SLIDE_W - Inches(1.2), SLIDE_H - Inches(0.45),
                Inches(1.0), Inches(0.35), text,
                size_pt=10, color=color, align=PP_ALIGN.RIGHT, font_name=font)


# ═══════════════════════════════════════════════════════════════════════════
# Layout Constants
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Layout Renderers
# ═══════════════════════════════════════════════════════════════════════════

def _render_cover(slide, content: dict, tokens: dict, slide_num: int, total: int):
    accent = _color(tokens, "accent")
    bg_grad = _color(tokens, "bg")
    font = _font_name(tokens)
    h1_pt = _pt(tokens, "h1")
    h3_pt = _pt(tokens, "h3")

    # Gradient accent panel (left 40%)
    panel_w = Inches(5.333)
    g_stops = [
        GradientStop(0.0, accent),
        GradientStop(0.6, _color(tokens, "accent2", "") or accent),
        GradientStop(1.0, accent),
    ]
    add_rect(slide, 0, 0, panel_w, SLIDE_H, gradient_stops=g_stops,
             gradient_angle=15)

    # Right 60% with subtle gradient
    bg2 = _color(tokens, "surface", "") or bg_grad
    r_stops = [
        GradientStop(0.0, bg_grad),
        GradientStop(1.0, bg2),
    ]
    add_rect(slide, panel_w, 0, Inches(8.0), SLIDE_H,
             gradient_stops=r_stops, gradient_angle=0)

    # Title
    title = content.get("title", "")
    add_textbox(slide, Inches(0.5), Inches(2.2), Inches(4.33), Inches(1.5),
                title, h1_pt, "#FFFFFF", True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    # Subtitle
    subtitle = content.get("subtitle", "")
    if subtitle:
        add_textbox(slide, Inches(0.5), Inches(3.8), Inches(4.33), Inches(1.0),
                    subtitle, h3_pt, "FFFFFFCC", False, PP_ALIGN.LEFT, font,
                    smart_scale=True)

    # Decorative line
    add_rect(slide, Inches(0.5), Inches(3.5), Inches(1.5), Inches(0.03), "#FFFFFF")


def _render_card_list(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    text_s = _color(tokens, "text", "s")
    accent = _color(tokens, "accent")
    surface = _color(tokens, "surface")
    bg = _color(tokens, "bg")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.5), CONTENT_W, Inches(0.7),
                title, h2_pt, _color(tokens, "text", "p"), True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    # Cards with shadows
    card_w = Inches(3.7)
    card_h = Inches(4.8)
    card_y = Inches(1.5)
    gap = Inches(0.33)

    n_cards = min(3, max(1, (len(bullets) + 2) // 3))
    cols = [bullets[i::n_cards] for i in range(n_cards)]

    for i in range(3):
        x = CONTENT_X + i * (card_w + gap)
        add_rounded_rect(slide, x, card_y, card_w, card_h, surface, shadow=True)

        col_bullets = cols[i] if i < len(cols) else []
        multi_lines = []
        for b in col_bullets:
            multi_lines.append(f"• {b}")
            multi_lines.append("")
        if multi_lines:
            add_multiline_textbox(slide, x + Inches(0.2), card_y + Inches(0.2),
                                  card_w - Inches(0.4), card_h - Inches(0.4),
                                  multi_lines, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                                  smart_scale=True)


def _render_image_text(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    subtitle = content.get("subtitle", "")
    visual = content.get("visual", {})
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    h3_pt = _pt(tokens, "h3")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    bg = _color(tokens, "bg")

    # Left: image or gradient placeholder
    img_w = Inches(6.5)
    img_path = visual.get("generated_path") or visual.get("path")
    placed = False
    if img_path:
        placed = add_image(slide, img_path, 0, 0, img_w, SLIDE_H)
    if not placed:
        g_stops = [
            GradientStop(0.0, accent),
            GradientStop(1.0, bg),
        ]
        add_rect(slide, 0, 0, img_w, SLIDE_H,
                 gradient_stops=g_stops, gradient_angle=45)

    # Right: text
    right_x = img_w + Inches(0.5)
    right_w = Inches(6.0)

    add_textbox(slide, right_x, Inches(1.5), right_w, Inches(1.0),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    if subtitle:
        add_textbox(slide, right_x, Inches(2.5), right_w, Inches(0.6),
                    subtitle, h3_pt, accent, False, PP_ALIGN.LEFT, font,
                    smart_scale=True)

    if bullets:
        lines = [f"• {b}" for b in bullets]
        add_multiline_textbox(slide, right_x, Inches(3.3), right_w, Inches(3.5),
                              lines, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                              smart_scale=True)


def _render_content(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    quote_block = content.get("quote")
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")

    # Title with gradient underline
    add_textbox(slide, CONTENT_X, Inches(0.4), CONTENT_W, Inches(0.7),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)
    g_stops = [
        GradientStop(0.0, accent),
        GradientStop(1.0, "#FFFFFF00" if False else accent),
    ]
    add_rect(slide, CONTENT_X, Inches(1.15), Inches(2.0), Inches(0.03),
             gradient_stops=g_stops, gradient_angle=45)

    y_start = Inches(1.8)

    if quote_block:
        quote_text = quote_block.get("text", "")
        quote_source = quote_block.get("source", "")
        add_textbox(slide, CONTENT_X, y_start, CONTENT_W, Inches(1.0),
                    f'"{quote_text}"', body_pt + 2, accent, False,
                    PP_ALIGN.LEFT, font, smart_scale=True)
        if quote_source:
            add_textbox(slide, CONTENT_X, y_start + Inches(0.9), CONTENT_W, Inches(0.5),
                        f"— {quote_source}", body_pt, text_s, False,
                        PP_ALIGN.LEFT, font)
        y_start = Inches(3.2)

    if bullets:
        lines = [f"• {b}" for b in bullets]
        add_multiline_textbox(slide, CONTENT_X, y_start, CONTENT_W, Inches(3.5),
                              lines, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                              smart_scale=True)


def _render_two_column(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    columns = content.get("columns", [])
    bullets = content.get("bullets", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    h3_pt = _pt(tokens, "h3")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    surface = _color(tokens, "surface")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.4), CONTENT_W, Inches(0.7),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    col_w = Inches(5.7)
    col_h = Inches(5.0)
    col_y = Inches(1.4)
    gap = Inches(0.5)

    if columns:
        for i, col in enumerate(columns):
            x = CONTENT_X + i * (col_w + gap)
            add_rounded_rect(slide, x, col_y, col_w, col_h, surface, shadow=True)

            heading = col.get("heading", "")
            add_textbox(slide, x + Inches(0.2), col_y + Inches(0.2),
                        col_w - Inches(0.4), Inches(0.5),
                        heading, h3_pt, accent, True, PP_ALIGN.LEFT, font,
                        smart_scale=True)

            items = [f"• {item}" for item in col.get("items", [])]
            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.8),
                                  col_w - Inches(0.4), col_h - Inches(1.0),
                                  items, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                                  smart_scale=True)
    else:
        mid = len(bullets) // 2
        col_pairs = [
            [f"• {b}" for b in bullets[:mid]],
            [f"• {b}" for b in bullets[mid:]],
        ]
        for i, items in enumerate(col_pairs):
            x = CONTENT_X + i * (col_w + gap)
            add_rounded_rect(slide, x, col_y, col_w, col_h, surface, shadow=True)
            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.2),
                                  col_w - Inches(0.4), col_h - Inches(0.4),
                                  items, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                                  smart_scale=True)


def _render_stat_card(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    stats = content.get("stats", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    bg = _color(tokens, "bg")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.4), CONTENT_W, Inches(0.7),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    n = len(stats)
    if n == 0:
        return
    stat_w = int(CONTENT_W // n)
    stat_y = Inches(2.0)

    for i, stat in enumerate(stats):
        x = CONTENT_X + i * stat_w

        # Stat card background (subtle gradient)
        card_w = stat_w - Inches(0.3)
        card_h = Inches(3.0)
        card_x = x + Inches(0.15)

        g_stops = [
            GradientStop(0.0, accent + "20" if accent.endswith(")") else _alpha_hex(accent, 0.0)),
            GradientStop(1.0, bg),
        ]
        # Actually just use surface
        add_rounded_rect(slide, card_x, stat_y, card_w, card_h,
                         _color(tokens, "surface", "") or bg, shadow=True)

        # Big number
        val = stat.get("value", "")
        val_pt = _smart_pt(val, card_w - Inches(0.4), Inches(1.2), max_pt=48)
        add_textbox(slide, card_x + Inches(0.2), stat_y + Inches(0.3),
                    card_w - Inches(0.4), Inches(1.2),
                    val, 48, accent, True, PP_ALIGN.CENTER, font,
                    smart_scale=True)

        # Label
        label = stat.get("label", "")
        add_textbox(slide, card_x + Inches(0.2), stat_y + Inches(1.6),
                    card_w - Inches(0.4), Inches(0.6),
                    label, body_pt, text_s, False, PP_ALIGN.CENTER, font,
                    smart_scale=True)


def _render_transition(slide, content: dict, tokens: dict, slide_num: int, total: int):
    accent = _color(tokens, "accent")
    accent2 = _color(tokens, "accent2", "") or accent
    font = _font_name(tokens)
    h1_pt = _pt(tokens, "h1") + 8
    h3_pt = _pt(tokens, "h3")
    title = content.get("title", "")
    subtitle = content.get("subtitle", "")

    # Full-slide gradient background
    g_stops = [
        GradientStop(0.0, accent),
        GradientStop(0.5, accent2),
        GradientStop(1.0, accent),
    ]
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, gradient_stops=g_stops,
             gradient_angle=45)

    # Decorative accent elements
    add_rect(slide, Inches(2.0), Inches(0.5), Inches(1.0), Inches(0.03),
             "#FFFFFF40")

    # Centered title
    add_textbox(slide, Inches(1.0), Inches(2.5), Inches(11.333), Inches(2.0),
                title, h1_pt, "#FFFFFF", True, PP_ALIGN.CENTER, font,
                smart_scale=True)

    if subtitle:
        add_textbox(slide, Inches(2.0), Inches(4.5), Inches(9.333), Inches(0.8),
                    subtitle, h3_pt, "FFFFFFBB", False, PP_ALIGN.CENTER, font,
                    smart_scale=True)


def _render_grid(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    columns_data = content.get("columns", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    h3_pt = _pt(tokens, "h3")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    surface = _color(tokens, "surface")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.3), CONTENT_W, Inches(0.6),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    # 2×2 grid
    cell_w = Inches(5.7)
    cell_h = Inches(2.7)
    gap_x = Inches(0.5)
    gap_y = Inches(0.3)
    grid_y = Inches(1.2)

    items = []
    if columns_data:
        for col in columns_data:
            items.append((col.get("heading", ""), col.get("items", [])))
    else:
        for i in range(min(4, len(bullets))):
            items.append((f"Item {i+1}", [bullets[i]]))

    for idx, (heading, sub_items) in enumerate(items):
        row = idx // 2
        col = idx % 2
        x = CONTENT_X + col * (cell_w + gap_x)
        y = grid_y + row * (cell_h + gap_y)

        add_rounded_rect(slide, x, y, cell_w, cell_h, surface, shadow=True)
        add_textbox(slide, x + Inches(0.2), y + Inches(0.15),
                    cell_w - Inches(0.4), Inches(0.4),
                    heading, h3_pt, accent, True, PP_ALIGN.LEFT, font,
                    smart_scale=True)
        cell_lines = [f"• {item}" for item in sub_items]
        if cell_lines:
            add_multiline_textbox(slide, x + Inches(0.2), y + Inches(0.6),
                                  cell_w - Inches(0.4), cell_h - Inches(0.8),
                                  cell_lines, body_pt, text_s, False,
                                  PP_ALIGN.LEFT, font, smart_scale=True)


def _render_timeline(slide, content: dict, tokens: dict, slide_num: int, total: int):
    title = content.get("title", "")
    steps = content.get("steps", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    h3_pt = _pt(tokens, "h3")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    bg = _color(tokens, "bg")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.3), CONTENT_W, Inches(0.6),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    # Timeline connector line
    line_x = CONTENT_X + Inches(0.35)
    add_rect(slide, line_x, Inches(1.1), Inches(0.03), Inches(5.5),
             accent + "40")

    step_y_start = Inches(1.3)
    step_h_val = Inches(1.5)
    n = len(steps)
    if n * step_h_val > Inches(5.5):
        step_h_val = int(Inches(5.5) // max(n, 1))

    for i, step in enumerate(steps):
        y = step_y_start + i * step_h_val
        num = step.get("number", i + 1)
        step_title = step.get("title", "")
        desc = step.get("description", "")

        # Number circle with gradient feel
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Emu(CONTENT_X), Emu(y), Emu(Inches(0.6)), Emu(Inches(0.6))
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = rgb(accent)
        circle.line.fill.background()
        tf = circle.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(num)
        run.font.size = Pt(18)
        run.font.color.rgb = rgb("#FFFFFF")
        run.font.bold = True
        run.font.name = font

        # Step text
        add_textbox(slide, CONTENT_X + Inches(0.9), y, Inches(10.5), Inches(0.4),
                    step_title, h3_pt, text_p, True, PP_ALIGN.LEFT, font,
                    smart_scale=True)

        if desc:
            add_textbox(slide, CONTENT_X + Inches(0.9), y + Inches(0.4),
                        Inches(10.5), Inches(0.7),
                        desc, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                        smart_scale=True)


def _render_table(slide, content: dict, tokens: dict, slide_num: int, total: int):
    """Render a table layout — uses bullets as rows, optional columns from extra."""
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    extra = content.get("extra", {})
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    surface = _color(tokens, "surface")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.3), CONTENT_W, Inches(0.6),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    # Table headers from extra.table_headers, or default to single column
    headers = extra.get("table_headers", ["項目"])
    n_cols = len(headers)
    n_rows = max(len(bullets), 1)

    # Add table
    table_w = CONTENT_W
    table_h = Inches(5.0)
    table_x = CONTENT_X
    table_y = Inches(1.2)
    row_h = int(table_h // (n_rows + 2))  # +1 for header row

    tbl_shape = slide.shapes.add_table(n_rows + 1, n_cols, Emu(table_x),
                                        Emu(table_y), Emu(table_w), Emu(table_h))
    table = tbl_shape.table

    # Header row
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for run in p.runs:
                run.font.size = Pt(body_pt)
                run.font.color.rgb = rgb("#FFFFFF")
                run.font.bold = True
                run.font.name = font
        # Header background
        tcPr = cell._tc.get_or_add_tcPr()
        solidFill = etree.SubElement(tcPr, qn("a:solidFill"))
        srgbClr = etree.SubElement(solidFill, qn("a:srgbClr"))
        srgbClr.set("val", accent.lstrip("#"))

    # Data rows
    for i, item in enumerate(bullets):
        row_idx = i + 1
        cell = table.cell(row_idx, 0)
        cell.text = item.lstrip("• ")
        for p in cell.text_frame.paragraphs:
            for run in p.runs:
                run.font.size = Pt(body_pt - 2)
                run.font.color.rgb = rgb(text_p)
                run.font.name = font
                run.font.bold = False
        # Alternating row colors
        if i % 2 == 1:
            tcPr = cell._tc.get_or_add_tcPr()
            solidFill = etree.SubElement(tcPr, qn("a:solidFill"))
            srgbClr = etree.SubElement(solidFill, qn("a:srgbClr"))
            srgbClr.set("val", surface.lstrip("#"))


def _render_comparison(slide, content: dict, tokens: dict, slide_num: int, total: int):
    """Comparison layout — two side-by-side columns with header row."""
    title = content.get("title", "")
    columns = content.get("columns", [])
    bullets = content.get("bullets", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    h3_pt = _pt(tokens, "h3")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    accent2 = _color(tokens, "accent2", "") or accent
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")
    bg = _color(tokens, "bg")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.3), CONTENT_W, Inches(0.6),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font,
                smart_scale=True)

    col_w = Inches(5.7)
    col_h = Inches(5.2)
    col_y = Inches(1.2)
    gap = Inches(0.5)

    # Two columns with colored headers
    colors = [accent, accent2]
    for i in range(2):
        x = CONTENT_X + i * (col_w + gap)

        # Top header bar (colored)
        add_rect(slide, x, col_y, col_w, Inches(0.5), colors[i])

        # Main area
        add_rounded_rect(slide, x, col_y + Inches(0.5), col_w, col_h - Inches(0.5),
                         bg, shadow=True)

        if i < len(columns):
            col = columns[i]
            heading = col.get("heading", "")
            items = [f"• {item}" for item in col.get("items", [])]

            add_textbox(slide, x + Inches(0.2), col_y + Inches(0.1),
                        col_w - Inches(0.4), Inches(0.4),
                        heading, h3_pt, "#FFFFFF", True, PP_ALIGN.LEFT, font,
                        smart_scale=True)

            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.7),
                                  col_w - Inches(0.4), col_h - Inches(1.0),
                                  items, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                                  smart_scale=True)
        else:
            # Split bullets
            half = len(bullets) // 2
            half_items = bullets[:half] if i == 0 else bullets[half:]
            lines = [f"• {b}" for b in half_items]
            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.7),
                                  col_w - Inches(0.4), col_h - Inches(1.0),
                                  lines, body_pt, text_s, False, PP_ALIGN.LEFT, font,
                                  smart_scale=True)


# ─── Layout Registry ────────────────────────────────────────────────────

LAYOUT_RENDERERS = {
    "cover": _render_cover,
    "card-list": _render_card_list,
    "image-text": _render_image_text,
    "content": _render_content,
    "two-column": _render_two_column,
    "stat-card": _render_stat_card,
    "transition": _render_transition,
    "grid": _render_grid,
    "timeline": _render_timeline,
    "table": _render_table,
    "comparison": _render_comparison,
    "quote": _render_content,
    "team": _render_card_list,
    "process-flow": _render_timeline,
}


# ═══════════════════════════════════════════════════════════════════════════
# Main API
# ═══════════════════════════════════════════════════════════════════════════

def render_slide(prs: Presentation, slide_spec: dict, tokens: dict,
                 slide_num: int = 1, total: int = 1) -> None:
    """
    Add a single slide to an existing Presentation.

    Args:
        prs: python-pptx Presentation object
        slide_spec: SlideSpec dict (from DeckSpec JSON)
        tokens: Design token dict
        slide_num: 1-based slide number (for page footer)
        total: total slide count
    """
    layout = slide_spec.get("layout", "content")
    content = slide_spec.get("content", {})

    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # ── Background: priority 1 = background_image, 2 = gradient parse, 3 = solid ──
    bg_img = slide_spec.get("background_image")
    bg_override = slide_spec.get("background_override")
    bg_color = _color(tokens, "bg")

    bg_applied = False

    # Try background image first
    if bg_img:
        img_path = unquote(bg_img)
        # Resolve relative paths
        abs_path = os.path.abspath(img_path)
        if os.path.exists(abs_path):
            try:
                # Full-slide image as first shape (z-order back)
                slide.shapes.add_picture(abs_path, Emu(0), Emu(0),
                                         Emu(SLIDE_W), Emu(SLIDE_H))
                bg_applied = True
            except Exception:
                pass

    # Try CSS gradient parsing for background
    if not bg_applied and bg_override:
        stops, angle = parse_css_gradient(bg_override)
        if stops:
            g_stops = [
                GradientStop(s.pos, s.color, s.alpha) for s in stops
            ]
            bg_shape = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), Emu(SLIDE_W), Emu(SLIDE_H)
            )
            bg_shape.line.fill.background()
            _apply_gradient_fill(bg_shape, g_stops, angle)
            bg_applied = True

    # Fallback: solid background
    if not bg_applied:
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = rgb(bg_color)

    # Apply layout-specific renderer
    renderer = LAYOUT_RENDERERS.get(layout)
    if renderer:
        renderer(slide, content, tokens, slide_num, total)

    # Page number footer (skip cover)
    if layout != "cover":
        font = _font_name(tokens)
        num_color = _color(tokens, "text", "s") + "60"
        add_slide_number(slide, slide_num, total, _color(tokens, "text", "s"), font)


def render_deck(slides: list[dict], tokens: dict, output_path: str) -> str:
    """
    Render all slides into a .pptx file.

    Args:
        slides: List of SlideSpec dicts
        tokens: Design token dict
        output_path: Path to save the .pptx file

    Returns:
        Absolute path to saved file
    """
    prs = Presentation()
    prs.slide_width = Inches(tokens.get("slide", {}).get("wIn", 13.333))
    prs.slide_height = Inches(tokens.get("slide", {}).get("hIn", 7.5))

    total = len(slides)
    for i, spec in enumerate(slides):
        render_slide(prs, spec, tokens, slide_num=i + 1, total=total)

    prs.save(output_path)
    return os.path.abspath(output_path)
