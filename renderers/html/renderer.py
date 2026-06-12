"""
HTML Renderer — renders slides from design tokens + SlideSpec.
Produces self-contained HTML <section> elements with inline CSS.
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

def _style_block(css_vars: str, slide_w: int = 1280, slide_h: int = 720) -> str:
    """Full CSS for the slide element."""
    return f"""<style>
{css_vars}

section.slide {{
    position: relative;
    width: {slide_w}px;
    height: {slide_h}px;
    overflow: hidden;
    font-family: var(--font-sans);
    color: var(--text-p);
    background: var(--bg);
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
}}

section.slide .slide-bg {{
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    object-fit: cover;
    z-index: 0;
}}

section.slide .slide-bg-overlay {{
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 1;
}}

section.slide .slide-content {{
    position: relative;
    z-index: 2;
    padding: var(--space-xl);
    flex: 1;
    display: flex;
    flex-direction: column;
}}

.slide h1 {{
    font-size: var(--fs-h1);
    line-height: var(--lh-h1);
    letter-spacing: var(--ls-h1);
    margin: 0 0 var(--space-md) 0;
    font-weight: 700;
}}

.slide h2 {{
    font-size: var(--fs-h2);
    line-height: var(--lh-h2);
    letter-spacing: var(--ls-h2);
    margin: 0 0 var(--space-sm) 0;
    font-weight: 600;
}}

.slide h3 {{
    font-size: var(--fs-h3);
    line-height: var(--lh-h3);
    letter-spacing: var(--ls-h3);
    margin: 0 0 var(--space-xs) 0;
    font-weight: 500;
}}

.slide .body-text {{
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    letter-spacing: var(--ls-body);
    color: var(--text-s);
}}

.slide .subtitle {{
    font-size: var(--fs-h3);
    line-height: var(--lh-h3);
    color: var(--accent);
    margin-bottom: var(--space-lg);
}}

.slide .card {{
    background: var(--surface);
    border-radius: var(--radius-card);
    padding: var(--space-md);
    box-shadow: var(--shadow-card, none);
    border: 1px solid var(--border);
}}

/* ─── Layout: Cover ─── */
.layout-cover {{
    justify-content: center;
    align-items: center;
    text-align: center;
}}
.layout-cover h1 {{
    color: var(--text-p);
    max-width: 80%;
}}
.layout-cover .subtitle {{
    color: var(--text-s);
}}

/* ─── Layout: Card List ─── */
.layout-card-list .card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: var(--space-md);
    flex: 1;
}}
.layout-card-list .card-grid .card {{
    display: flex;
    flex-direction: column;
}}
.layout-card-list .card-grid .card ul {{
    margin: 0;
    padding-left: var(--space-md);
    flex: 1;
}}
.layout-card-list .card-grid .card li {{
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--text-s);
    margin-bottom: var(--space-xs);
}}

/* ─── Layout: Image + Text ─── */
.layout-image-text {{
    flex-direction: row !important;
}}
.layout-image-text .image-side {{
    flex: 0 0 50%;
    position: relative;
    overflow: hidden;
}}
.layout-image-text .image-side img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    position: absolute;
}}
.layout-image-text .text-side {{
    flex: 0 0 50%;
    padding: var(--space-xl);
    display: flex;
    flex-direction: column;
    justify-content: center;
}}

/* ─── Layout: Grid ─── */
.layout-grid .grid-box {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    grid-template-rows: none;
    gap: var(--space-md);
    flex: 1;
}}

/* ─── Layout: Transition ─── */
.layout-transition {{
    justify-content: center;
    align-items: center;
    text-align: center;
}}
.layout-transition h1 {{
    font-size: calc(var(--fs-h1) * 1.3);
}}

/* ─── Layout: Content ─── */
.layout-content .content-title {{
    padding-bottom: var(--space-sm);
    border-bottom: 2px solid var(--accent);
    margin-bottom: var(--space-lg);
}}
.layout-content .content-body {{
    flex: 1;
    font-size: var(--fs-body);
    line-height: var(--lh-body);
}}
.layout-content .content-body ul {{
    margin: 0;
    padding-left: var(--space-lg);
}}
.layout-content .content-body li {{
    margin-bottom: var(--space-sm);
}}

