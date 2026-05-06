from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class SectionBlock(BaseModel):
    title: str
    paragraphs: list[list[str]]


class ScriptDocument(BaseModel):
    source_file: str
    title: str
    sections: list[SectionBlock]


class SentenceScene(BaseModel):
    sentence_index: int
    alignment_id: str = ''
    sentence: str
    youtube_sentence: str = ''
    academic_sentence: str = ''
    section_theme: str = ''
    page_id: str = ''
    page_position: int = 0
    scene_duration_sec: float = 2.8
    alignment_confidence: float = 1.0
    visual_concept: str
    image_prompt: str
    on_screen_text: str = ''
    placement: str = 'side label'
    background_animation: str = 'slow zoom'
    arrows_connections: str = 'no'
    visual_elements: list[str] = Field(default_factory=list)
    typography_block: dict[str, str] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    key_visual_tokens: list[str] = Field(default_factory=list)
    compositional_layers: list[str] = Field(default_factory=list)
    text_box_style: str = 'standard side box'
    motion_guidance: str = 'minimal face/hand motion; gentle full-body orientation shifts'
    map_required: bool = False
    quote_full_text: str = ''
    canva_only: bool = True
    scene_checklist: list[str] = Field(default_factory=list)
    additional_notes: str = ''
    paragraph_image_prompts: list[str] = Field(default_factory=list)
    overlay_text_elements: list[dict[str, str]] = Field(default_factory=list)
    chicago_citations: list[dict[str, str]] = Field(default_factory=list)
    image_path: str | None = None


class ParagraphPlan(BaseModel):
    paragraph_index: int
    scenes: list[SentenceScene] = Field(default_factory=list)


class SectionPlan(BaseModel):
    title: str
    paragraphs: list[ParagraphPlan] = Field(default_factory=list)


class Storyboard(BaseModel):
    title: str
    source_file: str
    academic_source_file: str | None = None
    sync_mode: Literal['single_script', 'dual_script'] = 'single_script'
    provider: Literal['fallback', 'openai_compatible'] = 'fallback'
    style_prompt: str
    brand_name: str = 'Theology Academy'
    canva_only_images: bool = True
    compliance_report: dict[str, object] = Field(default_factory=dict)
    sections: list[SectionPlan] = Field(default_factory=list)
