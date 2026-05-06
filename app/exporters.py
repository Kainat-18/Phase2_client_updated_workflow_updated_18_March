from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.models import Storyboard
from app.prompts import BRAND_RENDERING_DEFAULT, ensure_brand_block

LEGACY_STYLE_PATTERN = r"A detailed black-and-white charcoal rendering.*?medium shot\.?"
VIBRANT_STYLE_PATTERN = r"A richly detailed illustration with fully vibrant saturated colours, executed in a classical painterly style with warm natural lighting, high contrast, and cinematic depth of field, medium shot\.?"
BRAND_BLOCK_WRAPPER_PATTERN = r"---BRAND RENDERING BLOCK(?: \(append verbatim to every image_prompt\))?---|---END BRAND RENDERING BLOCK---|---BRAND RENDERING BLOCK---|---BRAND RENDERING---"
PARTIAL_BRAND_FRAGMENT_PATTERN = r"---BRAND[^\n.]*|Rendered as a heavy, hand-worked charcoal.*$"


def export_storyboard(storyboard: Storyboard, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'storyboard.json').write_text(storyboard.model_dump_json(indent=2), encoding='utf-8')
    _export_csv(storyboard, out_dir / 'storyboard.csv')
    _export_canva_csv(storyboard, out_dir / 'canva_prompts.csv')
    _export_canva_simple_csv(storyboard, out_dir / 'canva_simple.csv')
    _export_final_manifest_json(storyboard, out_dir / 'final_scene_manifest.json')
    _export_final_manifest_csv(storyboard, out_dir / 'final_scene_manifest.csv')
    _export_book_timeline(storyboard, out_dir / 'book_timeline.json')
    _export_animator_packet(storyboard, out_dir / 'animator_instruction_packet.json')
    _export_phase2_paragraph_csv(storyboard, out_dir / 'phase2_paragraph_outputs.csv')
    _export_run_guide(storyboard, out_dir / 'RUN_THIS_NEXT.md')
    (out_dir / 'compliance_report.json').write_text(json.dumps(storyboard.compliance_report, indent=2), encoding='utf-8')
    _export_preview(storyboard, out_dir / 'storyboard_preview.html')


def _rows(storyboard: Storyboard):
    style_sentence = _normalize_style_sentence(storyboard.style_prompt or settings.default_style_prompt)
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                cleaned_prompt = _final_clean_image_prompt(scene.image_prompt, style_sentence)
                cleaned_paragraph_prompts = [_final_clean_image_prompt(p, style_sentence) for p in scene.paragraph_image_prompts]
                cleaned_overlay = make_overlay_content(scene.sentence, scene.visual_concept, scene.on_screen_text)
                cleaned_overlay_elements = _sanitize_overlay_elements_export(scene.overlay_text_elements, scene.sentence)
                cleaned_placement = _final_validate_placement(
                    prompt=cleaned_prompt,
                    placement=scene.placement,
                    paragraph_text=scene.sentence,
                )
                cleaned_text_box_style = _text_box_style_for_placement(cleaned_placement)
                cleaned_visual_elements = _derive_visual_elements(cleaned_prompt, cleaned_placement)
                yield {
                    'section': section.title,
                    'paragraph_index': paragraph.paragraph_index,
                    'scene_index': scene.sentence_index,
                    'alignment_id': scene.alignment_id,
                    'paragraph_text': scene.sentence,
                    'academic_paragraph': scene.academic_sentence,
                    'prompt_type': scene.visual_concept,
                    'scene_focus': scene.visual_concept,
                    'image_prompt': cleaned_prompt,
                    'column_f_canva_image_prompts': json.dumps(cleaned_paragraph_prompts, ensure_ascii=False),
                    'column_g_text_overlay_content': json.dumps(cleaned_overlay_elements, ensure_ascii=False),
                    'column_l_references_chicago': json.dumps(scene.chicago_citations, ensure_ascii=False),
                    'overlay_content': cleaned_overlay,
                    'placement': cleaned_placement,
                    'text_box_style': cleaned_text_box_style,
                    'arrows_connections': scene.arrows_connections,
                    'visual_elements': '; '.join(cleaned_visual_elements),
                    'key_visual_tokens': '; '.join(scene.key_visual_tokens),
                    'compositional_layers': '; '.join(scene.compositional_layers),
                    'references': '; '.join(scene.references),
                    'image_path': scene.image_path or '',
                }


