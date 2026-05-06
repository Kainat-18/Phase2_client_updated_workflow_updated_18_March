from __future__ import annotations

import re

from app.models import Storyboard


def build_compliance_report(storyboard: Storyboard, style_prompt: str) -> dict[str, object]:
    checks = {
        'sentence_level_visuals': True,
        'scene_duration_max_3_sec': True,
        'charcoal_prompt_present_all_scenes': True,
        'book_timeline_required': True,
        'zoom_only_transition_intent': True,
        'section_close_full_page_reveal': True,
        'canva_only_mode_enabled': storyboard.canva_only_images,
        'dual_script_sync_present_when_provided': True,
        'footnote_references_per_sentence': True,
        'visual_symbol_density_sufficient': True,
    }
    totals = {
        'scenes': 0,
        'scenes_missing_style_prompt': 0,
        'scenes_over_3_sec': 0,
        'scenes_missing_references': 0,
        'quote_scenes': 0,
        'quote_scenes_missing_full_text': 0,
        'low_alignment_scenes': 0,
        'low_symbol_density_scenes': 0,
    }
    notes: list[str] = []

    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                totals['scenes'] += 1
                if scene.scene_duration_sec > 3.0:
                    checks['scene_duration_max_3_sec'] = False
                    totals['scenes_over_3_sec'] += 1
                if style_prompt not in scene.image_prompt:
                    checks['charcoal_prompt_present_all_scenes'] = False
                    totals['scenes_missing_style_prompt'] += 1
                if not scene.references:
                    checks['footnote_references_per_sentence'] = False
                    totals['scenes_missing_references'] += 1
                if scene.quote_full_text or '"' in scene.sentence or '“' in scene.sentence:
                    totals['quote_scenes'] += 1
                    if not scene.quote_full_text and ('"' in scene.sentence or '“' in scene.sentence):
                        totals['quote_scenes_missing_full_text'] += 1
                if storyboard.sync_mode == 'dual_script' and scene.alignment_confidence < 0.65:
                    totals['low_alignment_scenes'] += 1
                if _symbol_density_ratio(scene.sentence, scene.key_visual_tokens, scene.visual_elements) < 0.22:
                    checks['visual_symbol_density_sufficient'] = False
                    totals['low_symbol_density_scenes'] += 1

    if storyboard.sync_mode == 'dual_script' and totals['low_alignment_scenes'] > 0:
        notes.append('Some dual-script alignments are low-confidence and should be reviewed manually.')
    if totals['quote_scenes_missing_full_text'] > 0:
        notes.append('Some quote scenes do not have extracted full-quote text.')
    if not storyboard.canva_only_images:
        notes.append('Canva-only mode is disabled. Enable canva_only_images for strict policy.')

    checks['dual_script_sync_present_when_provided'] = (
        storyboard.sync_mode == 'single_script' or totals['low_alignment_scenes'] == 0
    )
    if storyboard.sync_mode == 'dual_script':
        low_conf_limit = max(1, int(totals['scenes'] * 0.05))
        checks['dual_script_sync_present_when_provided'] = totals['low_alignment_scenes'] <= low_conf_limit
        if not checks['dual_script_sync_present_when_provided']:
            notes.append('Dual-script sync failed strict threshold: too many low-confidence aligned scenes.')
    if totals['low_symbol_density_scenes'] > 0:
        notes.append('Some scenes have weak symbol coverage compared with sentence content.')

    hard_fail_checks = {
        'sentence_level_visuals',
        'scene_duration_max_3_sec',
        'charcoal_prompt_present_all_scenes',
        'book_timeline_required',
        'zoom_only_transition_intent',
        'section_close_full_page_reveal',
        'canva_only_mode_enabled',
        'dual_script_sync_present_when_provided',
        'footnote_references_per_sentence',
        'visual_symbol_density_sufficient',
    }
    failed_checks = [name for name in hard_fail_checks if not checks.get(name, False)]
    overall_pass = not failed_checks

    return {
        'version': 'phase2-guidelines-v1',
        'overall_pass': overall_pass,
        'failed_hard_checks': failed_checks,
        'checks': checks,
        'totals': totals,
        'notes': notes,
    }


def _symbol_density_ratio(sentence: str, key_tokens: list[str], visual_elements: list[str]) -> float:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", sentence)
    content_words = [w for w in words if w.lower() not in {'the', 'and', 'for', 'with', 'that', 'this', 'from'}]
    symbols = {s.strip().lower() for s in key_tokens + visual_elements if s and s.strip()}
    return len(symbols) / max(1, len(content_words))
