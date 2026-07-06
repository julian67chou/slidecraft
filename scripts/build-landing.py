#!/usr/bin/env python3
"""Generate a landing page (index.html) listing all published decks."""
import json
from pathlib import Path


def generate(output_dir: str = "output"):
    out = Path(output_dir)
    decks = []
    for f in sorted(out.glob("*.spec.json")):
        name = f.stem.replace(".spec", "")
        try:
            spec = json.loads(f.read_text())
        except Exception:
            spec = {}
        decks.append({
            "name": name,
            "title": spec.get("title", name),
            "slides": spec.get("num_slides", len(spec.get("slides", []))),
            "theme": spec.get("global_design", {}).get("theme_id", "?"),
            "date": spec.get("generated_at", ""),
            "has_html": (out / f"{name}.html").exists(),
            "has_pptx": (out / f"{name}.pptx").exists(),
            "has_images": (out / f"{name}_images").exists(),
        })

    if not decks:
        print("No decks to index")
        return

    decks.sort(key=lambda d: d["name"], reverse=True)

    cards = []
    for d in decks:
        badges = []
        if d["has_html"]:
            badges.append('<span class="badge html">HTML</span>')
        if d["has_pptx"]:
            badges.append('<span class="badge pptx">PPTX</span>')
        if d["has_images"]:
            badges.append('<span class="badge img">🖼️</span>')
        date_str = (d["date"] or "")[:10]
        cards.append(f"""
    <a href="{d["name"]}.html" class="deck-card">
        <h2>{d["title"]}</h2>
        <div class="meta">
            <span>{d["slides"]} slides</span>
            <span>🎨 {d["theme"]}</span>
            {f'<span>📅 {date_str}</span>' if date_str else ''}
        </div>
        <div class="badges">{''.join(badges)}</div>
        <div class="footer">
            <span class="view-link">View →</span>
        </div>
    </a>""")

    index_html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideCraft</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Noto Sans TC', sans-serif;
    background: #f7f5f0;
    color: #222;
    padding: 40px 20px;
}}
h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
.subtitle {{ color: #666; margin-bottom: 32px; font-size: 14px; }}
.deck-grid {{ display: flex; flex-direction: column; gap: 12px; }}
.deck-card {{
    display: block;
    background: #fff; border-radius: 12px; padding: 20px;
    text-decoration: none; color: inherit;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    transition: box-shadow 0.2s, transform 0.2s;
}}
.deck-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.12); transform: translateY(-1px); }}
.deck-card h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 8px; }}
.deck-card .meta {{ display: flex; gap: 16px; font-size: 12px; color: #666; margin-bottom: 10px; }}
.deck-card .badges {{ display: flex; gap: 6px; margin-bottom: 8px; }}
.deck-card .badge {{ font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
.badge.html {{ background: #e8f5e9; color: #2e7d32; }}
.badge.pptx {{ background: #e3f2fd; color: #1565c0; }}
.badge.img {{ background: #f3e5f5; color: #7b1fa2; }}
.deck-card .footer {{ font-size: 12px; color: #6C5CE7; font-weight: 600; }}
.empty {{ text-align: center; padding: 60px 20px; color: #888; }}
</style>
</head>
<body>
<h1>SlideCraft</h1>
<p class="subtitle">{len(decks)} published decks</p>
<div class="deck-grid">
{''.join(cards) if cards else '<div class="empty"><p>No decks published yet</p></div>'}
</div>
</body>
</html>"""

    (out / "index.html").write_text(index_html)
    print(f"Generated index.html with {len(decks)} decks")


if __name__ == "__main__":
    import sys
    generate(sys.argv[1] if len(sys.argv) > 1 else "output")
