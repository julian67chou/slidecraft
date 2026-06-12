"""
PPTX Renderer — renders slides from design tokens + SlideSpec.
Produces editable .pptx files with proper CJK support.
"""
import yaml
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


# ─── Helpers ────────────────────────────────────────────────────────────

def rgb(hexstr: str) -> RGBColor:
    h = hexstr.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load_tokens(theme_path: str) -> dict:
    with open(theme_path) as f:
        return yaml.safe_load(f)


def _font_name(tokens: dict) -> str:
    return tokens.get("typography", {}).get("family", {}).get("pptx", "Microsoft JhengHei")


def _pt(tokens: dict, level: str = "body") -> int:
    return tokens.get("typography", {}).get(level, {}).get("pt", 18)


def _color(tokens: dict, key: str, sub: str = None) -> str:
    c = tokens.get("colors", {})
    if sub:
        return c.get(key, {}).get(sub, "#333333")
    return c.get(key, "#333333")


def add_textbox(slide, left, top, width, height, text, size_pt=18,
                color="#333333", bold=False, align=PP_ALIGN.LEFT,
                font_name="Microsoft JhengHei"):
    """Add a textbox with a single paragraph."""
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
    run.font.name = font_name
    return txBox


def add_multiline_textbox(slide, left, top, width, height, lines,
                          size_pt=18, color="#333333", bold=False,
                          align=PP_ALIGN.LEFT, font_name="Microsoft JhengHei",
                          line_spacing: float = 1.3):
    """Add a textbox with multiple paragraphs (one per line)."""
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
        run.font.name = font_name
    return txBox


def add_rect(slide, left, top, width, height, fill_color=None):
    """Add a filled rectangle."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height))
    shape.line.fill.background()
    if fill_color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(fill_color)
    else:
        shape.fill.background()
    return shape


def add_rounded_rect(slide, left, top, width, height, fill_color="#FFFFFF"):
    """Add a rounded rectangle card."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height)
    )
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill_color)
    shape.adjustments[0] = 0.05
    return shape


def add_image(slide, image_path, left, top, width, height):
    """Add an image, handling URL-encoded paths."""
    # URL-decode if needed
    from urllib.parse import unquote
    decoded = unquote(image_path)
    actual_path = decoded if os.path.exists(decoded) else image_path
    if os.path.exists(actual_path):
        slide.shapes.add_picture(actual_path, Emu(left), Emu(top), Emu(width), Emu(height))
        return True
    return False


# ─── Layout Constants ───────────────────────────────────────────────────

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.5)
CONTENT_X = Inches(0.7)
CONTENT_W = Inches(11.933)


# ─── Layout Renderers ───────────────────────────────────────────────────

def _render_cover(slide, content: dict, tokens: dict):
    accent = _color(tokens, "accent")
    bg = _color(tokens, "bg")
    font = _font_name(tokens)
    h1_pt = _pt(tokens, "h1")
    h3_pt = _pt(tokens, "h3")

    # Left 40% accent panel
    panel_w = Inches(5.333)
    add_rect(slide, 0, 0, panel_w, SLIDE_H, accent)

    # Right 60% light area
    add_rect(slide, panel_w, 0, Inches(8.0), SLIDE_H, bg)

    # Title (centered in left panel)
    title = content.get("title", "")
    add_textbox(slide, Inches(0.5), Inches(2.2), Inches(4.33), Inches(1.5),
                title, h1_pt, "#FFFFFF", True, PP_ALIGN.LEFT, font)

    # Subtitle
    subtitle = content.get("subtitle", "")
    if subtitle:
        add_textbox(slide, Inches(0.5), Inches(3.8), Inches(4.33), Inches(0.8),
                    subtitle, h3_pt, "#FFFFFFBB", False, PP_ALIGN.LEFT, font)

    # Decorative line
    add_rect(slide, Inches(0.5), Inches(3.5), Inches(1.5), Inches(0.03), "#FFFFFF")


