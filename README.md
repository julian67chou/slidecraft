# SlideCraft

Prompt → Stunning Deck in seconds.

- **13 layouts**: cover, card-list, image-text, grid, transition, content, two-column, stat-card, timeline, comparison, quote, team, process-flow
- **11 themes**: clinic-warm, pitch-dark, academic-clean, tech-neon, education-warm, fitness-green, finance-navy, startup-bold, travel-sunset, government-blue, ngo-warm
- **Dual output**: HTML (slider mode with presenter view) + PPTX (editable CJK)
- **AI images**: Grok Draw generates 16:9 presentation backgrounds
- **CJK first**: Chinese/Japanese/Korean typography as priority

## Quick Start

```bash
cd /workspace/slidecraft

# Generate a deck
python3 -c "
from orchestrator.engine import generate
spec = {
    'deck_id': 'my-deck',
    'title': 'My Presentation',
    'slides': [...],
    'global_design': {'theme_id': 'clinic-warm'}
}
generate(spec, 'my-deck')
# → output/my-deck.html (browser-ready)
# → output/my-deck.pptx (editable)
"

# Or generate with Grok Draw images
# (Grok automatically generates visuals for slides with visual.prompt)
```

## Output

Generated decks are in `output/`. Open `.html` files directly in browser.
Use keyboard: ← → to navigate, F for fullscreen, S for presenter mode.

### Build Step Animations (HTML only)
The HTML viewer supports PPT-style "build" animations for progressive reveal:
- Elements that support stepping (e.g. bullets, cards, grid boxes, stats, timeline items, quote text then source, etc.) are hidden initially.
- Press → (or click right half / tap right / Space / ArrowDown) to reveal the next item **within the current slide**.
- Only after all steps on a slide are visible does → advance to the next slide.
- ← rewinds the last step first, then goes to the previous slide.
- Layouts like `transition` always appear all-at-once (no steps).
- Driven by `data-step="N"` + `.step-item` / `.step-visible` classes (0.35s opacity + translateY CSS transitions).
- Respects the core navigation model: no behavior change to arrows when there are no steps. 

This is a lightweight web-only effect (speaker controls the pace). PPTX exports are static.

## Architecture

```
design-tokens/    ← YAML theme system
  themes/         ← 11 themes
deckspec/         ← Pydantic schema (the contract)
renderers/
  html/           ← HTML renderer + slider.js
  pptx/           ← python-pptx renderer
orchestrator/     ← pipeline + Grok Draw
```

## DeckSpec Fields (the integration contract)

The `DeckSpec` (see `deckspec/schema.py`) is the stable contract between "planning" layers (e.g. presentation-builder / Hermes) and the SlideCraft engine.

Key fields on each slide (in addition to the classic `layout`, `content`, `visual`, etc.):

- `background_image`: Path to a full-bleed background image (used by the HTML renderer for `<img class="slide-bg">`).
- `background_prompt`: If present and `background_image` is missing/invalid, the engine will automatically call Grok Draw (via `generate_background`) to create the image and fill in the path. Theme colors are passed for visual consistency.
- `background_override`: Per-slide background style override. Solid hex colors are supported everywhere. Complex values (e.g. `linear-gradient(...)`) are honored by the HTML renderer (great for dark overlays on photos) and gracefully ignored by the PPTX renderer (falls back to theme bg).

Example slide with background support:

```json
{
  "id": "s01",
  "order": 1,
  "layout": "cover",
  "background_image": "output/my-deck_images/slide_01_bg.jpg",
  "background_prompt": "Minimalist dark navy tech background with subtle circuit lines, 16:9, professional",
  "background_override": "linear-gradient(135deg, rgba(10,14,39,0.75) 0%, rgba(10,14,39,0.45) 100%)",
  "content": { "title": "...", ... }
}
```

## Using the Engine from Code / CLI (clean public API)

```python
from orchestrator.engine import generate, generate_from_deckspec_file

# From dict (or from a planning agent)
result = generate(my_deckspec_dict, output_name="my-deck")

# Preferred for CLI / external tools: load directly from file (validates + deepcopy + no mutation)
result = generate_from_deckspec_file("path/to/spec.json", output_name="my-deck", build_steps=True)

# generate() itself now also accepts a path:
result = generate("path/to/spec.json", ...)
```

The engine automatically:
- Validates (best-effort) against the Pydantic schema.
- Generates images for both `visual.prompt` and `background_prompt`.
- Copies all assets into a self-contained `<name>_images/` folder with stable relative paths.
- Handles graceful degradation when images are missing (404-safe in HTML).

See `orchestrator/engine.py` for the full `generate(...)` signature and `generate_from_deckspec_file` wrapper.
