from __future__ import annotations

import re

from app.config import settings


TYPOGRAPHY_BLOCK = {
    'quote_font': 'Georgia, Times New Roman',
    'quote_size': '28-32pt',
    'name_title_font': 'Helvetica, Arial',
    'name_title_size': '18-22pt',
    'definition_font': 'Helvetica, Open Sans',
    'definition_size': '16-18pt',
    'subheading_font': 'Montserrat, Lato',
    'subheading_size': '24-28pt',
}

STOPWORDS = {
    'the', 'and', 'that', 'with', 'from', 'this', 'were', 'have', 'into', 'their', 'about',
    'which', 'will', 'would', 'could', 'should', 'than', 'then', 'when', 'what', 'where',
    'while', 'your', 'they', 'them', 'over', 'under', 'across', 'after', 'before', 'being',
    'been', 'also', 'very', 'more', 'most', 'some', 'such', 'only', 'just', 'same', 'each',
    'ever', 'wonder', 'why', 'how', 'what', 'does', 'did', 'into', 'onto', 'here', 'there',
}


def build_policy_bundle(
    section_title: str,
    section_theme: str,
    youtube_sentence: str,
    academic_sentence: str,
) -> dict[str, object]:
    visual_elements = _detect_visual_elements(youtube_sentence, academic_sentence)
    placement = _placement_for_elements(visual_elements)
    references = _reference_notes(section_title, youtube_sentence, academic_sentence)
    quote_text = _extract_quote(youtube_sentence)
    key_tokens = _key_visual_tokens(youtube_sentence)
    text_overlay = quote_text or _overlay_text(youtube_sentence, visual_elements, key_tokens)
    compositional_layers = _compositional_layers(youtube_sentence, key_tokens)
    text_box_style = _text_box_style(visual_elements, youtube_sentence)
    map_required = 'map with labeled movement arrow' in visual_elements
    scene_checklist = _scene_checklist(visual_elements, map_required, quote_text)
    motion_guidance = (
        'Keep facial/hand motion minimal; prefer gentle whole-body orientation shifts. '
        'Avoid exaggerated body-part animation.'
    )
    return {
        'section_theme': section_theme,
        'visual_elements': visual_elements,
        'placement': placement,
        'text_overlay': text_overlay,
        'quote_full_text': quote_text or '',
        'key_visual_tokens': key_tokens,
        'compositional_layers': compositional_layers,
        'text_box_style': text_box_style,
        'map_required': map_required,
        'motion_guidance': motion_guidance,
        'scene_checklist': scene_checklist,
        'typography_block': TYPOGRAPHY_BLOCK,
        'references': references,
    }


def compose_image_prompt(base_image_prompt: str, style_prompt: str, policy_bundle: dict[str, object]) -> str:
    base = base_image_prompt.strip()
    visual_elements = ', '.join(policy_bundle['visual_elements']) if policy_bundle['visual_elements'] else 'symbolic scene'
    references = ' | '.join(policy_bundle['references'])
    section_theme = str(policy_bundle['section_theme'])
    key_tokens = ', '.join(policy_bundle['key_visual_tokens']) or 'core concepts'
    layer_notes = ' | '.join(policy_bundle['compositional_layers'])
    text_box_style = str(policy_bundle['text_box_style'])
    map_rule = 'Use map markers and gentle arrows for movement.' if policy_bundle['map_required'] else 'No map is required unless geography appears.'
    policy_text = (
        f"Section visual framework: {section_theme}. "
        f"Visual elements: {visual_elements}. Key visual tokens: {key_tokens}. "
        f"Layering plan: {layer_notes}. "
        f"Book-page animation intent: sketch-reveal on zoom-in, zoom-out to full page at section close, subtle border and lower-right {settings.brand_name} logo (globe-cross, no shadow). "
        "Use concise scholarly labels only where needed; keep full text only for direct quotes. "
        f"Text box style: {text_box_style}. "
        f"{map_rule} "
        "For theology/anthropology themes, favor universal symbolic compositions over specific historical portraits unless a named council figure is explicitly discussed. "
        "Preserve blue and red symbolic spheres as distinct yet overlapping where divine/human natures are discussed. "
        "Maintain calm transitions with zoom only, no aggressive effects. "
        f"Footnote references for animator: {references}."
    )
    merged = f"{base} {policy_text}".strip()
    if style_prompt not in merged:
        merged = f"{merged} {style_prompt}".strip()
    return merged


