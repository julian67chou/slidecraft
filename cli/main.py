"""
# SlideCraft — CLI entry point.

Usage:
    python -m cli.main --spec <spec_json_or_path> [--theme clinic-warm] [--name output_name]
    python -m cli.main --prompt "建立一份關於 AI 醫療的簡報" [--theme pitch-dark]
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SlideCraft — spec-to-deck generator")
    parser.add_argument("--spec", help="DeckSpec JSON string or path to .json file")
    parser.add_argument("--prompt", "-p", help="Topic description (generates spec)")
    parser.add_argument("--theme", "-t", default="clinic-warm",
                        choices=["clinic-warm", "pitch-dark", "academic-clean",
                                  "tech-neon", "education-warm", "fitness-green",
                                  "finance-navy", "startup-bold", "travel-sunset",
                                  "government-blue", "ngo-warm"],
                        help="Slide theme")
    parser.add_argument("--name", "-n", default=None)
    parser.add_argument("--deploy", "-d", action="store_true",
                        help="Deploy to GitHub Pages after generation")
    parser.add_argument("--list-themes", action="store_true",
                        help="List available themes")
    parser.add_argument("--no-build-steps", action="store_true",
                        help="Disable build step animations (text appears all at once)")

    # Renderer mode flags (passed to HTML renderer)
    parser.add_argument("--standalone", dest="standalone", action="store_true", default=True,
                        help="Self-contained HTML: embed slidecraft.css + slider.js (default, single-file)")
    parser.add_argument("--external", dest="standalone", action="store_false",
                        help="External CSS/JS: smaller HTML + slidecraft.css/slider.js copied next to output")
    parser.add_argument("--css-path", default=None,
                        help="Custom <link href> when --external (default: slidecraft.css)")
    parser.add_argument("--js-path", default=None,
                        help="Custom <script src> when --external (default: slider.js)")

    args = parser.parse_args()

    if args.list_themes:
        import yaml
        from pathlib import Path
        themes_dir = Path(__file__).parent.parent / "design-tokens" / "themes"
        print("Available themes:")
        for f in sorted(themes_dir.glob("*.yaml")):
            with open(f) as fh:
                t = yaml.safe_load(fh)
            name = f.stem
            desc = t.get("description", "")
            accent = t.get("colors", {}).get("accent", "")
            print(f"  {name:20s} {accent}  {desc}")
        return

    # Get spec
    if args.spec:
        if os.path.exists(args.spec):
            with open(args.spec) as f:
                spec = json.load(f)
        else:
            spec = json.loads(args.spec)
    elif args.prompt:
        # Hermes generates the spec — just use a simple heuristic here
        # In practice, Hermes agent would plan this conversationally
        print("Please provide a --spec JSON. Use --prompt to describe the topic.")
        print("Example: python -m cli.main --spec path/to/spec.json")
        sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    from orchestrator.engine import generate

    build_steps = not args.no_build_steps
    result = generate(
        spec,
        output_name=args.name,
        build_steps=build_steps,
        standalone=args.standalone,
        css_path=getattr(args, "css_path", None),
        js_path=getattr(args, "js_path", None),
    )

    print(f"\n{'='*50}")
    print(f"  ✅ {result['title']}")
    print(f"  Slides: {result['slides']}")
    print(f"  HTML:  {result['html']}")
    print(f"  PPTX:  {result['pptx']}")
    print(f"{'='*50}")

    if args.deploy:
        from orchestrator.deploy import deploy
        url = deploy(deck_names=[args.name or result.get("title", "").lower().replace(" ", "-")])
        print(f"\n🌐 {url}")


if __name__ == "__main__":
    main()
