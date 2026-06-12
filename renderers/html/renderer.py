"""
HTML Renderer — renders slides from design tokens + SlideSpec.

- render_slide: returns a *pure* <section class="slide ..."> (no embedded <style>)
- render_deck: assembles full HTML document.
  - standalone=True (default): single-file self-contained (embeds slidecraft.css + slider.js)
  - standalone=False: external CSS/JS via <link>/<script src> using css_path / js_path (smaller HTML)
  - template support via templates/default.html (or custom template_path)
"""
import yaml
import os
import re
from pathlib import Path
from typing import Optional


# ─── Token Loading ──────────────────────────────────────────────────────

def load_tokens(theme_path: str) -> dict:
    """Load a design token YAML file and return as dict."""
    with open(theme_path) as f:
        return yaml.safe_load(f)


def tokens_to_css(tokens: dict) -> str:
    """Convert design tokens to CSS custom properties on :root."""
    c = tokens.get("colors", {})
    t = tokens.get("typography", {})
    s = tokens.get("spacing", {})
    r = tokens.get("radii", {})

    lines = [":root {"]

    # Colors
    lines.append(f"  --bg: {c.get('bg', '#FFFFFF')};")
    lines.append(f"  --surface: {c.get('surface', '#FFFFFF')};")
    lines.append(f"  --text-p: {c.get('text', {}).get('p', '#000000')};")
    lines.append(f"  --text-s: {c.get('text', {}).get('s', '#666666')};")
    lines.append(f"  --accent: {c.get('accent', '#004A99')};")
    if c.get("accent2"):
        lines.append(f"  --accent2: {c.get('accent2')};")
    lines.append(f"  --border: {c.get('border', '#E0E0E0')};")

    # Typography
    f = t.get("family", {})
    lines.append(f"  --font-sans: {f.get('web', 'system-ui, sans-serif')};")

    for level in ["h1", "h2", "h3", "body", "caption"]:
        lv = t.get(level, {})
        px = lv.get("px", 16)
        lh = lv.get("lh", 1.4)
        ls = lv.get("ls", 0)
        lines.append(f"  --fs-{level}: {px}px;")
        lines.append(f"  --lh-{level}: {lh};")
        lines.append(f"  --ls-{level}: {ls}em;")

    # Spacing
    for size in ["xs", "sm", "md", "lg", "xl"]:
        px = s.get(size, {}).get("px", 16)
        lines.append(f"  --space-{size}: {px}px;")

    # Radii
    lines.append(f"  --radius-card: {r.get('card', 6)}px;")
    lines.append(f"  --radius-btn: {r.get('button', 4)}px;")

    # Shadows
    sh = tokens.get("shadows", {}).get("card", {})
    if sh:
        lines.append(
            f"  --shadow-card: {sh.get('x', 0)}px {sh.get('y', 2)}px "
            f"{sh.get('blur', 8)}px {sh.get('spread', 0)}px {sh.get('color', '#00000015')};"
        )

    lines.append("}")
    return "\n".join(lines)


# ─── HTML Components ────────────────────────────────────────────────────

# ─── Static CSS (externalized) ─────────────────────────────────────────

_SLIDECRAFT_CSS_PATH = Path(__file__).parent / "slidecraft.css"
_SLIDER_JS_PATH = Path(__file__).parent / "slider.js"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _get_slidecraft_css() -> str:
    """Return the contents of slidecraft.css (static rules for slides, layouts, nav)."""
    if _SLIDECRAFT_CSS_PATH.exists():
        return _SLIDECRAFT_CSS_PATH.read_text(encoding="utf-8")
    return "/* slidecraft.css not found — falling back to minimal */ section.slide{width:1280px;height:720px;}"


def _inline_slider() -> str:
    """Read slider.js and return inline <script> tag (for --standalone)."""
    if _SLIDER_JS_PATH.exists():
        js = _SLIDER_JS_PATH.read_text(encoding="utf-8")
        return f"<script>\n{js}\n</script>"
    return ""