def _detect_visual_elements(youtube_sentence: str, academic_sentence: str) -> list[str]:
    text = f"{youtube_sentence} {academic_sentence}"
    lowered = text.lower()
    elements: list[str] = []
    if '"' in text or '“' in text or any(w in lowered for w in ['said', 'wrote', 'declared', 'quote']):
        elements.append('full quote callout')
    if any(w in lowered for w in ['from', 'to', 'journey', 'travel', 'route', 'city', 'region', 'empire']):
        elements.append('map with labeled movement arrow')
    if any(w in lowered for w in ['council', 'year', 'century', 'timeline']):
        elements.append('timeline marker')
    if any(w in lowered for w in ['defined as', 'means', 'nature', 'doctrine', 'concept']):
        elements.append('definition side box with connector')
    if any(w in lowered for w in ['humanity', 'human nature', 'anthropology', 'human person']):
        elements.append('universal anthropology tableau')
    if any(w in lowered for w in ['divine', 'human']):
        elements.append('distinct blue and red symbolic spheres (no purple merge)')

    names = re.findall(r"\b[A-Z][a-z]{2,}\b", youtube_sentence)
    if names:
        elements.append('name labels near relevant figures/objects')
    if not elements:
        elements.append('contextual symbolic illustration')
    return list(dict.fromkeys(elements))


def _placement_for_elements(elements: list[str]) -> str:
    if 'full quote callout' in elements:
        return 'center quote box'
    if 'map with labeled movement arrow' in elements:
        return 'map label'
    if 'definition side box with connector' in elements:
        return 'side explainer box'
    return 'side label'


def _overlay_text(sentence: str, elements: list[str], key_tokens: list[str]) -> str:
    if 'map with labeled movement arrow' in elements:
        locations = re.findall(r"\b(?:from|to|in)\s+([A-Z][a-zA-Z]+)", sentence)
        if len(locations) >= 2:
            return f"{locations[0]} to {locations[1]} movement"
        if len(locations) == 1:
            return f"Map focus: {locations[0]}"
        return "Regional context map"

    if 'definition side box with connector' in elements and key_tokens:
        return f"Key doctrine: {key_tokens[0]}"

    if key_tokens:
        concise = ", ".join(key_tokens[:4])
        if len(concise) <= 72:
            return concise

    cleaned = sentence.strip()
    if len(cleaned) <= 72:
        return cleaned
    trimmed = cleaned[:72].rsplit(" ", 1)[0].strip()
    return f"{trimmed}..."


def _extract_quote(sentence: str) -> str:
    matches = re.findall(r"[\"“](.*?)[\"”]", sentence)
    if matches:
        return matches[0].strip()
    return ''


def _key_visual_tokens(sentence: str) -> list[str]:
    named_chunks = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", sentence)
    named_tokens: list[str] = []
    for chunk in named_chunks:
        cleaned = chunk.strip()
        lowered = cleaned.lower()
        if not cleaned:
            continue
        if lowered in STOPWORDS or lowered in {'the', 'a', 'an'}:
            continue
        if lowered.startswith('the '):
            cleaned = cleaned[4:].strip()
            lowered = cleaned.lower()
        if cleaned and lowered not in STOPWORDS:
            named_tokens.append(cleaned)
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", sentence)
    filtered_words = [w for w in words if w.lower() not in STOPWORDS and w.lower() not in {'the', 'a', 'an'}]
    merged = list(dict.fromkeys(named_tokens + filtered_words))
    return merged[:10]


def _compositional_layers(sentence: str, key_tokens: list[str]) -> list[str]:
    layers: list[str] = []
    if key_tokens:
        lead = ', '.join(key_tokens[:3])
        layers.append(f'foreground symbols for: {lead}')
    if re.search(r"\b\d{3,4}\b", sentence):
        layers.append('timeline/date marker with click SFX cue')
    if any(word in sentence.lower() for word in ['from', 'to', 'journey', 'travel', 'route', 'city', 'region']):
        layers.append('midground movement path on map with dotted arrow')
    layers.append('background scholarly texture with subtle lighting depth')
    return layers


def _text_box_style(elements: list[str], sentence: str) -> str:
    if 'full quote callout' in elements:
        return 'centered elegant quote box (serif, large)'
    if 'definition side box with connector' in elements:
        return 'mini side-definition box with connector arrows'
    if re.search(r"\b\d{3,4}\b", sentence):
        return 'date-highlight capsule with subtle click cue'
    if 'map with labeled movement arrow' in elements:
        return 'map label anchors near locations'
    return 'contextual side label box'


def _scene_checklist(elements: list[str], map_required: bool, quote_text: str) -> list[str]:
    checklist = [
        'Sentence visual must include at least one foreground symbolic element.',
        'Use compositional layering (foreground, midground/background), avoid static full-frame hold.',
        'Transition should remain zoom in/out with sketch reveal intent only.',
        'Add concise explanatory text without copying narration verbatim.',
    ]
    if map_required:
        checklist.append('Map with clear labeled points and gentle directional arrow is mandatory.')
    if quote_text:
        checklist.append('Display full quote text in centered serif quote box.')
    return checklist


def _reference_notes(section_title: str, youtube_sentence: str, academic_sentence: str) -> list[str]:
    refs = [
        'Use Chicago-style citations only.',
    ]
    if '"' in youtube_sentence or '“' in youtube_sentence:
        refs.append('Primary source citation required for full quote.')
    if re.search(r"\b\d{3,4}\b", youtube_sentence):
        refs.append('Chronology citation required for mentioned year/date.')
    refs.append('Add final scholarly source footnote in edit timeline.')
    return refs
