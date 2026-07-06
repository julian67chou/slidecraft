"""
Deploy — publish generated decks to GitHub Pages.

Usage:
    python -m orchestrator.deploy [deck_name1 deck_name2 ...]
    python -m orchestrator.deploy --all
    python -m orchestrator.deploy --latest
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
REPO = "julian67chou/slidecraft"


def get_decks() -> list[dict]:
    """List all generated decks from output/ spec files."""
    decks = []
    for f in sorted(OUTPUT_DIR.glob("*.spec.json")):
        try:
            spec = json.loads(f.read_text())
            name = f.stem.replace(".spec", "")
            html_path = OUTPUT_DIR / f"{name}.html"
            pptx_path = OUTPUT_DIR / f"{name}.pptx"
            images_dir = OUTPUT_DIR / f"{name}_images"
            decks.append({
                "name": name,
                "title": spec.get("title", name),
                "slides": spec.get("num_slides", len(spec.get("slides", []))),
                "theme": spec.get("global_design", {}).get("theme_id", "?"),
                "date": spec.get("generated_at", ""),
                "has_html": html_path.exists(),
                "has_pptx": pptx_path.exists(),
                "has_images": images_dir.exists(),
            })
        except Exception:
            pass
    return sorted(decks, key=lambda d: d["name"], reverse=True)


def build_index_page(decks: list[dict]) -> str:
    """Build an HTML index page listing all decks."""
    cards = []
    for d in decks:
        badges = []
        if d["has_html"]:
            badges.append('<span class="badge html">HTML</span>')
        if d["has_pptx"]:
            badges.append('<span class="badge pptx">PPTX</span>')
        if d["has_images"]:
            badges.append('<span class="badge img">🖼️</span>')
        
        date_str = d.get("date", "")[:10] if d.get("date") else ""
        
        cards.append(f"""
        <a href="{d['name']}.html" class="deck-card">
            <h2>{d['title']}</h2>
            <div class="meta">
                <span>{d['slides']} slides</span>
                <span>🎨 {d['theme']}</span>
                {f'<span>📅 {date_str}</span>' if date_str else ''}
            </div>
            <div class="badges">{''.join(badges)}</div>
            <div class="footer">
                <span class="view-link">View →</span>
                {f'<span class="dl-link">📊 {d["name"]}.pptx</span>' if d['has_pptx'] else ''}
            </div>
        </a>""")
    
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideCraft — Published Decks</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Inter', 'Noto Sans TC', system-ui, sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    padding: 40px 20px;
    max-width: 900px;
    margin: 0 auto;
}}
h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; color: #fff; }}
.subtitle {{ color: #888; margin-bottom: 32px; font-size: 15px; }}
.deck-grid {{ display: flex; flex-direction: column; gap: 12px; }}
.deck-card {{
    display: block;
    background: #151520;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 20px;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.2s, background 0.2s;
}}
.deck-card:hover {{ border-color: #6C5CE7; background: #1a1a2e; }}
.deck-card h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 8px; color: #fff; }}
.deck-card .meta {{ display: flex; gap: 16px; font-size: 13px; color: #888; margin-bottom: 10px; }}
.deck-card .badges {{ display: flex; gap: 6px; margin-bottom: 10px; }}
.deck-card .badge {{
    font-size: 11px; padding: 2px 8px; border-radius: 4px;
    font-weight: 600; letter-spacing: 0.5px;
}}
.badge.html {{ background: #1a3a2a; color: #4ade80; }}
.badge.pptx {{ background: #1a2a3a; color: #60a5fa; }}
.badge.img {{ background: #2a1a3a; color: #c084fc; }}
.deck-card .footer {{ display: flex; justify-content: space-between; font-size: 13px; }}
.view-link {{ color: #6C5CE7; font-weight: 600; }}
.dl-link {{ color: #60a5fa; }}
.empty {{ text-align: center; padding: 60px 20px; color: #666; }}
.empty p {{ font-size: 18px; margin-bottom: 8px; }}
</style>
</head>
<body>
<h1>🎯 SlideCraft</h1>
<p class="subtitle">Published decks — {len(decks)} total</p>
<div class="deck-grid">
{''.join(cards) if cards else '<div class="empty"><p>No decks generated yet</p><p>Run the CLI to create your first deck</p></div>'}
</div>
</body>
</html>"""