def _export_csv(storyboard: Storyboard, path: Path) -> None:
    rows = list(_rows(storyboard))
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['section'])
        writer.writeheader()
        writer.writerows(rows)


def _export_phase2_paragraph_csv(storyboard: Storyboard, path: Path) -> None:
    rows = []
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            if not paragraph.scenes:
                continue
            first = paragraph.scenes[0]
            rows.append(
                {
                    'Section': section.title,
                    'ParagraphIndex': paragraph.paragraph_index,
                    'ColumnF_CanvaImagePrompts': json.dumps(first.paragraph_image_prompts, ensure_ascii=False),
                    'ColumnG_TextOverlayContent': json.dumps(first.overlay_text_elements, ensure_ascii=False),
                    'ColumnL_ReferencesChicago': json.dumps(first.chicago_citations, ensure_ascii=False),
                }
            )
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'Section',
                'ParagraphIndex',
                'ColumnF_CanvaImagePrompts',
                'ColumnG_TextOverlayContent',
                'ColumnL_ReferencesChicago',
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _export_canva_csv(storyboard: Storyboard, path: Path) -> None:
    rows = []
    for row in _rows(storyboard):
        rows.append({
            'SceneID': row['alignment_id'],
            'Section': row['section'],
            'PromptType': row['prompt_type'],
            'ParagraphIndex': row['paragraph_index'],
            # Client wants Column F as the actual Canva prompt to copy/paste.
            # Keep it scene-specific (not the paragraph-level list) to avoid duplicates.
            'ColumnF_CanvaImagePrompts': row['image_prompt'],
            'ColumnG_TextOverlayContent': row['column_g_text_overlay_content'],
            'ColumnL_ReferencesChicago': row['column_l_references_chicago'],
            'OverlayContent': row['overlay_content'],
            'Placement': row['placement'],
            'Style': row['text_box_style'],
            'Visuals': row['visual_elements'],
            'VisualElements': row['visual_elements'],
            'References': row['references'],
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'SceneID',
                'Section',
                'PromptType',
                'ParagraphIndex',
                'ColumnF_CanvaImagePrompts',
                'ColumnG_TextOverlayContent',
                'ColumnL_ReferencesChicago',
                'OverlayContent',
                'Placement',
                'Style',
                'Visuals',
                'VisualElements',
                'References',
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _export_canva_simple_csv(storyboard: Storyboard, path: Path) -> None:
    rows = []
    style_sentence = _normalize_style_sentence(storyboard.style_prompt or settings.default_style_prompt)
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                cleaned_prompt = _final_clean_image_prompt(scene.image_prompt, style_sentence)
                overlay_str = " | ".join(
                    str(item.get("content", "")).strip()
                    for item in scene.overlay_text_elements
                    if isinstance(item, dict)
                    and str(item.get("content", "")).strip()
                )
                citation_str = " | ".join(
                    str(item.get("citation_short", "")).strip()
                    for item in scene.chicago_citations
                    if isinstance(item, dict)
                    and str(item.get("citation_short", "")).strip()
                )
                rows.append({
                    "Scene_ID": scene.alignment_id,
                    "Image_Prompt": cleaned_prompt,
                    "Overlay_Text": overlay_str,
                    "Citations": citation_str,
                })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Scene_ID", "Image_Prompt", "Overlay_Text", "Citations"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _export_final_manifest_json(storyboard: Storyboard, path: Path) -> None:
    scenes = []
    for row in _rows(storyboard):
        scenes.append({
            'scene_id': row['alignment_id'],
            'section': row['section'],
            'paragraph_index': row['paragraph_index'],
            'paragraph_text': row['paragraph_text'],
            'prompt_type': row['prompt_type'],
            'scene_focus': row['scene_focus'],
            'image_prompt': row['image_prompt'],
            'overlay_content': row['overlay_content'],
            'column_f_canva_image_prompts': json.loads(row['column_f_canva_image_prompts']) if row['column_f_canva_image_prompts'] else [],
            'column_g_text_overlay_content': json.loads(row['column_g_text_overlay_content']) if row['column_g_text_overlay_content'] else [],
            'column_l_references_chicago': json.loads(row['column_l_references_chicago']) if row['column_l_references_chicago'] else [],
            'placement': row['placement'],
            'text_box_style': row['text_box_style'],
            'visual_elements': [v for v in row['visual_elements'].split('; ') if v],
            'references': [v for v in row['references'].split('; ') if v],
            'resolution': '16:9',
            'book_layout': {
                'page_border': True,
                'logo_position': 'lower-right TheoEngage logo',
                'section': row['section'],
            },
            'animation': {
                'scene_duration': f"{scene_duration_from_row(row):.1f} seconds",
                'transition': 'zoom in -> zoom out',
                'sketch_reveal': True,
            },
        })
    payload = {'title': storyboard.title, 'brand': storyboard.brand_name, 'workflow': 'paragraph_to_canva_prompts', 'total_scenes': len(scenes), 'scenes': scenes}
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _export_final_manifest_csv(storyboard: Storyboard, path: Path) -> None:
    rows = []
    for row in _rows(storyboard):
        rows.append({
            'SceneID': row['alignment_id'],
            'Section': row['section'],
            'PromptType': row['prompt_type'],
            'ParagraphIndex': row['paragraph_index'],
            'ParagraphText': row['paragraph_text'],
            'Prompt': row['image_prompt'],
            'ColumnF_CanvaImagePrompts': row['column_f_canva_image_prompts'],
            'ColumnG_TextOverlayContent': row['column_g_text_overlay_content'],
            'ColumnL_ReferencesChicago': row['column_l_references_chicago'],
            'OverlayContent': row['overlay_content'],
            'Placement': row['placement'],
            'Style': row['text_box_style'],
            'Visuals': row['visual_elements'],
            'VisualElements': row['visual_elements'],
            'References': row['references'],
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['SceneID','Section','PromptType','ParagraphIndex','ParagraphText','Prompt','ColumnF_CanvaImagePrompts','ColumnG_TextOverlayContent','ColumnL_ReferencesChicago','OverlayContent','Placement','Style','Visuals','VisualElements','References'])
        writer.writeheader()
        writer.writerows(rows)


def _export_book_timeline(storyboard: Storyboard, path: Path) -> None:
    payload = {
        'episode_title': storyboard.title,
        'brand': storyboard.brand_name,
        'workflow_mode': 'Canva prompts only',
        'opening_sequence': [
            {'event': 'closed_book_cover', 'notes': 'Closed book with episode title and TheoEngage logo on cover.'},
            {'event': 'book_open_title_page', 'notes': 'Book opens to title page with heading and introduction.'},
        ],
        'sections': [],
        'closing_sequence': [{'event': 'credits'}, {'event': 'logo_end_card'}, {'event': 'animated_cta'}],
    }
    for section in storyboard.sections:
        events = []
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                events.append({
                    'event': 'canva_image_scene',
                    'alignment_id': scene.alignment_id,
                    'paragraph_index': paragraph.paragraph_index,
                    'duration_sec': 2.8,
                    'camera': 'zoom in then zoom out',
                    'on_screen_text': scene.on_screen_text,
                    'placement': scene.placement,
                })
        payload['sections'].append({'title': section.title, 'events': events, 'section_close': {'event': 'full_page_reveal', 'camera': 'zoom out'}, 'next_transition': 'page_flip'})
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _export_preview(storyboard: Storyboard, path: Path) -> None:
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape(['html', 'xml']))
    template = env.get_template('storyboard_preview.html.j2')
    html = template.render(storyboard=storyboard)
    path.write_text(html, encoding='utf-8')


def _export_animator_packet(storyboard: Storyboard, path: Path) -> None:
    packet = {'title': storyboard.title, 'brand': storyboard.brand_name, 'workflow': 'paragraph prompt generation for Canva', 'paragraph_templates': []}
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            para_block = {'section': section.title, 'paragraph_index': paragraph.paragraph_index, 'prompt_count': len(paragraph.scenes), 'scenes': []}
            for scene in paragraph.scenes:
                para_block['scenes'].append({
                    'alignment_id': scene.alignment_id,
                    'paragraph_text': scene.sentence,
                    'scene_focus': scene.visual_concept,
                    'prompt': scene.image_prompt,
                    'overlay_content': scene.on_screen_text,
                    'placement': scene.placement,
                    'text_box_style': scene.text_box_style,
                    'references': scene.references,
                })
            packet['paragraph_templates'].append(para_block)
    path.write_text(json.dumps(packet, indent=2), encoding='utf-8')


def _export_run_guide(storyboard: Storyboard, path: Path) -> None:
    content = f'''# RUN THIS NEXT

## Workflow
1. Open `final_scene_manifest.csv`.
2. For each row, copy the `Prompt` into Canva AI Image Generator.
3. Generate an image in 16:9.
4. Add optional text using `OverlayContent`.
5. Export images as `ALN-XXXX.png`.
6. Run:
   - `python main.py attach-canva-images --storyboard storyboard.json --images-dir <folder>`
   - `python main.py make-video --storyboard storyboard.json`

## Project title
{storyboard.title}
'''
    path.write_text(content, encoding='utf-8')


def make_overlay_content(paragraph_text: str, prompt_type: str, existing_overlay: str = "") -> str:
    base_text = existing_overlay or paragraph_text
    text = clean_markdown(base_text).strip()
    if not text:
        return ''

    lowered = text.lower()
    quote = extract_short_quote(paragraph_text or existing_overlay)
    candidate = ''
    if quote and ('quote' in prompt_type.lower() or '"' in text or '“' in text or '”' in text):
        candidate = quote

    cleaned = strip_lead_ins(text)
    if not candidate:
        meaning_label = _semantic_overlay_label(text) or _semantic_overlay_label(cleaned)
        if meaning_label:
            candidate = meaning_label

    transition_markers = ('transition:', "let's", 'now', 'finally', 'wrapping it up', 'fast-forward', 'stick around')
    if not candidate and any(marker in lowered for marker in transition_markers):
        candidate = summarize_label(cleaned, max_words=5)

    if not candidate:
        candidate = summarize_label(cleaned, max_words=6)
    normalized = _normalize_overlay_content(candidate, cleaned or text)
    if _contains_cta_words(normalized):
        return 'Core Concept'
    return normalized


def summarize_label(text: str, max_words: int = 6) -> str:
    cleaned = strip_lead_ins(text)
    words = [w for w in cleaned.split() if w and w != '...']
    if not words:
        return ''
    short = ' '.join(words[:max_words]).strip(" ,.-:")
    short = _trim_tail_stopwords(short)
    return _title_case_label(short)


def _normalize_overlay_content(candidate: str, fallback_text: str) -> str:
    words = _overlay_words(candidate)[:5]
    if len(words) < 2:
        fallback_words = _overlay_words(fallback_text)[:5]
        if len(fallback_words) >= 2:
            words = fallback_words[:5]
        elif len(fallback_words) == 1:
            words = [fallback_words[0], 'Concept']
        elif len(words) == 1:
            words = [words[0], 'Concept']
        else:
            return ''
    if len(words) > 5:
        words = words[:5]
    normalized = _title_case_label(' '.join(words))
    if normalized.lower().startswith('nothing '):
        return 'Core Concept'
    if _contains_cta_words(normalized):
        return 'Core Concept'
    return normalized


def _overlay_words(text: str) -> list[str]:
    stopwords = {
        'the', 'a', 'an', 'in', 'on', 'at', 'to', 'of', 'for', 'with', 'by', 'from', 'and', 'or',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'this', 'that', 'these', 'those', 'it',
        'as', 'into', 'about', 'through', 'between', 'across', 'around', 'now', 'then',
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", clean_markdown(text))
    meaningful = [t for t in tokens if t.lower() not in stopwords]
    return meaningful


def strip_lead_ins(text: str) -> str:
    cleaned = clean_markdown(text)
    cleaned = re.sub(
        r"^(hook:\s*|transition:\s*|let's\s+start(?:\s+with)?\s+|let's\s+turn\s+to\s+|let's\s+turn\s+|let's\s+see\s+how\s+|now,\s*|next,\s*|finally,\s*|fast-forward(?:\s+to)?[:,]?\s*|wrapping it up[:,]?\s*|stick around(?:\s+as)?\s+|to the middle ages,\s*where\s+|at the roots in the\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def clean_markdown(text: str) -> str:
    cleaned = (text or '').replace('**', '').replace('*', '').replace('`', ' ')
    cleaned = cleaned.replace('...', ' ')
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()


def extract_short_quote(text: str) -> str:
    match = re.search(r'["“](.*?)["”]', text)
    if not match:
        return ''
    quote = clean_markdown(match.group(1))
    if not quote:
        return ''
    return summarize_label(quote, max_words=8)


def _semantic_overlay_label(text: str) -> str:
    lowered = text.lower()
    patterns = [
        (all(k in lowered for k in ['inherited', 'sin', 'adam']), 'Inherited Sin from Adam'),
        ('roots' in lowered and 'church' in lowered, 'Roots in the Early Church'),
        ('augustine' in lowered and any(k in lowered for k in ['spread', 'took hold', 'hold']), "Augustine's Ideas Spread"),
        ('middle ages' in lowered, 'The Middle Ages Organize Doctrine'),
        ('what this history' in lowered or 'what does this history' in lowered, 'What This History Reveals'),
        ('east' in lowered and 'west' in lowered and 'theolog' in lowered, 'East-West Theological Divide'),
        ('peter lombard' in lowered, 'Peter Lombard on Propagation'),
        ('original sin' in lowered and 'salvation' in lowered, 'Original Sin and Salvation'),
        ('fences and bridges' in lowered, 'Fences and Bridges'),
        ('just imitation' in lowered, 'Just Imitation'),
        ('from nothing' in lowered, 'From Nothing'),
    ]
    for match, label in patterns:
        if match:
            return label
    return ''


def _trim_tail_stopwords(text: str) -> str:
    stop_tail = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'of', 'for', 'with', 'by', 'from', 'and', 'or', 'where'}
    parts = text.split()
    while parts and parts[-1].lower() in stop_tail:
        parts.pop()
    return ' '.join(parts)


def _title_case_label(text: str) -> str:
    parts = text.replace("’", "'").split()
    normalized = []
    for part in parts:
        if "'" in part:
            left, right = part.split("'", 1)
            normalized.append(f"{left[:1].upper()}{left[1:].lower()}'{right[:1].lower()}{right[1:].lower()}")
        else:
            normalized.append(part[:1].upper() + part[1:].lower())
    return ' '.join(normalized)


def _contains_cta_words(text: str) -> bool:
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or '')}
    return bool(words & {'like', 'subscribe', 'comment'})


def _normalize_style_sentence(style_prompt: str) -> str:
    style_clean = ' '.join((style_prompt or '').split()).strip().rstrip('.')
    if style_clean and (
        re.search(LEGACY_STYLE_PATTERN, style_clean, flags=re.IGNORECASE)
        or re.search(VIBRANT_STYLE_PATTERN, style_clean, flags=re.IGNORECASE)
    ):
        style_clean = ' '.join((settings.default_style_prompt or '').split()).strip().rstrip('.')
    if not style_clean:
        style_clean = ' '.join(BRAND_RENDERING_DEFAULT.split()).strip().rstrip('.')
    return style_clean


def _final_clean_image_prompt(prompt: str, style_sentence: str) -> str:
    value = ' '.join((prompt or '').split()).strip()
    value = _ensure_style_once(value, style_sentence)
    body = value.replace(style_sentence, ' ').strip(" .;")
    body = re.sub(VIBRANT_STYLE_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = re.sub(BRAND_BLOCK_WRAPPER_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = re.sub(PARTIAL_BRAND_FRAGMENT_PATTERN, ' ', body, flags=re.IGNORECASE)
    body = _strip_export_artifacts(body)
    body = re.sub(r'(?:\bA detailed(?: black-and-white)?(?: charcoal)?\.?)\s*$', '', body, flags=re.IGNORECASE)
    body = re.sub(r'(?:\b(?:and|yet|the)\.?)\s*$', '', body, flags=re.IGNORECASE)
    if _looks_broken_export_prompt(body):
        body = "Historically grounded scholarly scene with clear subjects and setting"
    if len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", body)) < 8:
        body = "Historically grounded scholarly scene with clear subjects and setting"
    return ensure_brand_block(body)


def _ensure_style_once(prompt: str, style_sentence: str) -> str:
    body = re.sub(LEGACY_STYLE_PATTERN, " ", prompt or '', flags=re.IGNORECASE)
    body = re.sub(VIBRANT_STYLE_PATTERN, " ", body, flags=re.IGNORECASE)
    body = re.sub(BRAND_BLOCK_WRAPPER_PATTERN, " ", body, flags=re.IGNORECASE)
    body = re.sub(PARTIAL_BRAND_FRAGMENT_PATTERN, " ", body, flags=re.IGNORECASE)
    body = re.sub(re.escape(style_sentence), " ", body, flags=re.IGNORECASE)
    body = ' '.join(body.split()).strip(" .;")
    if not body:
        return style_sentence
    return ensure_brand_block(body)


def _strip_export_artifacts(text: str) -> str:
    cleaned = text or ''
    patterns = (
        r'\bcartouche(?:s)?\b',
        r'\barrows_connections\s*[:=]?\s*(?:yes|no)\b',
        r'\boverlay text\b',
        r'\btext overlays?\b',
        r'(?:^|[.;]\s*)A detailed(?: black-and-white)?\.?(?=$|[.;])',
        r'\bdiagram\b',
        r'\btimeline diagram\b',
        r'\btoward\s+a\s+of\b',
        r',\s*of\s+[^,.;]{1,120}(?=[,.;]|$)',
        r'\bmind-\s*thought\b',
        r'\bfor\s+and\s+while\b',
        r';\s*incorporate\s+subtle\s+text\s+and\s+integrated\s+as\s*;?',
        r'\bintegrated\s+with\s+circular\s+for\s+and\s*;?',
        r'\bwith\s+for\s+and\s*;?',
        r'\bcentral\s+divider\s+with\s+and\b',
        r"\band\s+s\s+Choice,?\s*Grace\s+for\s+All'?\s*;?",
        r'\bshared\s+banner\s*;?',
        r'\bintegrated\s+in\s+a\s+subtle\b',
        r'\bwith\s+and\b',
        r'\binclude\s+a\s+short\s+in\s+a\s+subtle\s+(?:circle|box|cartouche)\b',
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*an contemplative\b', 'A contemplative', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*central of\b', 'Central scene of', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*showing\b', 'A scene showing', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*depicting\b', 'A scene depicting', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*of\s+([a-z])', r'A scene of \1', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = re.sub(r'\s*;\s*', '; ', cleaned)
    cleaned = re.sub(r';\s*[.,]', '.', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip(" .;,:")


def _looks_broken_export_prompt(text: str) -> bool:
    value = (text or '').strip()
    if not value:
        return True
    broken_patterns = (
        r'^\s*A featuring\b',
        r'^\s*A showing\b',
        r'^\s*showing\b',
        r'^\s*depicting\b',
        r'^\s*of\s+[A-Za-z]',
        r'^\s*of a\b',
        r'^\s*(?:A|An)\s+of\s+a\b',
        r'\btoward\s+a\s+of\b',
        r',\s*of\s+[^,.;]{1,120}(?=[,.;]|$)',
        r'\bwith\s+and\b',
        r'\bcentral\s+divider\s+with\s+and\b',
        r'\bintegrated\s+in\s+a\s+subtle\b',
        r'\bintegrated\s+as\b',
        r"\band\s+s\s+Choice,?\s*Grace\s+for\s+All'?",
        r'\bshared\s+banner\s*;',
        r'\bmind-\s*thought\b',
        r'\bcartouche(?:s)?\b',
        r'\barrows_connections\b',
        r'\btimeline diagram\b',
        r'\binclude\s+a\s+short\s+in\s+a\s+subtle\s+(?:circle|box|cartouche)\b',
    )
    return any(re.search(p, value, flags=re.IGNORECASE) for p in broken_patterns)


def _final_validate_placement(prompt: str, placement: str, paragraph_text: str) -> str:
    p = (prompt or '').lower()
    original = (placement or '').strip().lower()
    has_quote = bool(re.search(r'["“][^"”]+["”]', paragraph_text or ''))
    map_like = any(t in p for t in (' map ', ' map,', ' map.', ' geography', ' route', ' region', ' location'))
    explainer_like = any(t in p for t in ('contrast', 'doctrinal', 'theological', 'comparison', 'split composition', ' vs '))
    if has_quote:
        return 'center quote box'
    if map_like:
        return 'map label'
    if explainer_like:
        return 'side explainer box'
    if original in {'side label', 'side explainer box', 'map label', 'center quote box'}:
        return original if original != 'map label' else 'side label'
    return 'side label'


def _text_box_style_for_placement(placement: str) -> str:
    if placement == 'center quote box':
        return 'centered elegant quote box (serif, large)'
    if placement == 'map label':
        return 'map label anchors near locations'
    if placement == 'side explainer box':
        return 'mini side-definition box with connector arrows'
    return 'contextual side label box'


def _derive_visual_elements(prompt: str, placement: str) -> list[str]:
    p = (prompt or '').lower()
    elements: list[str] = []
    if any(t in p for t in ('scholar', 'figure', 'portrait', 'council', 'theologian', 'fathers')):
        elements.append('historical figures')
    if 'split composition' in p or 'left side' in p or 'right side' in p:
        elements.append('split composition')
    if any(t in p for t in ('doctrinal', 'theological', 'contrast', 'comparison')):
        elements.append('doctrinal contrast')
    if any(t in p for t in ('architecture', 'cathedral', 'church', 'hall', 'library')):
        elements.append('architecture')
    if placement == 'map label':
        elements.append('map')
    if placement == 'center quote box':
        elements.append('quote treatment')
    if not elements:
        elements.append('contextual illustration')
    deduped: list[str] = []
    for item in elements:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _sanitize_overlay_elements_export(text_elements: list[dict[str, str]], fallback_text: str) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    items = text_elements or []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get('type', 'keyword')).strip().lower()
        if kind not in {'keyword', 'definition', 'quote', 'paraphrase_quote', 'personnel'}:
            kind = 'keyword'
        timing = str(item.get('timing_hint', 'middle')).strip().lower()
        if timing not in {'beginning', 'middle', 'end'}:
            timing = 'middle'
        raw_content = str(item.get('content', '')).strip()
        if kind in {'personnel', 'paraphrase_quote'}:
            content = ' '.join(raw_content.split())
        else:
            content = _normalize_overlay_content(raw_content, fallback_text)
        if not content:
            continue
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", content)
        if kind in {'keyword', 'definition'}:
            if len(words) > 6:
                content = _title_case_label(' '.join(words[:6]))
            if len(words) < 2:
                content = 'Core Concept'
        cleaned.append({'type': kind, 'content': content, 'timing_hint': timing})
    if len(cleaned) < 3:
        cleaned.extend(
            [
                {'type': 'keyword', 'content': 'Core Concept', 'timing_hint': 'beginning'},
                {'type': 'definition', 'content': 'Historical Context', 'timing_hint': 'middle'},
                {'type': 'keyword', 'content': 'Key Insight', 'timing_hint': 'end'},
            ][: 3 - len(cleaned)]
        )
    return cleaned[:12]


def scene_duration_from_row(row: dict[str, str]) -> float:
    # preview manifests currently do not store scene_duration directly in row payload;
    # transition rows are identified via prompt type.
    prompt_type = (row.get('prompt_type') or '').lower()
    if prompt_type == 'contextual scholarly illustration':
        return 2.0
    return 2.8
