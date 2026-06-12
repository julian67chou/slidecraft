"""
DeckSpec — The single contract flowing between all pipeline stages.
Pydantic models with JSON serialization for orchestrator ↔ renderer communication.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Slide Content Types ────────────────────────────────────────────────

class Stat(BaseModel):
    """A data point with a label, e.g. '85%' / 'Conversion Rate'"""
    value: str
    label: str
    icon: Optional[str] = None


class Column(BaseModel):
    """A single column in a multi-column layout"""
    heading: str
    items: list[str] = Field(default_factory=list)


class Step(BaseModel):
    """A single step in a numbered process"""
    number: int
    title: str
    description: str


class Quote(BaseModel):
    """A quote with attribution"""
    text: str
    source: str


class Visual(BaseModel):
    """Visual asset directive for this slide"""
    type: str = Field(
        default="none",
        description="One of: none, image, icon, chart, background"
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Image generation prompt (sent to Grok Draw)"
    )
    icon_name: Optional[str] = None
    generated_path: Optional[str] = Field(
        default=None,
        description="Filled in by pipeline: path to generated image file"
    )


class SlideContent(BaseModel):
    """The actual content of a slide — structured, not raw text"""
    title: str
    subtitle: Optional[str] = None
    bullets: list[str] = Field(default_factory=list)
    stats: list[Stat] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    quote: Optional[Quote] = None
    visual: Visual = Field(default_factory=Visual)
    extra: dict = Field(default_factory=dict)


# ─── Slide & Deck Spec ──────────────────────────────────────────────────

class SlideSpec(BaseModel):
    """Specification for a single slide"""
    id: str = Field(description="Stable slide ID, e.g. 's01', 'title', 'closing'")
    order: int = Field(ge=1, description="Slide order in deck (1-indexed, contiguous)")
    layout: str = Field(description="Layout type from design tokens: cover, card-list, image-text, grid, transition, content, two-column, stat-card, timeline")
    content: SlideContent
    speaker_notes: Optional[str] = None
    background_override: Optional[str] = Field(
        default=None,
        description="Override slide background color (hex) for this slide only"
    )
    background_image: Optional[str] = Field(
        default=None,
        description="Path to full-bleed background image for this slide (e.g. cover or section backgrounds). "
                    "The orchestrator engine can generate it from background_prompt and populate the final path."
    )
    background_prompt: Optional[str] = Field(
        default=None,
        description="Prompt used by the engine to generate a full-bleed background image via Grok Draw "
                    "(if background_image is not already a valid existing path)."
    )


class GlobalDesign(BaseModel):
    """Theme and style applied to all slides"""
    theme_id: str = Field(description="Design token theme name, e.g. 'clinic-warm'")
    accent_override: Optional[str] = None


class DeckSpec(BaseModel):
    """Complete deck specification — the single contract for the whole pipeline"""
    deck_id: str = Field(description="Unique deck identifier")
    title: str = Field(description="Deck title")
    num_slides: int = Field(ge=1)
    global_design: GlobalDesign
    slides: list[SlideSpec]
    source_prompt: str = Field(description="Original user prompt")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON for passing between pipeline stages"""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str) -> "DeckSpec":
        """Deserialize from JSON"""
        return cls.model_validate_json(data)


# ─── Pipeline Communication ─────────────────────────────────────────────

class RenderArtifact(BaseModel):
    """Output from a single slide renderer"""
    slide_id: str
    order: int
    layout: str
    format: str = Field(description="'html' or 'pptx'")
    path: str = Field(description="File path to rendered artifact")
    assets: list[str] = Field(
        default_factory=list,
        description="Paths to generated images/assets used by this slide"
    )


class DeckArtifact(BaseModel):
    """Final output of the pipeline"""
    deck_id: str
    title: str
    html_path: Optional[str] = None
    pptx_path: Optional[str] = None
    slide_artifacts: list[RenderArtifact] = Field(default_factory=list)


class RefinementDelta(BaseModel):
    """Patch for targeted refinement — only changed fields"""
    slide_id: str
    field_path: str = Field(description="Dot-notation path, e.g. 'content.title'")
    new_value: object