def _render_card_list(slide, content: dict, tokens: dict):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    text_s = _color(tokens, "text", "s")
    accent = _color(tokens, "accent")
    surface = _color(tokens, "surface")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.5), CONTENT_W, Inches(0.7),
                title, h2_pt, _color(tokens, "text", "p"), True, PP_ALIGN.LEFT, font)

    # 3 cards
    card_w = Inches(3.7)
    card_h = Inches(4.8)
    card_y = Inches(1.5)
    gap = Inches(0.33)

    n_cards = min(3, max(1, (len(bullets) + 2) // 3))
    cols = [bullets[i::n_cards] for i in range(n_cards)]

    for i in range(3):
        x = CONTENT_X + i * (card_w + gap)
        add_rounded_rect(slide, x, card_y, card_w, card_h, surface)

        col_bullets = cols[i] if i < len(cols) else []
        multi_lines = []
        for b in col_bullets:
            multi_lines.append(f"• {b}")
            multi_lines.append("")
        if multi_lines:
            add_multiline_textbox(slide, x + Inches(0.2), card_y + Inches(0.2),
                                  card_w - Inches(0.4), card_h - Inches(0.4),
                                  multi_lines, body_pt, text_s, False, PP_ALIGN.LEFT, font)


def _render_image_text(slide, content: dict, tokens: dict):
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

    # Left: image or placeholder
    img_w = Inches(6.5)
    img_path = visual.get("generated_path")
    placed = False
    if img_path:
        placed = add_image(slide, img_path, 0, 0, img_w, SLIDE_H)
    if not placed:
        add_rect(slide, 0, 0, img_w, SLIDE_H, accent + "20")

    # Right: text
    right_x = img_w + Inches(0.5)
    right_w = Inches(6.0)

    add_textbox(slide, right_x, Inches(1.5), right_w, Inches(1.0),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)

    if subtitle:
        add_textbox(slide, right_x, Inches(2.5), right_w, Inches(0.6),
                    subtitle, h3_pt, accent, False, PP_ALIGN.LEFT, font)

    if bullets:
        lines = [f"• {b}" for b in bullets]
        add_multiline_textbox(slide, right_x, Inches(3.3), right_w, Inches(3.5),
                              lines, body_pt, text_s, False, PP_ALIGN.LEFT, font)


def _render_content(slide, content: dict, tokens: dict):
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    quote = content.get("quote")
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")

    # Title with underline
    add_textbox(slide, CONTENT_X, Inches(0.4), CONTENT_W, Inches(0.7),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)
    add_rect(slide, CONTENT_X, Inches(1.15), Inches(2.0), Inches(0.03), accent)

    # Body
    if quote:
        add_textbox(slide, CONTENT_X, Inches(1.8), CONTENT_W, Inches(1.0),
                    f'"{quote.get("text", "")}"', body_pt + 2, accent, False, PP_ALIGN.LEFT, font)
        add_textbox(slide, CONTENT_X, Inches(2.7), CONTENT_W, Inches(0.5),
                    f'— {quote.get("source", "")}', body_pt, text_s, False, PP_ALIGN.LEFT, font)

    if bullets:
        lines = [f"• {b}" for b in bullets]
        y = Inches(3.5) if not quote else Inches(3.5)
        add_multiline_textbox(slide, CONTENT_X, y, CONTENT_W, Inches(3.0),
                              lines, body_pt, text_s, False, PP_ALIGN.LEFT, font)


def _render_two_column(slide, content: dict, tokens: dict):
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
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)

    # Two columns
    col_w = Inches(5.7)
    col_h = Inches(5.0)
    col_y = Inches(1.4)
    gap = Inches(0.5)

    if columns:
        for i, col in enumerate(columns):
            x = CONTENT_X + i * (col_w + gap)
            add_rounded_rect(slide, x, col_y, col_w, col_h, surface)
            # Heading
            add_textbox(slide, x + Inches(0.2), col_y + Inches(0.2),
                        col_w - Inches(0.4), Inches(0.5),
                        col.get("heading", ""), h3_pt, accent, True, PP_ALIGN.LEFT, font)
            # Items
            items = [f"• {item}" for item in col.get("items", [])]
            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.8),
                                  col_w - Inches(0.4), col_h - Inches(1.0),
                                  items, body_pt, text_s, False, PP_ALIGN.LEFT, font)
    else:
        mid = len(bullets) // 2
        left_items = [f"• {b}" for b in bullets[:mid]]
        right_items = [f"• {b}" for b in bullets[mid:]]

        for i, items in enumerate([left_items, right_items]):
            x = CONTENT_X + i * (col_w + gap)
            add_rounded_rect(slide, x, col_y, col_w, col_h, surface)
            add_multiline_textbox(slide, x + Inches(0.2), col_y + Inches(0.2),
                                  col_w - Inches(0.4), col_h - Inches(0.4),
                                  items, body_pt, text_s, False, PP_ALIGN.LEFT, font)


def _render_stat_card(slide, content: dict, tokens: dict):
    title = content.get("title", "")
    stats = content.get("stats", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.4), CONTENT_W, Inches(0.7),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)

    # Stats grid
    n = len(stats)
    if n == 0:
        return
    stat_w = CONTENT_W // n
    stat_y = Inches(2.0)

    for i, stat in enumerate(stats):
        x = CONTENT_X + i * stat_w
        # Big number
        add_textbox(slide, x, stat_y, stat_w, Inches(1.2),
                    stat.get("value", ""), 48, accent, True, PP_ALIGN.CENTER, font)
        # Label
        add_textbox(slide, x, stat_y + Inches(1.3), stat_w, Inches(0.6),
                    stat.get("label", ""), body_pt, text_s, False, PP_ALIGN.CENTER, font)