/* ─── Layout: Two Column ─── */
.layout-two-column .two-col-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: var(--space-lg);
    flex: 1;
}}
.layout-two-column .two-col-grid .col {{
    background: var(--surface);
    border-radius: var(--radius-card);
    padding: var(--space-md);
    border: 1px solid var(--border);
}}
.layout-two-column .two-col-grid .col ul {{
    margin: 0;
    padding-left: var(--space-md);
}}
.layout-two-column .two-col-grid .col li {{
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--text-s);
    margin-bottom: var(--space-xs);
}}

/* ─── Layout: Stat Card ─── */
.layout-stat-card .stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: var(--space-md);
    flex: 1;
    align-items: center;
}}
.layout-stat-card .stat-grid .stat {{
    text-align: center;
    padding: var(--space-lg);
}}
.layout-stat-card .stat-grid .stat .stat-value {{
    font-size: clamp(22px, 9cqi, 48px);
    font-weight: 700;
    color: var(--accent);
    line-height: 1.1;
}}
.layout-stat-card .stat-grid .stat .stat-label {{
    font-size: var(--fs-body);
    color: var(--text-s);
    margin-top: var(--space-xs);
}}

/* ─── Layout: Timeline ─── */
.layout-timeline .timeline {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-around;
    padding: 0 var(--space-lg);
}}
.layout-timeline .timeline .step {{
    display: flex;
    align-items: flex-start;
    gap: var(--space-md);
}}
.layout-timeline .timeline .step .step-num {{
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: var(--fs-h3);
}}
.layout-timeline .timeline .step .step-text {{
    flex: 1;
}}
.layout-timeline .timeline .step .step-text h3 {{
    margin-bottom: 4px;
}}
.layout-timeline .timeline .step .step-text p {{
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--text-s);
    margin: 0;
}}

/* ─── Responsive & Compact Mode ───
   .compact is applied by slider.js on small viewports.
   In compact mode the slide element gets a real narrow width so
   minmax grids + cqi units naturally adapt. These rules tighten
   spacing and force single-column stacks for complex layouts.
*/
.slide.compact .slide-content {{
    padding: var(--space-md);
}}
.slide.compact h1 {{
    font-size: clamp(26px, 7.5cqi, var(--fs-h1));
}}
.slide.compact h2 {{
    font-size: clamp(20px, 5.8cqi, var(--fs-h2));
}}
.slide.compact h3 {{
    font-size: clamp(16px, 4.5cqi, var(--fs-h3));
}}
.slide.compact .body-text,
.slide.compact .card li,
.slide.compact .two-col-grid li {{
    font-size: clamp(14px, 3.8cqi, var(--fs-body));
}}
.slide.compact .stat-value {{
    font-size: clamp(20px, 8cqi, 36px);
}}
.slide.compact .step-num {{
    width: 32px;
    height: 32px;
    font-size: 14px;
}}

/* Image+Text stacks vertically in compact */
.slide.compact .layout-image-text {{
    flex-direction: column !important;
}}
.slide.compact .layout-image-text .image-side {{
    flex: none !important;
    width: 100% !important;
    height: 220px !important;
    min-height: 160px;
}}
.slide.compact .layout-image-text .text-side {{
    flex: 1 !important;
    width: 100% !important;
    padding: var(--space-md) !important;
}}

/* Force single column stacks for grids that had 2-4 cols */
.slide.compact .layout-card-list .card-grid,
.slide.compact .layout-grid .grid-box {{
    grid-template-columns: 1fr !important;
}}
.slide.compact .layout-two-column .two-col-grid,
.slide.compact .layout-stat-card .stat-grid,
.slide.compact .two-col-grid {{
    grid-template-columns: 1fr !important;
    gap: var(--space-sm);
}}