def _load_template(template_path: Optional[str] = None) -> str:
    """Load a template file from templates/ dir (name or full path).
    Supports custom templates for different fonts/analytics etc.
    """
    if template_path:
        p = Path(template_path)
        if not p.is_absolute():
            cand = _TEMPLATES_DIR / p.name
            if cand.exists():
                p = cand
        if p.exists():
            return p.read_text(encoding="utf-8")
    # default
    p = _TEMPLATES_DIR / "default.html"
    if p.exists():
        return p.read_text(encoding="utf-8")
    # ultimate fallback (legacy placeholders for safety)
    return """<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#1a1a1a;color:#fff}}</style>
{css_block}
</head><body><div class="deck">{deck_content}</div>{js_block}</body></html>"""


def _img_tag(path: str, css_class: str = "slide-bg") -> str:
    """Generate an <img> tag."""
    # Try relative path from HTML file location
    html_dir = os.getcwd()  # fallback
    try:
        html_dir = os.path.dirname(os.path.abspath(__file__))
    except:
        pass
    
    # Use the path as-is — works for both file:// and http://
    return f'<img class="{css_class}" src="{path}" alt="Slide background" onerror="this.style.display=\'none\'">'


# ─── Layout Renderers ───────────────────────────────────────────────────

def _render_cover(content: dict) -> str:
    title = content.get("title", "")
    subtitle = content.get("subtitle", "")
    parts = ['<div class="slide-content">']
    step = 0
    if title:
        step += 1
        parts.append(f'<h1 class="step-item" data-step="{step}">{_esc(title)}</h1>')
    if subtitle:
        step += 1
        parts.append(f'<div class="subtitle step-item" data-step="{step}">{_esc(subtitle)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _render_card_list(content: dict) -> str:
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    # Split bullets into ~3 columns
    n = max(1, len(bullets) // 3 + (1 if len(bullets) % 3 else 0))
    cols = [bullets[i:i+n] for i in range(0, len(bullets), n)]
    while len(cols) < 3:
        cols.append([])

    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="card-grid">')
    step = 0
    for i, col in enumerate(cols):
        step += 1
        parts.append(f'<div class="card step-item" data-step="{step}"><ul>')
        for item in col:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul></div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_image_text(content: dict, visual_path: Optional[str] = None) -> str:
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    parts = []
    if visual_path:
        parts.append(f'<div class="image-side">{_img_tag(visual_path, "slide-bg")}</div>')
    else:
        parts.append('<div class="image-side" style="background:var(--accent);opacity:0.1"></div>')
    parts.append('<div class="text-side">')
    parts.append(f'<h2>{_esc(title)}</h2>')
    if content.get("subtitle"):
        parts.append(f'<div class="subtitle">{_esc(content["subtitle"])}</div>')
    if bullets:
        parts.append('<ul class="body-text">')
        step = 0
        for b in bullets:
            step += 1
            parts.append(f'<li class="step-item" data-step="{step}">{_esc(b)}</li>')
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


def _render_grid(content: dict) -> str:
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    cols = content.get("columns", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="grid-box">')
    # Use columns if provided, otherwise split bullets into 4 boxes
    items = cols if cols else [{"heading": f"Item {i+1}", "items": [b]} for i, b in enumerate(bullets[:4])]
    step = 0
    for item in items:
        step += 1
        parts.append(f'<div class="card step-item" data-step="{step}">')
        parts.append(f'<h3>{_esc(item.get("heading", ""))}</h3>')
        for sub in item.get("items", []):
            parts.append(f'<p class="body-text">{_esc(sub)}</p>')
        parts.append("</div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_transition(content: dict) -> str:
    title = content.get("title", "")
    subtitle = content.get("subtitle", "")
    parts = ['<div class="slide-content">']
    parts.append(f'<h1>{_esc(title)}</h1>')
    if subtitle:
        parts.append(f'<p class="subtitle">{_esc(subtitle)}</p>')
    parts.append("</div>")
    return "".join(parts)


def _render_content(content: dict) -> str:
    title = content.get("title", "")
    bullets = content.get("bullets", [])
    quote = content.get("quote")
    parts = ['<div class="slide-content">']
    parts.append(f'<div class="content-title"><h2>{_esc(title)}</h2></div>')
    parts.append('<div class="content-body">')
    step = 0
    if quote:
        qtext = quote.get("text", "")
        qsrc = quote.get("source", "")
        parts.append('<blockquote>')
        if qtext:
            step += 1
            parts.append(f'<p class="step-item" data-step="{step}">&quot;{_esc(qtext)}&quot;</p>')
        if qsrc:
            step += 1
            parts.append(f'<cite class="step-item" data-step="{step}">— {_esc(qsrc)}</cite>')
        parts.append('</blockquote>')
    if bullets:
        parts.append("<ul>")
        for b in bullets:
            step += 1
            parts.append(f'<li class="step-item" data-step="{step}">{_esc(b)}</li>')
        parts.append("</ul>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_two_column(content: dict) -> str:
    title = content.get("title", "")
    columns = content.get("columns", [])
    bullets = content.get("bullets", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="two-col-grid">')
    step = 0
    if columns:
        for col in columns:
            step += 1
            parts.append(f'<div class="col step-item" data-step="{step}"><h3>{_esc(col.get("heading", ""))}</h3><ul>')
            for item in col.get("items", []):
                parts.append(f"<li>{_esc(item)}</li>")
            parts.append("</ul></div>")
    else:
        mid = len(bullets) // 2
        step += 1
        parts.append(f'<div class="col step-item" data-step="{step}"><ul>')
        for b in bullets[:mid]:
            parts.append(f"<li>{_esc(b)}</li>")
        parts.append("</ul></div>")
        step += 1
        parts.append(f'<div class="col step-item" data-step="{step}"><ul>')
        for b in bullets[mid:]:
            parts.append(f"<li>{_esc(b)}</li>")
        parts.append("</ul></div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_stat_card(content: dict) -> str:
    title = content.get("title", "")
    stats = content.get("stats", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="stat-grid">')
    step = 0
    for stat in stats:
        step += 1
        parts.append(f'<div class="stat step-item" data-step="{step}"><div class="stat-value">{_esc(stat.get("value", ""))}</div>')
        parts.append(f'<div class="stat-label">{_esc(stat.get("label", ""))}</div></div>')
    parts.append("</div></div>")
    return "".join(parts)


def _render_timeline(content: dict) -> str:
    title = content.get("title", "")
    steps = content.get("steps", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="timeline">')
    step = 0
    for s in steps:
        step += 1
        num = s.get("number", 1)
        parts.append(f'<div class="step step-item" data-step="{step}"><div class="step-num">{num}</div><div class="step-text">')
        parts.append(f'<h3>{_esc(s.get("title", ""))}</h3>')
        parts.append(f'<p>{_esc(s.get("description", ""))}</p>')
        parts.append("</div></div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_comparison(content: dict) -> str:
    """Two-column comparison with highlight on preferred option."""
    title = content.get("title", "")
    columns = content.get("columns", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="two-col-grid" style="flex:1;gap:var(--space-lg)">')
    step = 0
    for i, col in enumerate(columns):
        step += 1
        is_winner = i == 0
        extra_style = 'border:2px solid var(--accent);' if is_winner else ''
        badge = '<div style="color:var(--accent);font-weight:700;font-size:var(--fs-caption);text-transform:uppercase;margin-bottom:var(--space-xs)">✓ Recommended</div>' if is_winner else ''
        parts.append(f'<div class="card step-item" data-step="{step}" style="{extra_style}">{badge}')
        parts.append(f'<h3>{_esc(col.get("heading", ""))}</h3><ul>')
        for item in col.get("items", []):
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul></div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_quote(content: dict) -> str:
    """Large centered quote with attribution."""
    quote = content.get("quote", {})
    title = content.get("title", "")
    parts = ['<div class="slide-content" style="justify-content:center;align-items:center;text-align:center">']
    if title:
        parts.append(f'<h2 style="margin-bottom:var(--space-lg)">{_esc(title)}</h2>')
    if quote:
        parts.append(f'<blockquote style="font-size:calc(var(--fs-h2) * 1.2);line-height:1.4;color:var(--text-p);font-weight:500;max-width:80%;margin:0 auto var(--space-lg)">')
        step = 0
        qtext = quote.get("text", "")
        qsrc = quote.get("source", "")
        if qtext:
            step += 1
            parts.append(f'<p class="step-item" data-step="{step}" style="position:relative">&#x201C;{_esc(qtext)}&#x201D;</p>')
        if qsrc:
            step += 1
            parts.append(f'<cite class="step-item" data-step="{step}" style="font-size:var(--fs-body);color:var(--text-s);font-style:normal;margin-top:var(--space-md);display:block">— {_esc(qsrc)}</cite>')
        parts.append('</blockquote>')
    parts.append("</div>")
    return "".join(parts)


def _render_team(content: dict) -> str:
    """Team member cards with photo placeholders."""
    title = content.get("title", "")
    columns = content.get("columns", [])
    members = content.get("bullets", [])
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="card-grid" style="flex:1">')
    items = columns if columns else [{"heading": f"Member {i+1}", "items": [m]} for i, m in enumerate(members[:6])]
    step = 0
    for item in items:
        step += 1
        name = item.get("heading", "")
        roles = item.get("items", [])
        # Avatar placeholder (initials)
        initials = "".join([w[0] for w in name.split()[:2]]) if name else "?"
        parts.append(f'<div class="card step-item" data-step="{step}" style="display:flex;flex-direction:column;align-items:center;text-align:center;padding:var(--space-lg)">')
        parts.append(f'<div style="width:64px;height:64px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;margin-bottom:var(--space-sm)">{_esc(initials)}</div>')
        parts.append(f'<h3 style="margin-bottom:4px">{_esc(name)}</h3>')
        for role in roles:
            parts.append(f'<p class="body-text" style="margin-bottom:2px">{_esc(role)}</p>')
        parts.append("</div>")
    parts.append("</div></div>")
    return "".join(parts)


def _render_process_flow(content: dict) -> str:
    """Horizontal process flow with connected steps."""
    title = content.get("title", "")
    steps = content.get("steps", [])
    cols = content.get("columns", [])
    items = cols if cols else [{"heading": s.get("title",""), "items": [s.get("description","")]} for s in steps]
    parts = ['<div class="slide-content">']
    parts.append(f'<h2>{_esc(title)}</h2>')
    parts.append('<div class="card-grid" style="flex:1;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));position:relative">')
    _step = 0
    for i, item in enumerate(items):
        _step += 1
        heading = item.get("heading", f"Step {i+1}")
        desc = item.get("items", [""])[0] if item.get("items") else ""
        parts.append(f'<div class="card step-item" data-step="{_step}" style="display:flex;flex-direction:column;align-items:center;text-align:center;padding:var(--space-lg);position:relative">')
        parts.append(f'<div style="width:48px;height:48px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;margin-bottom:var(--space-sm)">{i+1}</div>')
        parts.append(f'<h3 style="font-size:var(--fs-h3);margin-bottom:4px">{_esc(heading)}</h3>')
        parts.append(f'<p class="body-text">{_esc(desc)}</p>')
        parts.append('</div>')
        if i < len(items) - 1:
            parts.append(f'<div style="position:absolute;top:48px;left:calc({(i+1)*100//(len(items)+1)}% - 12px);width:calc({100//(len(items)+1)}%);height:2px;background:var(--accent);opacity:0.3;z-index:0"></div>')
    parts.append("</div></div>")
    return "".join(parts)


def _esc(text: str) -> str:
    """HTML-escape text content."""
    if not text:
        return ""
    return (str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


LAYOUT_RENDERERS = {
    "cover": _render_cover,
    "card-list": _render_card_list,
    "image-text": _render_image_text,
    "grid": _render_grid,
    "transition": _render_transition,
    "content": _render_content,
    "two-column": _render_two_column,
    "stat-card": _render_stat_card,
    "timeline": _render_timeline,
    "comparison": _render_comparison,
    "quote": _render_quote,
    "team": _render_team,
    "process-flow": _render_process_flow,
}


def render_slide(
    slide_spec: dict,
    tokens: dict,
    output_dir: Optional[str] = None,
    build_steps: Optional[bool] = None,
) -> str:
    """
    Render a single slide as a *pure* HTML <section> string (no embedded <style> or JS).

    The theme CSS vars and slidecraft rules live at document level (see render_deck).
    This keeps per-slide HTML small and avoids repeating hundreds of CSS rules.

    Args:
        slide_spec: SlideSpec dict (from DeckSpec JSON)
        tokens: Design token dict (still accepted for API compat / future per-slide needs)
        output_dir: If set, compute relative image paths here
        build_steps: Enable build step animations.
                     Falls back to slide_spec.build_steps, then deck default (True).
    """
    layout = slide_spec.get("layout", "content")
    content = slide_spec.get("content", {})
    visual = content.get("visual", {})
    notes = slide_spec.get("speaker_notes", "")

    # Background image (with relative path support)
    bg_parts = []
    img_src = None
    img_path = visual.get("generated_path") or slide_spec.get("background_image")

    if img_path:
        # Compute relative path for browser compatibility (even if file not present yet)
        if output_dir:
            try:
                rel = os.path.relpath(img_path, output_dir)
                img_src = rel
            except ValueError:
                img_src = img_path
        else:
            img_src = img_path
        bg_parts.append(_img_tag(img_src, "slide-bg"))
        # Add overlay for readability — dark enough for bright clinic photos.
        # Minimum floor of 0.55 ensures the bottom-right corner still provides
        # adequate contrast for text placed anywhere on the slide.
        # If the spec has background_override, use it as the overlay gradient
        # (lets the planner/LLM control overlay strength per photo).
        bg_override = slide_spec.get("background_override")
        if bg_override:
            overlay_bg = bg_override
        else:
            overlay_bg = "linear-gradient(135deg, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0.55) 100%)"
        bg_parts.append(f'<div class="slide-bg-overlay" style="background: {overlay_bg};"></div>')
    elif layout in ("cover", "transition") and "accent" in tokens.get("colors", {}):
        accent = tokens["colors"]["accent"]
        # Subtle gradient background using accent
        bg_parts.append(
            f'<div class="slide-bg-overlay" style="background: linear-gradient(135deg, {accent}15 0%, {accent}05 100%);"></div>'
        )

    # Render content based on layout
    renderer = LAYOUT_RENDERERS.get(layout, _render_content)
    if layout == "image-text":
        content_html = renderer(content, img_src)
    else:
        content_html = renderer(content)

    # Check build_steps: slide-level overrides deck default
    if build_steps is None:
        build_steps = slide_spec.get("build_steps", True)
    if not build_steps:
        content_html = content_html.replace('step-item', '')
        content_html = re.sub(r'\s*data-step="\d+"', '', content_html)

    # Append inline SVG from extra.inline_svg if present (self-contained visual per slide)
    inline_svg = None
    extra = content.get("extra", {}) if isinstance(content, dict) else {}
    if isinstance(extra, dict):
        inline_svg = extra.get("inline_svg")
    if inline_svg:
        content_html += f'<div class="inline-visual">{inline_svg}</div>'

    # Background override
    bg_style = ""
    bg_override = slide_spec.get("background_override")
    if bg_override:
        bg_style = f' style="background: {bg_override};"'

    # Auto-detect dark background (no bg image + dark background override).
    # When a slide has custom dark background_override but no photo, the
    # data-has-bg CSS rules won't fire — but dark bg + dark text is unreadable.
    # Heuristic: check if the override contains dark colors (hex or rgba).
    has_dark_bg = False
    if bg_override and not img_path:
        import re as _re
        has_dark_bg = False
        # Check hex colors
        hex_colors = _re.findall(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})', bg_override)
        for hc in hex_colors:
            if len(hc) == 3:
                hc = hc[0]*2 + hc[1]*2 + hc[2]*2
            try:
                r, g, b = int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16)
                avg = (r + g + b) / 3
                if avg < 85:  # darker than ~#555555
                    has_dark_bg = True
                    break
            except ValueError:
                pass
        # Also check rgba — dark with significant opacity = dark bg
        if not has_dark_bg:
            rgba_matches = _re.findall(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)', bg_override)
            for r, g, b, a in rgba_matches:
                r, g, b = int(r), int(g), int(b)
                alpha = float(a)
                if alpha >= 0.35 and (r + g + b) / 3 < 100:
                    has_dark_bg = True
                    break

    # Speaker notes
    notes_html = ""
    if notes:
        notes_html = f'<div class="notes" style="display:none">{_esc(notes)}</div>'

    return (
        f'<section class="slide layout-{layout}" '
        f'data-slide-id="{_esc(slide_spec.get("id", ""))}" '
        f'data-layout="{_esc(layout)}" '
        f'data-order="{slide_spec.get("order", 0)}"'
        f'{" data-has-bg" if img_path else ""}'
        f'{" data-has-dark-bg" if has_dark_bg else ""}{bg_style}>'
        f'{"".join(bg_parts)}'
        f'{content_html}'
        f'{notes_html}'
        f'</section>'
    )


def render_deck(
    slides: list[dict],
    tokens: dict,
    output_dir: str = None,
    build_steps: bool = True,
    standalone: bool = True,
    css_path: Optional[str] = None,
    js_path: Optional[str] = None,
    template_path: Optional[str] = None,
    title: str = "Presentation",
) -> str:
    """
    Render all slides as a complete HTML document.

    - standalone=True (default): self-contained single-file HTML.
      Embeds theme vars + full slidecraft.css + slider.js inline.
      Produces larger but portable .html (backward compatible).
    - standalone=False: external CSS/JS references (smaller HTML output).
      Uses <link> and <script src>. css_path/js_path control the URLs.
      Caller is responsible for making assets available (engine auto-copies
      when defaults used).

    Template:
      Uses templates/default.html (or custom via template_path).
      Custom templates can inject extra analytics, different font loading etc.

    Args:
        slides: List of SlideSpec dicts
        tokens: Design token dict
        output_dir: Output dir for relative image paths (passed to render_slide)
        build_steps: Enable build step animations (default True). Per-slide override wins.
        standalone: Embed CSS/JS (True) or link external (False)
        css_path: href value for <link> when standalone=False (default: "slidecraft.css")
        js_path: src value for <script> when standalone=False (default: "slider.js")
        template_path: Custom template file (full path or name in templates/)
        title: Document <title>
    """
    slide_htmls = []
    for spec in slides:
        slide_htmls.append(f'<div class="slide-wrapper">{render_slide(spec, tokens, output_dir, build_steps)}</div>')
    deck_content = "".join(slide_htmls)

    css_vars = tokens_to_css(tokens)

    if standalone:
        slidecraft_css = _get_slidecraft_css()
        css_block = f"""<style id="theme-vars">
{css_vars}
</style>
<style id="slidecraft">
{slidecraft_css}
</style>"""
        js_block = _inline_slider()
    else:
        c_href = css_path or "slidecraft.css"
        j_src = js_path or "slider.js"
        css_block = f"""<style id="theme-vars">
{css_vars}
</style>
<link rel="stylesheet" href="{c_href}">
"""
        js_block = f'<script src="{j_src}"></script>'

    tmpl = _load_template(template_path)

    # Prefer .format; fall back to replace for legacy/custom templates
    try:
        return tmpl.format(
            title=title,
            css_block=css_block,
            deck_content=deck_content,
            js_block=js_block,
        )
    except (KeyError, ValueError):
        # legacy fallback support {css_vars} etc + our new keys
        c_href = css_path or "slidecraft.css"
        j_src = js_path or "slider.js"
        html = tmpl.replace("{title}", title)
        html = html.replace("{css_block}", css_block)
        html = html.replace("{deck_content}", deck_content)
        html = html.replace("{js_block}", js_block)
        # legacy
        html = html.replace("{css_vars}", css_vars)
        html = html.replace("{css_href}", c_href if not standalone else "")
        html = html.replace("{js_src}", j_src if not standalone else "")
        return html
