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
deckspec/         ← Pydantic schema
renderers/
  html/           ← HTML renderer + slider.js
  pptx/           ← python-pptx renderer
orchestrator/     ← pipeline + Grok Draw
```