/* Hide or neutralize absolute process-flow connectors on narrow reflow */
.slide.compact [style*="position:absolute"][style*="height:2px"] {{
    display: none !important;
}}
.slide.compact .layout-process-flow .card-grid {{
    position: static !important;
}}

/* Slightly tighter cards and lists */
.slide.compact .card {{
    padding: var(--space-sm);
}}
.slide.compact .slide-content ul,
.slide.compact .slide-content ol {{
    padding-left: var(--space-md);
}}

/* ─── Build Step Animations ─── */
.step-item {{
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.35s ease, transform 0.35s ease;
}}
.step-item.step-visible {{
  opacity: 1;
  transform: translateY(0);
}}
</style>"""


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


# ─── Slider Runtime (inlined for self-contained HTML) ───────────────

_SLIDER_JS_PATH = Path(__file__).parent / "slider.js"


def _inline_slider() -> str:
    """Read slider.js and return inline <script> tag."""
    if _SLIDER_JS_PATH.exists():
        return f"<script>\n{_SLIDER_JS_PATH.read_text()}\n</script>"
    return ""


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
    Render a single slide as an HTML <section> string.

    Args:
        slide_spec: SlideSpec dict (from DeckSpec JSON)
        tokens: Design token dict (from load_tokens)
        output_dir: If set, copy/process image assets here
        build_steps: Enable build step animations.
                     Falls back to slide_spec.build_steps, then deck default (True).
    """
    layout = slide_spec.get("layout", "content")
    content = slide_spec.get("content", {})
    visual = content.get("visual", {})
    notes = slide_spec.get("speaker_notes", "")

    # Build CSS
    css_vars = tokens_to_css(tokens)
    full_style = _style_block(css_vars)

    # Background image (with relative path support)
    bg_parts = []
    img_src = None
    img_path = visual.get("generated_path") or slide_spec.get("background_image")

    if img_path and os.path.exists(img_path):
        # Compute relative path for browser compatibility
        if output_dir:
            try:
                rel = os.path.relpath(img_path, output_dir)
                img_src = rel
            except ValueError:
                img_src = img_path
        else:
            img_src = img_path
        bg_parts.append(_img_tag(img_src, "slide-bg"))
        # Add overlay for readability on dark images
        bg_parts.append('<div class="slide-bg-overlay" style="background: linear-gradient(135deg, rgba(0,0,0,0.3) 0%, transparent 100%);"></div>')
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

    # Background override
    bg_style = ""
    bg_override = slide_spec.get("background_override")
    if bg_override:
        bg_style = f' style="background: {bg_override};"'

    # Speaker notes
    notes_html = ""
    if notes:
        notes_html = f'<div class="notes" style="display:none">{_esc(notes)}</div>'

    return (
        f'<section class="slide layout-{layout}" '
        f'data-slide-id="{_esc(slide_spec.get("id", ""))}" '
        f'data-layout="{_esc(layout)}" '
        f'data-order="{slide_spec.get("order", 0)}"{bg_style}>'
        f'{full_style}'
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
) -> str:
    """
    Render all slides as a complete HTML document.

    Args:
        slides: List of SlideSpec dicts
        tokens: Design token dict
        output_dir: Output directory for computing relative image paths
        build_steps: Enable build step animations (default True). Can be overridden per slide.
    """
    slide_htmls = []
    for spec in slides:
        slide_htmls.append(f'<div class="slide-wrapper">{render_slide(spec, tokens, output_dir, build_steps)}</div>')

    css_vars = tokens_to_css(tokens)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Presentation</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #1a1a1a;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    min-height: 100vh;
    padding: 20px;
}}
.deck {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    max-width: 100%;
    width: 100%;
}}
@media (max-width: 800px) {{
  body {{ padding: 0; }}
  .deck {{ gap: 0; }}
}}
{css_vars}
</style>
</head>
<body>
<div class="deck">
{"".join(slide_htmls)}
</div>
{_inline_slider()}
</body></html>"""
