from __future__ import annotations

from pathlib import Path
from difflib import SequenceMatcher
import re

from app.config import settings
from app.compliance import build_compliance_report
from app.exporters import export_storyboard
from app.llm import LLMPlanner
from app.models import ParagraphPlan, ScriptDocument, SectionPlan, SentenceScene, Storyboard
from app.parser import analyze_paragraph, extract_bibliography_map, is_visual_content_paragraph, parse_script
from app.prompts import BRAND_RENDERING_DEFAULT, ensure_brand_block
from app.utils import ensure_dir, safe_slug

BAD_OVERLAY_PREFIXES = {'ever', 'how', 'who', 'what', "let's", 'lets', 'now', 'finally'}
LEGACY_STYLE_PATTERN = r"A detailed black-and-white charcoal rendering.*?medium shot\.?"
VIBRANT_STYLE_PATTERN = r"A richly detailed illustration with fully vibrant saturated colours, executed in a classical painterly style with warm natural lighting, high contrast, and cinematic depth of field, medium shot\.?"
BRAND_BLOCK_WRAPPER_PATTERN = r"---BRAND RENDERING BLOCK(?: \(append verbatim to every image_prompt\))?---|---END BRAND RENDERING BLOCK---|---BRAND RENDERING BLOCK---|---BRAND RENDERING---"
PARTIAL_BRAND_FRAGMENT_PATTERN = r"---BRAND[^\n.]*|Rendered as a heavy, hand-worked charcoal.*$"
STYLE_SENTENCE_FALLBACK = BRAND_RENDERING_DEFAULT


class StoryboardPipeline:
    def run(
        self,
        input_path: str,
        academic_input_path: str | None = None,
        provider: str = 'xai',
        style_prompt: str | None = None,
        title_override: str | None = None,
    ) -> Path:
        style = style_prompt or settings.default_style_prompt
        script = parse_script(input_path, title_override=title_override)
        academic_script = parse_script(academic_input_path, title_override=title_override) if academic_input_path else None
        bibliography_map = extract_bibliography_map(input_path)
        planner = LLMPlanner(provider='xai')

        sections: list[SectionPlan] = []
        global_index = 1
        for s_idx, section in enumerate(script.sections, start=1):
            page_id = f"page_{safe_slug(section.title)}"
            page_position = 1
            paragraph_plans: list[ParagraphPlan] = []
            for p_idx, paragraph_sentences in enumerate(section.paragraphs, start=1):
                paragraph_text = ' '.join(paragraph_sentences).strip()
                paragraph_analysis = analyze_paragraph(paragraph_text)
                if not is_visual_content_paragraph(paragraph_analysis):
                    continue
                academic_paragraph = _academic_paragraph_text(academic_script, s_idx - 1, p_idx - 1)
                if bool(paragraph_analysis.get('is_transition_paragraph')):
                    result = _transition_result(section.title, paragraph_text, style)
                    max_prompts = 1
                else:
                    result = planner.plan_paragraph(
                        script.title,
                        section.title,
                        paragraph_text,
                        style,
                        paragraph_analysis=paragraph_analysis,
                    )
                    max_prompts = _allowed_prompt_count(paragraph_analysis)
                paragraph_prompts = [str(item.get('image_prompt', '')).strip() for item in result.get('prompts', []) if isinstance(item, dict)]
                try:
                    overlay_payload = planner.generate_overlay_elements(
                        section.title,
                        paragraph_text,
                        episode_section_type=section.title,
                    )
                except Exception:
                    overlay_payload = {'text_elements': []}
                try:
                    citation_payload = planner.generate_chicago_citations(paragraph_text, bibliography_map)
                except Exception:
                    citation_payload = {'citations': []}
                citation_payload = _ensure_citation_payload(paragraph_text, bibliography_map, citation_payload)
                scenes: list[SentenceScene] = []
                for prompt_plan in result.get('prompts', [])[:max_prompts]:
                    alignment_id = f"ALN-{global_index:04d}"
                    raw_prompt = str(prompt_plan.get('image_prompt', ''))
                    visual_concept = str(prompt_plan.get('visual_concept', 'Canva prompt scene'))
                    on_screen_text = str(prompt_plan.get('on_screen_text', ''))
                    image_prompt = _simplify_prompt_density(raw_prompt, paragraph_analysis, visual_concept)
                    image_prompt = _inject_theology_symbolism(image_prompt, paragraph_analysis, visual_concept)
                    image_prompt = _ensure_style(image_prompt, style)
                    map_required = 'map' in image_prompt.lower()
                    placement = _infer_scene_placement(
                        image_prompt=image_prompt,
                        paragraph_analysis=paragraph_analysis,
                        visual_concept=visual_concept,
                        overlay_text=on_screen_text,
                    )
                    references = _scene_reference_lines(citation_payload)
                    scenes.append(
                        SentenceScene(
                            sentence_index=global_index,
                            alignment_id=alignment_id,
                            sentence=paragraph_text,
                            youtube_sentence=paragraph_text,
                            academic_sentence=academic_paragraph,
                            section_theme=section.title,
                            page_id=page_id,
                            page_position=page_position,
                            scene_duration_sec=2.8,
                            alignment_confidence=_alignment_confidence(paragraph_text, academic_paragraph),
                            visual_concept=visual_concept,
                            image_prompt=image_prompt,
                            on_screen_text=on_screen_text,
                            placement=placement,
                            background_animation='zoom in then zoom out',
                            arrows_connections=str(prompt_plan.get('arrows_connections', 'no')),
                            visual_elements=_visual_elements_from_prompt(
                                image_prompt,
                                paragraph_analysis,
                                placement=placement,
                                visual_concept=visual_concept,
                            ),
                            key_visual_tokens=_key_tokens(paragraph_text),
                            compositional_layers=_layers_from_prompt(image_prompt),
                            text_box_style=_text_box_style(placement),
                            motion_guidance='Keep facial and hand motion minimal. Use simple zoom-based movement only.',
                            map_required=map_required,
                            quote_full_text=_extract_quote(paragraph_text),
                            canva_only=settings.canva_only_images,
                            scene_checklist=_scene_checklist(map_required),
                            typography_block=_typography_block(),
                            references=references,
                            additional_notes=str(prompt_plan.get('additional_notes', '')),
                            paragraph_image_prompts=paragraph_prompts[:3],
                            overlay_text_elements=[
                                {
                                    'type': str(item.get('type', 'keyword')),
                                    'content': str(item.get('content', '')).strip(),
                                    'timing_hint': str(item.get('timing_hint', 'middle')),
                                }
                                for item in overlay_payload.get('text_elements', [])[:12]
                                if isinstance(item, dict)
                            ],
                            chicago_citations=[
                                {
                                    'citation_number': str(item.get('citation_number', '')).strip(),
                                    'sentence_excerpt': str(item.get('sentence_excerpt', '')).strip(),
                                    'citation_short': str(item.get('citation_short', '')).strip(),
                                    'citation_full': str(item.get('citation_full', '')).strip(),
                                }
                                for item in citation_payload.get('citations', [])
                                if isinstance(item, dict)
                            ],
                        )
                    )
                    global_index += 1
                    page_position += 1
                paragraph_plans.append(ParagraphPlan(paragraph_index=p_idx, scenes=scenes))
            sections.append(SectionPlan(title=section.title, paragraphs=paragraph_plans))

        storyboard = Storyboard(
            title=script.title,
            source_file=script.source_file,
            academic_source_file=academic_script.source_file if academic_script else None,
            sync_mode='dual_script' if academic_script else 'single_script',
            provider='openai_compatible',
            style_prompt=style,
            brand_name=settings.brand_name,
            canva_only_images=settings.canva_only_images,
            sections=sections,
        )
        _finalize_storyboard(storyboard, style)
        storyboard.compliance_report = build_compliance_report(storyboard, style_prompt=style)
        out_dir = ensure_dir(Path(settings.output_dir) / safe_slug(script.title))
        export_storyboard(storyboard, out_dir)
        return out_dir