def deploy(deck_names: list[str] = None, all_decks: bool = False, latest: bool = False) -> str:
    """
    Deploy decks to GitHub Pages.

    Args:
        deck_names: Specific deck names to publish
        all_decks: Publish all decks
        latest: Publish only the most recent deck

    Returns:
        GitHub Pages URL
    """
    decks = get_decks()
    if not decks:
        return "No decks found in output/"

    if latest:
        selected = decks[:1]
    elif deck_names:
        selected = [d for d in decks if d["name"] in deck_names]
    else:
        selected = decks

    if not selected:
        return "No matching decks found"

    print(f"📦 Deploying {len(selected)} deck(s) to GitHub Pages...")

    # Create a temp directory and clone existing gh-pages branch
    with tempfile.TemporaryDirectory() as tmp:
        pages_dir = Path(tmp) / "pages"
        
        # Clone existing gh-pages branch (shallow, preserve existing files like landing page)
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "gh-pages",
             f"git@github.com:{REPO}.git", str(pages_dir)],
            capture_output=True, text=True, timeout=30,
        )
        
        if clone.returncode != 0 and "couldn't find remote ref" not in clone.stderr:
            # If branch doesn't exist yet, create fresh
            print("  ⚠️  gh-pages branch not found, creating fresh...")
            pages_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(pages_dir), capture_output=True)
            subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=str(pages_dir), capture_output=True)
        elif clone.returncode != 0:
            # "couldn't find remote ref" = new repo, create fresh
            print("  ⚠️  gh-pages branch not found, creating fresh...")
            pages_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(pages_dir), capture_output=True)
            subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=str(pages_dir), capture_output=True)
        else:
            print(f"  ✅ Cloned existing gh-pages branch")

        # Copy HTML files and images (only selected ones)
        for d in selected:
            name = d["name"]
            src_html = OUTPUT_DIR / f"{name}.html"
            src_pptx = OUTPUT_DIR / f"{name}.pptx"
            src_images = OUTPUT_DIR / f"{name}_images"

            if src_html.exists():
                (pages_dir / f"{name}.html").write_text(src_html.read_text())
                print(f"  ✅ {name}.html")

            if src_pptx.exists():
                import shutil
                shutil.copy2(str(src_pptx), str(pages_dir / f"{name}.pptx"))
                print(f"  ✅ {name}.pptx")

            if src_images.exists():
                dest = pages_dir / f"{name}_images"
                import shutil
                shutil.copytree(str(src_images), str(dest), dirs_exist_ok=True)
                print(f"  ✅ {name}_images/")

        # Rebuild full index from ALL decks, not just selected ones
        all_decks_list = get_decks()
        index = build_index_page(all_decks_list)
        (pages_dir / "index.html").write_text(index)

        # Add, commit and push (no force: preserve existing files)
        orig_dir = os.getcwd()
        subprocess.run(["git", "add", "-A"], cwd=str(pages_dir), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"deploy: {len(selected)} deck(s)"],
            cwd=str(pages_dir), capture_output=True,
        )

        # If repo was init'd fresh, add remote
        if clone.returncode != 0:
            subprocess.run(
                ["git", "remote", "add", "origin", f"git@github.com:{REPO}.git"],
                cwd=str(pages_dir), capture_output=True, text=True,
            )

        push = subprocess.run(
            ["git", "push", "origin", "gh-pages"],
            cwd=str(pages_dir), capture_output=True, text=True, timeout=30,
        )
        # If non-fast-forward (e.g. concurrent changes), fall back to --force
        if push.returncode != 0 and "non-fast-forward" in push.stderr:
            print("  ⚠️  Non-fast-forward push, retrying with --force...")
            push = subprocess.run(
                ["git", "push", "--force", "origin", "gh-pages"],
                cwd=str(pages_dir), capture_output=True, text=True, timeout=30,
            )

        if push.returncode != 0:
            return f"Push failed: {push.stderr[:300]}"

    url = f"https://julian67chou.github.io/slidecraft/"
    print(f"\n🌐 Published: {url}")
    return url


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        result = deploy(all_decks=True)
    elif "--latest" in args:
        result = deploy(latest=True)
    elif args:
        result = deploy(deck_names=args)
    else:
        print("Usage: python -m orchestrator.deploy [deck_names...] [--all] [--latest]")
        sys.exit(1)
    print(result)