def _render_transition(slide, content: dict, tokens: dict):
    accent = _color(tokens, "accent")
    font = _font_name(tokens)
    h1_pt = _pt(tokens, "h1") + 8
    h3_pt = _pt(tokens, "h3")
    title = content.get("title", "")
    subtitle = content.get("subtitle", "")

    # Full-slide accent background
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, accent)

    # Centered title
    add_textbox(slide, Inches(1.0), Inches(2.5), Inches(11.333), Inches(2.0),
                title, h1_pt, "#FFFFFF", True, PP_ALIGN.CENTER, font)

    if subtitle:
        add_textbox(slide, Inches(2.0), Inches(4.5), Inches(9.333), Inches(0.8),
                    subtitle, h3_pt, "#FFFFFFBB", False, PP_ALIGN.CENTER, font)


def _render_grid(slide, content: dict, tokens: dict):
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
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)

    # 2x2 grid
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

        add_rounded_rect(slide, x, y, cell_w, cell_h, surface)
        add_textbox(slide, x + Inches(0.2), y + Inches(0.15),
                    cell_w - Inches(0.4), Inches(0.4),
                    heading, h3_pt, accent, True, PP_ALIGN.LEFT, font)
        cell_lines = []
        for item in sub_items:
            cell_lines.append(f"• {item}")
        if cell_lines:
            add_multiline_textbox(slide, x + Inches(0.2), y + Inches(0.6),
                                  cell_w - Inches(0.4), cell_h - Inches(0.8),
                                  cell_lines, body_pt, text_s, False, PP_ALIGN.LEFT, font)


def _render_timeline(slide, content: dict, tokens: dict):
    title = content.get("title", "")
    steps = content.get("steps", [])
    font = _font_name(tokens)
    h2_pt = _pt(tokens, "h2")
    h3_pt = _pt(tokens, "h3")
    body_pt = _pt(tokens, "body")
    accent = _color(tokens, "accent")
    text_p = _color(tokens, "text", "p")
    text_s = _color(tokens, "text", "s")

    # Title
    add_textbox(slide, CONTENT_X, Inches(0.3), CONTENT_W, Inches(0.6),
                title, h2_pt, text_p, True, PP_ALIGN.LEFT, font)

    # Timeline steps
    step_y_start = Inches(1.3)
    step_h = Inches(1.6)
    n = len(steps)
    total_h = n * step_h
    available_h = Inches(5.5)
    if total_h > available_h:
        step_h = available_h / max(n, 1)

    for i, step in enumerate(steps):
        y = step_y_start + i * step_h
        num = step.get("number", i + 1)
        step_title = step.get("title", "")
        desc = step.get("description", "")

        # Number circle
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
                    step_title, h3_pt, text_p, True, PP_ALIGN.LEFT, font)
        add_textbox(slide, CONTENT_X + Inches(0.9), y + Inches(0.4), Inches(10.5), Inches(0.8),
                    desc, body_pt, text_s, False, PP_ALIGN.LEFT, font)


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
    "comparison": _render_two_column,
    "quote": _render_content,
    "team": _render_card_list,
    "process-flow": _render_timeline,
}


# ─── Main API ───────────────────────────────────────────────────────────

def render_slide(prs: Presentation, slide_spec: dict, tokens: dict) -> None:
    """
    Add a single slide to an existing Presentation.

    Args:
        prs: python-pptx Presentation object
        slide_spec: SlideSpec dict (from DeckSpec JSON)
        tokens: Design token dict
    """
    layout = slide_spec.get("layout", "content")
    content = slide_spec.get("content", {})

    # Use blank layout
    blank_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(blank_layout)

    # Set background
    # Support solid hex colors. Gradient or complex overrides (e.g. "linear-gradient(...)")
    # are gracefully ignored for PPTX (python-pptx has limited gradient bg support).
    bg_override = slide_spec.get("background_override")
    bg_color = None
    if bg_override and isinstance(bg_override, str) and bg_override.strip().startswith("#"):
        candidate = bg_override.strip()
        if len(candidate) in (4, 7):  # #rgb or #rrggbb
            try:
                rgb(candidate)  # validate
                bg_color = candidate
            except Exception:
                bg_color = None
    if not bg_color:
        bg_color = _color(tokens, "bg")
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(bg_color)

    # Apply layout-specific renderer
    renderer = LAYOUT_RENDERERS.get(layout)
    if renderer:
        renderer(slide, content, tokens)


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

    for spec in slides:
        render_slide(prs, spec, tokens)

    prs.save(output_path)
    return os.path.abspath(output_path)