def _academic_paragraph_text(academic_script: ScriptDocument | None, section_idx: int, paragraph_idx: int) -> str:
    if not academic_script:
        return ''
    try:
        return ' '.join(academic_script.sections[section_idx].paragraphs[paragraph_idx]).strip()
    except Exception:
        return ''


def _alignment_confidence(youtube: str, academic: str) -> float:
    if not academic:
        return 1.0
    return round(SequenceMatcher(None, youtube.lower(), academic.lower()).ratio(), 3)


def _ensure_style(prompt: str, style: str) -> str:
    body = (prompt or '').strip()
    style_clean = _normalized_style_sentence(style)
    if not style_clean:
        return body

    # Remove duplicated style occurrences/fragments, then append exactly once at the end.
    body = re.sub(
        LEGACY_STYLE_PATTERN,
        " ",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(VIBRANT_STYLE_PATTERN, " ", body, flags=re.IGNORECASE)
    body = re.sub(BRAND_BLOCK_WRAPPER_PATTERN, " ", body, flags=re.IGNORECASE)
    body = re.sub(PARTIAL_BRAND_FRAGMENT_PATTERN, " ", body, flags=re.IGNORECASE)
    candidates = {
        (style or '').strip(),
        style_clean,
        style_clean.rstrip('.'),
    }
    for candidate in sorted((c for c in candidates if c), key=len, reverse=True):
        body = re.sub(re.escape(candidate), ' ', body)

    body = re.sub(r'\s{2,}', ' ', body).strip()
    if not body:
        return style_clean
    return ensure_brand_block(body)


def _normalized_style_sentence(style: str) -> str:
    style_clean = ' '.join((style or '').split()).strip()
    if style_clean and (
        re.search(LEGACY_STYLE_PATTERN, style_clean, flags=re.IGNORECASE)
        or re.search(VIBRANT_STYLE_PATTERN, style_clean, flags=re.IGNORECASE)
    ):
        style_clean = settings.default_style_prompt or STYLE_SENTENCE_FALLBACK
    if not style_clean:
        return settings.default_style_prompt or STYLE_SENTENCE_FALLBACK
    return style_clean.rstrip()


def _finalize_storyboard(storyboard: Storyboard, style: str) -> None:
    previous_overlay = ''
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            if not paragraph.scenes:
                continue
            canonical_prompts = _sanitize_paragraph_prompts(paragraph.scenes[0].paragraph_image_prompts, style)
            if not canonical_prompts:
                canonical_prompts = [_sanitize_canva_image_prompt(paragraph.scenes[0].image_prompt, style)]
            canonical_overlays = _sanitize_overlay_elements(
                paragraph.scenes[0].overlay_text_elements,
                paragraph.scenes[0].sentence,
            )
            canonical_citations = _sanitize_citations(paragraph.scenes[0].chicago_citations, paragraph.scenes[0].sentence)
            for scene in paragraph.scenes:
                scene.image_prompt = _strip_internal_generation_rules(scene.image_prompt)
                scene.image_prompt = _strip_irrelevant_christology_symbolism(
                    scene.image_prompt,
                    scene.sentence,
                    scene.visual_concept,
                )
                scene.image_prompt = _sanitize_canva_image_prompt(scene.image_prompt, style)
                scene.image_prompt = _ensure_style(scene.image_prompt, style)
                scene.quote_full_text = scene.quote_full_text or _extract_quote(scene.sentence)
                scene.on_screen_text = _normalize_overlay_text(
                    scene.on_screen_text or scene.sentence,
                    scene.visual_concept,
                    has_quote=bool(scene.quote_full_text),
                )

                if _is_transition_scene(scene):
                    scene.scene_duration_sec = 2.0
                    scene.placement = 'side label'
                    scene.visual_elements = ['architecture', 'manuscripts', 'parchment']
                    if _has_named_figures_in_text(scene.sentence):
                        scene.visual_elements.append('historical figures')
                else:
                    scene.placement = _validated_placement(scene)
                    scene.visual_elements = _visual_elements_from_prompt(
                        scene.image_prompt,
                        placement=scene.placement,
                        visual_concept=scene.visual_concept,
                    )
                    if scene.placement == 'map label' and 'map' not in scene.visual_elements:
                        scene.placement = 'side label'
                    if scene.placement == 'center quote box' and not scene.quote_full_text:
                        scene.placement = 'side explainer box'

                if previous_overlay and scene.on_screen_text.lower() == previous_overlay.lower():
                    scene.on_screen_text = _make_overlay_distinct(scene.on_screen_text)
                previous_overlay = scene.on_screen_text

                scene.text_box_style = _text_box_style(scene.placement)
                scene.map_required = scene.placement == 'map label' or 'map' in scene.image_prompt.lower()
                scene.paragraph_image_prompts = canonical_prompts[:]
                scene.overlay_text_elements = canonical_overlays[:]
                scene.chicago_citations = canonical_citations[:]
                scene.references = _scene_reference_lines({'citations': scene.chicago_citations})

    _fill_transition_scene_citations(storyboard)


def _fill_transition_scene_citations(storyboard: Storyboard) -> None:
    scenes: list[SentenceScene] = [
        scene
        for section in storyboard.sections
        for paragraph in section.paragraphs
        for scene in paragraph.scenes
    ]
    if not scenes:
        return

    for idx, scene in enumerate(scenes):
        if not _is_transition_scene(scene):
            continue
        if scene.chicago_citations:
            scene.references = _scene_reference_lines({'citations': scene.chicago_citations})
            continue

        inherited = _nearest_scene_citations(scenes, idx)
        if not inherited:
            continue

        scene.chicago_citations = [dict(item) for item in inherited]
        scene.references = _scene_reference_lines({'citations': scene.chicago_citations})


def _nearest_scene_citations(scenes: list[SentenceScene], idx: int) -> list[dict[str, str]]:
    for offset in range(1, len(scenes)):
        forward = idx + offset
        if forward < len(scenes) and scenes[forward].chicago_citations:
            return [dict(item) for item in scenes[forward].chicago_citations]
        backward = idx - offset
        if backward >= 0 and scenes[backward].chicago_citations:
            return [dict(item) for item in scenes[backward].chicago_citations]
    return []


def _is_transition_scene(scene: SentenceScene) -> bool:
    note = (scene.additional_notes or '').lower()
    concept = (scene.visual_concept or '').lower()
    sentence = (scene.sentence or '').lower()
    return (
        'transition paragraph' in note
        or concept == 'contextual scholarly illustration'
        or sentence.startswith('**transition:**')
        or sentence.startswith('transition:')
    )


def _normalize_overlay_text(text: str, visual_concept: str, has_quote: bool = False) -> str:
    concept_words = _meaningful_overlay_words(visual_concept)
    quote_words = _meaningful_overlay_words(_extract_quote(text)) if has_quote else []
    if quote_words:
        words = quote_words[:5]
    elif concept_words:
        words = concept_words[:5]
    else:
        source = ' '.join((text or '').replace('*', ' ').split()).strip()
        words = _meaningful_overlay_words(source)
    if not words:
        words = ['Key', 'Doctrine']
    if words[0].lower() in BAD_OVERLAY_PREFIXES:
        words = concept_words[:5] if concept_words else ['Key', 'Doctrine']

    if len(words) < 2:
        if concept_words:
            words = (words + concept_words)[:2]
        else:
            words = (words + ['Concept'])[:2]

    deduped_words: list[str] = []
    for word in words:
        if not deduped_words or word.lower() != deduped_words[-1].lower():
            deduped_words.append(word)
    words = deduped_words
    if len(words) < 2:
        words = (words + ['Key'])[:2]

    words = words[:5]
    # Avoid CTA-style overlays in academic output.
    if any(w.lower() in {'like', 'subscribe', 'comment'} for w in words):
        words = ['Core', 'Concept']
    return _title_overlay(' '.join(words))


def _meaningful_overlay_words(text: str) -> list[str]:
    stop = {
        'the', 'a', 'an', 'in', 'on', 'at', 'to', 'of', 'for', 'with', 'by', 'from', 'and', 'or',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'this', 'that', 'these', 'those', 'it',
        'as', 'into', 'about', 'through', 'between', 'across', 'around', 'came', 'first', 'later',
        'after', 'before', 'did', 'not', 'got', 'stage', 'teaches',
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or '')
    return [token for token in tokens if token.lower() not in stop]


def _title_overlay(text: str) -> str:
    parts = text.replace("’", "'").split()
    normalized: list[str] = []
    for part in parts:
        if "'" in part:
            left, right = part.split("'", 1)
            normalized.append(f"{left[:1].upper()}{left[1:].lower()}'{right[:1].lower()}{right[1:].lower()}")
        else:
            normalized.append(part[:1].upper() + part[1:].lower())
    return ' '.join(normalized)


def _extract_quote(text: str) -> str:
    m = re.search(r'["“](.*?)["”]', text)
    return m.group(1).strip() if m else ''


def _key_tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    stop = {'the','and','for','with','that','this','from','into','while','about','their','they','were','have','will','just','using','amid'}
    out = []
    for w in words:
        if w.lower() in stop:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= 8:
            break
    return out


def _visual_elements_from_prompt(
    prompt: str,
    paragraph_analysis: dict[str, object] | None = None,
    placement: str = 'side label',
    visual_concept: str = '',
) -> list[str]:
    lowered = prompt.lower()
    analysis = paragraph_analysis or {}
    concept = (visual_concept or '').lower()
    elements: list[str] = []
    if 'map' in lowered or placement == 'map label':
        elements.append('map')
    if any(w in lowered for w in ['arrow', 'route', 'connector']):
        elements.append('arrows')
    if analysis.get('named_figures') or any(w in lowered for w in ['historical figure', 'historically accurate', 'scholar', 'portrait', 'bishop', 'council fathers']):
        elements.append('historical figures')
    if any(w in lowered for w in ['diagram', 'symbolic', 'sphere', 'connector', 'layered']):
        elements.append('symbolic diagram')
    if any(w in lowered for w in ['split composition', 'left-right', 'east-west', 'east west', 'divided scene']):
        elements.append('split composition')
    if any(w in lowered for w in ['doctrinal contrast', 'theological contrast', 'east-west contrast', 'contrast']):
        elements.append('doctrinal contrast')
    if any(w in lowered for w in ['timeline', 'chronological', 'century progression', 'major anchors']) or 'timeline' in concept:
        elements.append('timeline')
    if any(w in lowered for w in ['council', 'synod', 'debate']) and 'council scene' not in elements:
        elements.append('council scene')
    if any(w in lowered for w in ['architecture', 'cathedral', 'church interior', 'stone hall']):
        elements.append('architecture')
    if placement == 'center quote box' or 'quote' in lowered:
        elements.append('quote treatment')
    if not elements:
        elements.append('contextual illustration')
    # Keep unique ordering and avoid stale tags that are unsupported by prompt intent.
    deduped = []
    for item in elements:
        if item not in deduped:
            deduped.append(item)
    if 'historical figures' in deduped and not analysis.get('named_figures') and not any(w in lowered for w in ['portrait', 'scholar', 'council fathers', 'historical figure']):
        deduped.remove('historical figures')
    return deduped


def _layers_from_prompt(prompt: str) -> list[str]:
    layers = []
    lowered = prompt.lower()
    if 'map' in lowered:
        layers.append('midground map or geographic frame')
    if any(w in lowered for w in ['symbolic', 'diagram', 'connector']):
        layers.append('foreground symbolic comparison elements')
    if any(w in lowered for w in ['historically accurate', 'figure', 'scholar']):
        layers.append('foreground figures or discussion focal point')
    layers.append('background scholarly parchment texture')
    return layers


def _text_box_style(placement: str) -> str:
    if placement == 'center quote box':
        return 'centered elegant quote box (serif, large)'
    if placement == 'map label':
        return 'map label anchors near locations'
    if placement == 'side explainer box':
        return 'mini side-definition box with connector arrows'
    if placement in {'top title', 'top event title'}:
        return 'bold sans-serif title bar'
    return 'contextual side label box'


def _scene_checklist(map_required: bool) -> list[str]:
    checks = [
        'Use the generated prompt in Canva, not in a direct image API step.',
        'Keep the charcoal visual style consistent across the full video.',
        'Add concise on-screen text manually in Canva when needed.',
    ]
    if map_required:
        checks.append('Include clearly marked locations and subtle arrows in Canva-generated output.')
    return checks


def _typography_block() -> dict[str, str]:
    return {
        'quote_font': 'Georgia, Times New Roman',
        'quote_size': '28-32pt',
        'name_title_font': 'Helvetica, Arial',
        'name_title_size': '18-22pt',
        'definition_font': 'Helvetica, Open Sans',
        'definition_size': '16-18pt',
        'subheading_font': 'Montserrat, Lato',
        'subheading_size': '24-28pt',
    }


def _allowed_prompt_count(paragraph_analysis: dict[str, object]) -> int:
    if bool(paragraph_analysis.get('is_transition_paragraph')) or bool(paragraph_analysis.get('is_transition')):
        return 1

    has_map_or_movement = bool(paragraph_analysis.get('locations')) or bool(paragraph_analysis.get('movement'))
    has_event_or_figures = bool(paragraph_analysis.get('events')) or bool(paragraph_analysis.get('named_figures'))
    has_theology = bool(paragraph_analysis.get('theological_concepts')) or bool(paragraph_analysis.get('definitions')) or bool(paragraph_analysis.get('symbolic_concepts'))
    has_quote = bool(paragraph_analysis.get('quotes'))

    if has_map_or_movement and has_event_or_figures and has_theology:
        return 3
    if has_quote and (has_map_or_movement or has_event_or_figures or has_theology):
        return 2
    if has_map_or_movement and has_theology:
        return 2
    if has_event_or_figures and has_theology:
        return 2

    return 1


def _transition_result(section_title: str, paragraph_text: str, style: str) -> dict[str, object]:
    prompt = (
        f"Contextual scholarly illustration for a transition in section {section_title}, with subtle parchment texture, "
        f"manuscripts, and architecture only, minimal labels. {style}"
    )
    return {
        'paragraph_analysis': 'Transition paragraph detected. Use 1 lightweight contextual prompt only.',
        'prompt_count': 1,
        'prompts': [
            {
                'visual_concept': 'contextual scholarly illustration',
                'image_prompt': prompt,
                'on_screen_text': paragraph_text,
                'placement': 'side label',
                'arrows_connections': 'no',
                'additional_notes': 'Transition paragraph: disable map prompt and symbolic split.',
            }
        ],
    }


def _infer_scene_placement(
    image_prompt: str,
    paragraph_analysis: dict[str, object],
    visual_concept: str,
    overlay_text: str,
) -> str:
    lowered = image_prompt.lower()
    concept = (visual_concept or '').lower()
    overlay = (overlay_text or '').strip()
    has_quote = bool(paragraph_analysis.get('quotes')) or '"' in overlay or 'quote' in lowered or 'quote' in concept
    is_map_or_timeline = any(w in lowered for w in ['map', 'route', 'timeline', 'chronological']) or bool(paragraph_analysis.get('locations')) or bool(paragraph_analysis.get('movement'))
    is_comparison = any(w in lowered for w in ['contrast', 'comparison', 'split composition', 'left-right', 'east-west', 'east west']) or bool(paragraph_analysis.get('symbolic_concepts'))
    is_council_or_portrait = any(w in lowered for w in ['council', 'synod', 'portrait', 'historical figures']) or bool(paragraph_analysis.get('named_figures')) or bool(paragraph_analysis.get('events'))
    is_transition = bool(paragraph_analysis.get('is_transition_paragraph'))

    if has_quote:
        return 'center quote box'
    if is_map_or_timeline:
        return 'map label'
    if is_comparison:
        return 'side explainer box'
    if is_transition:
        return 'side label'
    if is_council_or_portrait:
        return 'top event title' if 'council' in lowered else 'side label'
    return 'side label'


def _inject_theology_symbolism(prompt: str, paragraph_analysis: dict[str, object], visual_concept: str) -> str:
    lowered = prompt.lower()
    theology_terms = ' '.join(str(x).lower() for x in paragraph_analysis.get('theological_concepts', []))
    concept = (visual_concept or '').lower()
    christology_terms = (
        'divinity',
        'divine nature',
        'humanity',
        'human nature',
        'christology',
        'incarnation',
        'two natures',
    )
    has_christology = any(k in lowered for k in christology_terms) or any(k in theology_terms for k in christology_terms)
    has_divine_human_pair = (
        ('divinity' in lowered or 'divine nature' in lowered)
        and ('humanity' in lowered or 'human nature' in lowered)
    ) or (
        ('divinity' in theology_terms or 'divine nature' in theology_terms)
        and ('humanity' in theology_terms or 'human nature' in theology_terms)
    )
    if 'symbolic' in concept and has_christology and has_divine_human_pair and 'blue symbolic sphere' not in lowered:
        return (
            f"{prompt.rstrip('. ')}. "
            "Include a distinct blue symbolic sphere for divinity and a distinct red symbolic sphere for humanity, "
            "overlapping but not blending into purple, with subtle connector arrows where appropriate."
        )
    return prompt


def _simplify_prompt_density(prompt: str, paragraph_analysis: dict[str, object], visual_concept: str) -> str:
    cleaned = ' '.join((prompt or '').split()).strip()
    if not cleaned:
        return cleaned

    cleaned = _strip_internal_generation_rules(cleaned)

    # Keep prompt concise for Canva model quality.
    if len(cleaned) > 620:
        cleaned = cleaned[:620].rsplit(' ', 1)[0].strip()
    return _strip_internal_generation_rules(cleaned)


def _strip_internal_generation_rules(prompt: str) -> str:
    cleaned = prompt or ''
    patterns = (
        r'(?:^|[.;]\s*)Limit foreground to[^.;]*[.;]?',
        r'(?:^|[.;]\s*)Use only three(?: major)? timeline anchors[.;]?',
        r'(?:^|[.;]\s*)Keep one dominant left-right contrast composition[.;]?',
        r'(?:^|[.;]\s*)Focus on a central trio[^.;]*[.;]?',
        r'(?:^|[.;]\s*)arrows_connections\s*[:=]?\s*(?:yes|no)[.;]?',
        r'\barrows_connections\s*[:=]?\s*(?:yes|no)\b',
        r'(?:^|[.;]\s*)placement\s*[:=][^.;]*[.;]?',
        r'(?:^|[.;]\s*)validation hint[^.;]*[.;]?',
        r'(?:^|[.;]\s*)internal (?:rule|instruction)[^.;]*[.;]?',
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    return ' '.join(cleaned.split()).strip(" .;")


def _sanitize_canva_image_prompt(prompt: str, style: str) -> str:
    cleaned = _ensure_style(prompt, style)
    style_clean = _normalized_style_sentence(style) or STYLE_SENTENCE_FALLBACK
    body = cleaned
    body = re.sub(re.escape(style_clean), ' ', body)
    body = re.sub(VIBRANT_STYLE_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = re.sub(BRAND_BLOCK_WRAPPER_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = re.sub(PARTIAL_BRAND_FRAGMENT_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = _remove_forbidden_prompt_artifacts(body)
    body = re.sub(r'(?:\bA detailed(?: black-and-white)?(?: charcoal)?\.?)\s*$', '', body, flags=re.IGNORECASE)
    body = re.sub(r'(?:\b(?:and|yet|the)\.?)\s*$', '', body, flags=re.IGNORECASE)
    body = re.sub(r"\s{2,}", " ", body).strip(" .;")
    if _has_forbidden_prompt_artifacts(body) or _looks_malformed_prompt(body):
        body = ""
    if not body or len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", body)) < 8:
        body = "Historically grounded scholarly scene with clear subjects and setting"
    return ensure_brand_block(body)


def _validated_placement(scene: SentenceScene) -> str:
    lowered = scene.image_prompt.lower()
    has_quote = _scene_requires_quote_box(scene)
    has_map = any(token in lowered for token in ('map', 'geography', 'route', 'region', 'locations'))
    is_explainer = any(
        token in lowered
        for token in (
            'contrast',
            'definition',
            'doctrinal',
            'theological',
            'concept label',
            'split composition',
            'left-right',
            'vs',
        )
    )
    if has_quote:
        return 'center quote box'
    if has_map:
        return 'map label'
    if is_explainer:
        return 'side explainer box'
    return 'side label'


def _make_overlay_distinct(overlay: str) -> str:
    words = overlay.split()
    if len(words) < 5:
        words.append('Focus')
    else:
        words[-1] = 'Focus'
    return _title_overlay(' '.join(words[:5]))


def _has_named_figures_in_text(text: str) -> bool:
    candidates = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text or '')
    filtered = [item for item in candidates if item.lower() not in {'original sin', 'middle ages', 'early church'}]
    return bool(filtered)


def _strip_irrelevant_christology_symbolism(prompt: str, sentence: str, visual_concept: str) -> str:
    lowered = f"{prompt} {sentence} {visual_concept}".lower()
    is_christology_context = (
        ('divinity' in lowered or 'divine nature' in lowered or 'christology' in lowered or 'incarnation' in lowered)
        and ('humanity' in lowered or 'human nature' in lowered)
    )
    if is_christology_context:
        return prompt
    cleaned = re.sub(
        r'(?:^|[.;]\s*)Include a distinct blue symbolic sphere for divinity and a distinct red symbolic sphere for humanity, overlapping but not blending into purple, with subtle connector arrows where appropriate\.?',
        ' ',
        prompt,
        flags=re.IGNORECASE,
    )
    return ' '.join(cleaned.split()).strip(" .;")


def _sanitize_paragraph_prompts(prompts: list[str], style: str) -> list[str]:
    sanitized = [_sanitize_canva_image_prompt(str(prompt), style) for prompt in (prompts or []) if str(prompt).strip()]
    return sanitized[:3]


def _sanitize_overlay_elements(text_elements: list[dict[str, str]], paragraph_text: str) -> list[dict[str, str]]:
    items = text_elements or []
    if len(items) < 3:
        items = items + [
            {'type': 'keyword', 'content': 'Core Doctrine', 'timing_hint': 'beginning'},
            {'type': 'keyword', 'content': 'Historical Development', 'timing_hint': 'middle'},
            {'type': 'keyword', 'content': 'Comparative Insight', 'timing_hint': 'end'},
        ]
    out: list[dict[str, str]] = []
    quotes = _all_quotes(paragraph_text)
    seen: set[str] = set()
    for idx, item in enumerate(items[:12]):
        kind = str(item.get('type', 'keyword')).strip().lower()
        content = _clean_overlay_phrase(str(item.get('content', '')).strip())
        timing = str(item.get('timing_hint', 'middle')).strip().lower()
        if timing not in {'beginning', 'middle', 'end'}:
            timing = 'middle'
        if kind not in {'keyword', 'definition', 'quote', 'paraphrase_quote', 'personnel'}:
            kind = 'keyword'
        if kind == 'quote':
            if not _is_exact_quote(content, quotes):
                kind = 'keyword'
                content = _normalize_overlay_text(paragraph_text, 'Core Concept', has_quote=False)
        elif kind == 'personnel':
            content = ' '.join(content.split())
        elif kind == 'paraphrase_quote':
            content = ' '.join(content.split())
            content_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", content)
            if len(content_words) > 12:
                content = ' '.join(content_words[:12])
            if len(content_words) < 4:
                kind = 'keyword'
                content = _normalize_overlay_text(paragraph_text, content or 'Key Concept', has_quote=False)
        else:
            if _looks_narrative_overlay(content):
                content = _normalize_overlay_text(paragraph_text, content or 'Key Concept', has_quote=False)
            else:
                content = _normalize_overlay_text(content, content or 'Key Concept', has_quote=False)
        content_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", content)
        if not content_words:
            continue
        if kind in {'keyword', 'definition'} and len(content_words) > 5:
            content = ' '.join(content_words[:5])
        if kind in {'keyword', 'definition'} and len(content_words) < 2:
            content = f"{content_words[0]} Concept" if content_words else "Core Concept"
        if kind in {'keyword', 'definition'} and _looks_narrative_overlay(content):
            content = _normalize_overlay_text(paragraph_text, content or 'Key Concept', has_quote=False)
        key = f"{kind}:{content.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append({'type': kind, 'content': content, 'timing_hint': timing})
        if len(out) >= 12:
            break
    if len(out) < 3:
        fallback = [
            {'type': 'keyword', 'content': 'Core Doctrine', 'timing_hint': 'beginning'},
            {'type': 'definition', 'content': 'Historical Development', 'timing_hint': 'middle'},
            {'type': 'keyword', 'content': 'Comparative Insight', 'timing_hint': 'end'},
        ]
        for item in fallback:
            if len(out) >= 3:
                break
            out.append(item)
    return out[:12]


def _clean_overlay_phrase(text: str) -> str:
    cleaned = ' '.join((text or '').replace('*', ' ').split()).strip()
    cleaned = re.sub(r'^[\-"“”\'`]+|[\-"“”\'`]+$', '', cleaned).strip()
    return cleaned


def _all_quotes(text: str) -> list[str]:
    return [quote.strip() for quote in re.findall(r'["“](.*?)["”]', text or '') if quote.strip()]


def _is_exact_quote(content: str, quotes: list[str]) -> bool:
    target = ' '.join((content or '').split()).lower()
    for quote in quotes:
        if target == ' '.join(quote.split()).lower():
            return True
    return False


def _ensure_citation_payload(
    paragraph_text: str,
    bibliography_map: dict[str, str],
    payload: dict[str, object],
) -> dict[str, object]:
    citations = payload.get('citations') if isinstance(payload, dict) else []
    normalized = _sanitize_citations(citations if isinstance(citations, list) else [], paragraph_text)
    if normalized:
        return {'citations': normalized}

    matches = re.findall(r"\[([A-Za-z0-9]+)\]", paragraph_text or '')
    fallback: list[dict[str, str]] = []
    for marker in matches:
        marker_text = str(marker).strip()
        source = bibliography_map.get(marker_text, '').strip()
        if not source:
            # If the marker is alphanumeric (e.g., E6), also try the numeric part.
            numeric_part = re.sub(r"[^0-9]", "", marker_text)
            if numeric_part:
                source = bibliography_map.get(numeric_part, '').strip()
        fallback.append(
            {
                'citation_number': marker_text,
                'sentence_excerpt': _citation_excerpt(paragraph_text, marker_text),
                'citation_short': (
                    f"[{marker_text}] {_short_chicago_from_source(source) if source else 'Source unavailable'}."
                ).replace('..', '.'),
                'citation_full': (
                    _full_chicago_from_source(source)
                    if source
                    else f"[{marker_text}] Source unavailable in provided bibliography"
                ).replace('..', '.'),
            }
        )
    return {'citations': fallback}


def _scene_reference_lines(citation_payload: dict[str, object] | None) -> list[str]:
    citations = citation_payload.get('citations') if isinstance(citation_payload, dict) else []
    if not isinstance(citations, list):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for item in citations:
        if not isinstance(item, dict):
            continue
        full = str(item.get('citation_full', '')).strip()
        short = str(item.get('citation_short', '')).strip()
        candidate = full or short
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        refs.append(candidate)
    return refs


def _sanitize_citations(citations: list[dict[str, object]], paragraph_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in citations:
        if not isinstance(item, dict):
            continue
        number = str(item.get('citation_number', '')).strip()
        if not number:
            continue
        key = number.lower()
        if key in seen:
            continue
        seen.add(key)
        excerpt = str(item.get('sentence_excerpt', '')).strip() or _citation_excerpt(paragraph_text, number)
        short = str(item.get('citation_short', '')).strip() or f"[{number}] Source"
        full = str(item.get('citation_full', '')).strip() or f"[{number}] Source unavailable in provided bibliography"
        # Strip any markdown italics markers to keep overlay text plain.
        short = short.replace('*', '').strip()
        full = full.replace('*', '').strip()
        # Strip bracket citation markers like "[E6]" or "[1]" if present.
        short = re.sub(r'^\s*\[[^\]]+\]\s*', '', short).strip()
        full = re.sub(r'^\s*\[[^\]]+\]\s*', '', full).strip()
        # Normalize punctuation to match on-screen overlay expectations.
        if short and not short.endswith('.'):
            short = f"{short}."
        if full and not full.endswith('.'):
            full = f"{full}."
        out.append(
            {
                'citation_number': number,
                'sentence_excerpt': excerpt,
                'citation_short': short,
                'citation_full': full,
            }
        )
    return out


def _citation_excerpt(paragraph_text: str, marker: str) -> str:
    text = paragraph_text or ''
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        if f'[{marker}]' in sentence:
            return sentence.strip()[:180]
    return text[:180].strip()


def _short_chicago_from_source(source: str) -> str:
    if not source:
        return 'Source'

    # Supports the structured bibliography format from your input files.
    # Example fields:
    # - Author: Fisher, George Park, 1827-1909
    # - Title: History of Christian doctrine
    # - Year: 2021
    # - Page: 331
    author_line = re.search(r"^Author:\s*(.+)$", source, flags=re.MULTILINE)
    title_line = re.search(r"^Title:\s*(.+)$", source, flags=re.MULTILINE)
    year_line = re.search(r"^Year:\s*(\d{4})\b", source, flags=re.MULTILINE)
    page_line = re.search(r"^Page:\s*(.+)$", source, flags=re.MULTILINE)

    author_raw = (author_line.group(1).strip() if author_line else '').strip() or 'Author'
    # If author is "Last, First ..." extract the last name.
    if ',' in author_raw:
        author_last = author_raw.split(',', 1)[0].strip() or author_raw.strip()
    else:
        author_last = author_raw.split()[-1].strip() if author_raw.split() else author_raw.strip()

    title_raw = (title_line.group(1).strip() if title_line else '').strip()
    if not title_raw:
        # Fallback: try to pull something from the raw source.
        title_raw = source.split('\n', 1)[0].strip()

    title_short = ' '.join(title_raw.split()[:4]).strip()
    title_short = title_short or title_raw

    year = year_line.group(1).strip() if year_line else ''
    page = page_line.group(1).strip() if page_line else ''

    parts = [f"{author_last}, {title_short}"]
    if year:
        parts.append(f"({year})")
    if page:
        parts.append(f"{page}")
    return ', '.join([p for p in parts if p]).replace(', (', ' (').strip()


def _full_chicago_from_source(source: str) -> str:
    if not source:
        return 'Source unavailable in provided bibliography'

    author_line = re.search(r"^Author:\s*(.+)$", source, flags=re.MULTILINE)
    title_line = re.search(r"^Title:\s*(.+)$", source, flags=re.MULTILINE)
    year_line = re.search(r"^Year:\s*(\d{4})\b", source, flags=re.MULTILINE)
    publisher_line = re.search(r"^Publisher:\s*(.+)$", source, flags=re.MULTILINE)
    page_line = re.search(r"^Page:\s*(.+)$", source, flags=re.MULTILINE)

    author_raw = (author_line.group(1).strip() if author_line else '').strip()
    title_raw = (title_line.group(1).strip() if title_line else '').strip()
    year = year_line.group(1).strip() if year_line else ''
    publisher_raw = (publisher_line.group(1).strip() if publisher_line else '').strip()
    page = page_line.group(1).strip() if page_line else ''

    # Convert "Last, First ..." -> "First Last"
    if author_raw and ',' in author_raw:
        last, rest = author_raw.split(',', 1)
        # remove birth/death if present
        rest = rest.split(',', 1)[0].strip()
        author_full = f"{rest} {last}".strip()
    else:
        author_full = author_raw or 'Author'

    title_part = title_raw if title_raw else 'Title'
    pub_part = f"{publisher_raw}" if publisher_raw else ''

    # Keep formatting minimal if City is unknown.
    if pub_part and year:
        base = f"{author_full}, {title_part} ({pub_part}, {year})"
    elif year:
        base = f"{author_full}, {title_part} ({year})"
    else:
        base = f"{author_full}, {title_part}"

    if page:
        return f"{base}, {page}."
    return base + '.'


def _remove_forbidden_prompt_artifacts(text: str) -> str:
    cleaned = text or ''
    # Hard bans from client instruction for Column F.
    hard_remove_patterns = (
        r'\btext overlays?\b',
        r'\boverlay text\b',
        r'\blabel(?:s|ed|ing)?\b',
        r'\bcartouche(?:s)?\b',
        r'(?:^|[.;]\s*)A detailed(?: black-and-white)?\.?(?=$|[.;])',
        r'\barrow(?:s)?\b',
        r'\bconnector(?:s)?\b',
        r'\bconnecting lines?\b',
        r'\bcallouts?\b',
        r'\bspeech bubbles?\b',
        r'\bquestion bubbles?\b',
        r'\bdiagram with text\b',
        r'\bsymbolic diagram\b',
        r'\bflowchart\b',
        r'\binfographic\b',
        r'\bcall[- ]to[- ]action\b',
        r'\blike,\s*subscribe,\s*and\s*comment\b',
        r'\blike\b',
        r'\bsubscribe\b',
        r'\bcomment\b',
        r'\bthumbs?-?up\b',
        r'\bbell icon\b',
        r'\bui[- ]style\b',
        r'\bbutton(?:s)?\b',
        r'\bprompt(?:s)?\s+for\s+canva\b',
        r'\barrows_connections\s*[:=]?\s*(?:yes|no)\b',
        r"'[^']{1,40}'",
    )
    for pattern in hard_remove_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Remove awkward residual punctuation/spaces after token cleanup.
    cleaned = re.sub(r'\b(?:and|or)\s+(?:and|or)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bplus\s+icons?\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r'\s*[,;:]\s*[,;:]\s*', ', ', cleaned)
    cleaned = re.sub(r'\(\s*\)', '', cleaned)
    cleaned = re.sub(r'\bwith\s+subtle\b', 'with', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\binclude\s+a\s+short\s+in\s+a\s+subtle\s+(?:circle|box|cartouche)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bfor\s+and\s+while\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\btoward\s+a\s+of\b', 'toward', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r',\s*of\s+[^,.;]{1,120}(?=[,.;])', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bmind-\s*thought\b', 'mind', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*an contemplative\b', 'A contemplative', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*central of\b', 'Central scene of', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = re.sub(r'\s+,\s+', ', ', cleaned)
    return cleaned.strip(" .;,:")


def _has_forbidden_prompt_artifacts(text: str) -> bool:
    banned = (
        r'\btext overlays?\b',
        r'\boverlay text\b',
        r'\bcartouche(?:s)?\b',
        r'\blabel(?:s|ed|ing)?\b',
        r'\barrow(?:s)?\b',
        r'\bconnector(?:s)?\b',
        r'\bconnecting lines?\b',
        r'\bcall[- ]to[- ]action\b',
        r'\blike\b',
        r'\bsubscribe\b',
        r'\bcomment\b',
        r'\bthumbs?-?up\b',
        r'\bbell\b',
        r'\bspeech bubbles?\b',
        r'\bquestion\b',
        r'\bsymbolic diagram\b',
        r'\btoward\s+a\s+of\b',
        r'\bmind-\s*thought\b',
    )
    for pattern in banned:
        if re.search(pattern, text or '', flags=re.IGNORECASE):
            return True
    return False


def _looks_malformed_prompt(text: str) -> bool:
    value = (text or '').strip()
    if not value:
        return True
    malformed_patterns = (
        r'^\s*A featuring\b',
        r'^\s*A showing\b',
        r'^\s*Central of\b',
        r'^\s*of a\b',
        r'^\s*(?:A|An)\s+of\s+a\b',
        r'\ba subtle(?:\s+\w+){0,4}\s+within a\b',
        r'\ba subtle(?:\s+\w+){0,4}\s+integrated into the composition\b',
        r'\binclude\s+a\s+short\s+in\s+a\s+subtle\s+(?:circle|box|cartouche)\b',
        r'\bcartouche(?:s)?\b',
        r'\btoward\s+a\s+of\b',
        r',\s*of\s+[^,.;]{1,120}(?=[,.;])',
        r'\barrows_connections\s*[:=]?\s*(?:yes|no)\b',
        r'\bfor\s+and\s+while\b',
        r'\bmind-\s*thought\b',
        r'\bicons?\s+for\s+and\s+while\b',
        r'\bwhile\s+emphasizing\s+linked\s+to\b',
        r'\bemphasizing\s+linked\s+to\b',
        r'\bruling\s+out\s+symbolic\s+icons?\b',
        r"\bPurpose'\s+integrated in a\b",
        r'\bruling out and meanings\b',
    )
    for pattern in malformed_patterns:
        if re.search(pattern, value, flags=re.IGNORECASE):
            return True
    return False


def _looks_narrative_overlay(text: str) -> bool:
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or '')]
    if not words:
        return True
    narrative_markers = {
        'ever', 'wonder', 'have', 'you', 'lets', "let's", 'now', 'finally', 'did', 'does', 'is', 'are', 'was',
        'were', 'why', 'how', 'when', 'what', 'who', 'came', 'first', 'then',
    }
    if words[0] in BAD_OVERLAY_PREFIXES:
        return True
    marker_count = sum(1 for w in words if w in narrative_markers)
    return marker_count >= 2


def _scene_requires_quote_box(scene: SentenceScene) -> bool:
    quote_text = (scene.quote_full_text or '').strip()
    if not quote_text:
        return False
    overlay = (scene.on_screen_text or '').strip()
    lowered_prompt = (scene.image_prompt or '').lower()
    if _is_exact_quote(overlay, [quote_text]) or '"' in overlay or '“' in overlay:
        return True
    return any(token in lowered_prompt for token in ('quote', 'quoted phrase', 'verbatim'))
