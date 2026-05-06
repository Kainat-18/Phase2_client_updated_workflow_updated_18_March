from __future__ import annotations

import json
import logging
import re
from typing import Any
import httpx

from app.config import settings
from app.prompts import (
    BRAND_RENDERING_DEFAULT,
    SYSTEM_PROMPT,
    OVERLAY_SYSTEM_PROMPT,
    CITATION_SYSTEM_PROMPT,
    REFINEMENT_SYSTEM_PROMPT,
    ensure_brand_block,
    make_user_prompt,
    make_overlay_user_prompt,
    make_citation_user_prompt,
    make_refinement_prompt,
)

logger = logging.getLogger(__name__)

VIBRANT_STYLE_PATTERN = r"A richly detailed illustration with fully vibrant saturated colours, executed in a classical painterly style with warm natural lighting, high contrast, and cinematic depth of field, medium shot\.?"


def _enrich_personnel_dates(name: str) -> str:
    """Query Wikipedia REST API for lifespan of a named historical figure."""
    import json as _j
    import re as _re
    import urllib.parse
    import urllib.request

    try:
        q = urllib.parse.quote(name.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{q}"
        req = urllib.request.Request(url, headers={"User-Agent": "TheoEngage/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _j.loads(r.read())
        extract = data.get("extract", "")
        m = _re.search(r"\((\d{3,4}).*?(\d{3,4})\)", extract)
        if m:
            return f"({m.group(1)}–{m.group(2)})"
        m2 = _re.search(r"born.*?(\d{3,4})", extract, _re.IGNORECASE)
        if m2:
            return f"(b. {m2.group(1)})"
    except Exception:
        pass
    return ""


class LLMPlanner:
    def __init__(self, provider: str = 'fallback') -> None:
        self.requested_provider = provider
        self.provider = 'xai'
        self.base_url = settings.resolved_llm_base_url(self.provider)
        self.model = settings.resolved_llm_model(self.provider)
        self.api_key = settings.resolved_llm_api_key(self.provider)
        self.enabled = bool(self.api_key)

        if settings.llm_debug:
            logger.info("DEBUG LLM provider: %s", self.provider)
            logger.info("DEBUG LLM base_url: %s", self.base_url)
            logger.info("DEBUG LLM model: %s", self.model)
            logger.info("DEBUG LLM api_key_present: %s", bool(self.api_key))

        self.disabled_reason = ''
        if not self.enabled:
            self.disabled_reason = 'LLM disabled: no XAI_API_KEY/LLM_API_KEY found. Grok is required.'
            logger.error(self.disabled_reason)
            raise RuntimeError(self.disabled_reason)

    def plan_paragraph(
        self,
        title: str,
        section_title: str,
        paragraph_text: str,
        style_prompt: str,
        paragraph_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._api_plan(title, section_title, paragraph_text, style_prompt, paragraph_analysis=paragraph_analysis)
        except Exception as exc:
            raise RuntimeError(f"Grok API request failed: {exc}") from exc

    def refine_image_prompt(
        self,
        original_prompt: str,
        change_instructions: str,
        style_prompt: str,
    ) -> str:
        try:
            return self._api_refine(original_prompt, change_instructions, style_prompt)
        except Exception as exc:
            raise RuntimeError(f"Grok API refinement request failed: {exc}") from exc

    def generate_overlay_elements(
        self,
        section_title: str,
        paragraph_text: str,
        episode_section_type: str = "",
        channel_name: str = "",
    ) -> dict[str, Any]:
        payload = {
            'model': self.model,
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': OVERLAY_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': make_overlay_user_prompt(
                        section_title,
                        paragraph_text,
                        episode_section_type=episode_section_type,
                        channel_name=channel_name,
                    ),
                },
            ],
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data['choices'][0]['message']['content']
        result = json.loads(content)
        if not isinstance(result.get('text_elements'), list):
            return {'text_elements': []}
        normalized: list[dict[str, str]] = []
        for item in result.get('text_elements', [])[:6]:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    'type': str(item.get('type', 'keyword')),
                    'content': str(item.get('content', '')).strip(),
                    'timing_hint': str(item.get('timing_hint', 'middle')),
                }
            )
        # Enrich personnel overlays: verify lifespan dates via Wikipedia
        import re as _re

        for item in normalized:
            if item.get("type") == "personnel":
                content = item.get("content", "")
                name_match = _re.match(r"^([A-Za-z ,.'-]+?)(?:\s*\(|\s+—|\s*-)", content)
                if not name_match:
                    continue
                name = name_match.group(1).strip()
                if "c." in content or ("(" not in content):
                    verified = _enrich_personnel_dates(name)
                    if verified:
                        content = _re.sub(r"\(c\..*?\)", verified, content, count=1)
                        if "(" not in item["content"]:
                            content = content.replace(name, f"{name} {verified}", 1)
                        item["content"] = content
        return {'text_elements': normalized}

    def generate_chicago_citations(
        self,
        paragraph_text: str,
        bibliography_map: dict[str, str],
    ) -> dict[str, Any]:
        if not bibliography_map:
            return {'citations': []}
        bibliography_lines = '\n'.join(f"[{k}] {v}" for k, v in bibliography_map.items())
        payload = {
            'model': self.model,
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': CITATION_SYSTEM_PROMPT},
                {'role': 'user', 'content': make_citation_user_prompt(paragraph_text, bibliography_lines)},
            ],
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data['choices'][0]['message']['content']
        result = json.loads(content)
        if not isinstance(result.get('citations'), list):
            return {'citations': []}
        normalized: list[dict[str, str]] = []
        for item in result.get('citations', []):
            if not isinstance(item, dict):
                continue
            citation_number = item.get('citation_number')
            if citation_number is None:
                continue
            normalized.append(
                {
                    'citation_number': str(citation_number).strip(),
                    'sentence_excerpt': str(item.get('sentence_excerpt', '')).strip(),
                    'citation_short': str(item.get('citation_short', '')).strip(),
                    'citation_full': str(item.get('citation_full', '')).strip(),
                }
            )
        return {'citations': normalized}

    def _api_plan(
        self,
        title: str,
        section_title: str,
        paragraph_text: str,
        style_prompt: str,
        paragraph_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if settings.llm_debug:
            logger.info("DEBUG LLM provider: %s", self.provider)
            logger.info("DEBUG LLM base_url: %s", self.base_url)
            logger.info("DEBUG LLM model: %s", self.model)
            logger.info("DEBUG LLM api_key_present: %s", bool(self.api_key))

        analysis_block = ""
        if paragraph_analysis:
            analysis_block = f"\n\nStructured analysis to use (JSON):\n{json.dumps(paragraph_analysis, ensure_ascii=True)}"
        payload = {
            'model': self.model,
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': make_user_prompt(title, section_title, paragraph_text) + analysis_block},
            ],
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data['choices'][0]['message']['content']
        result = json.loads(content)
        return _normalize_image_prompt_result(result, style_prompt)

    def _api_refine(
        self,
        original_prompt: str,
        change_instructions: str,
        style_prompt: str,
    ) -> str:
        if settings.llm_debug:
            logger.info("DEBUG LLM refine provider: %s", self.provider)
            logger.info("DEBUG LLM refine base_url: %s", self.base_url)
            logger.info("DEBUG LLM refine model: %s", self.model)
            logger.info("DEBUG LLM refine api_key_present: %s", bool(self.api_key))

        user_content = make_refinement_prompt(original_prompt, change_instructions)
        payload = {
            'model': self.model,
            'temperature': 0.2,
            'messages': [
                {'role': 'system', 'content': REFINEMENT_SYSTEM_PROMPT},
                {'role': 'user', 'content': user_content},
            ],
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = (data['choices'][0]['message']['content'] or '').strip()
        return content.strip()

    def _fallback(
        self,
        paragraph_text: str,
        section_title: str,
        style_prompt: str,
        paragraph_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = re.sub(r'\s+', ' ', paragraph_text).strip()
        lowered = f" {text.lower()} "
        analysis = paragraph_analysis or {}
        locations = [str(x) for x in analysis.get('locations', [])]
        named_figures = [str(x) for x in analysis.get('named_figures', [])]
        theological_concepts = [str(x) for x in analysis.get('theological_concepts', [])]
        events = [str(x) for x in analysis.get('events', [])]
        quotes = [str(x) for x in analysis.get('quotes', [])]
        dates = [str(x) for x in analysis.get('dates', [])]
        movement = bool(analysis.get('movement', False))

        has_map = bool(locations) or movement or any(w in lowered for w in [' map ', 'region', 'city', 'from ', ' to '])
        has_quote = bool(quotes) or '"' in text or '“' in text or '”' in text
        has_figures = bool(named_figures)
        has_theology = bool(theological_concepts) or any(w in lowered for w in ['divinity', 'grace', 'salvation', 'humanity', 'christ'])
        has_event = bool(events) or any(w in lowered for w in ['council', 'debate', 'controversy', 'condemn'])
        has_timeline = bool(dates) or bool(re.search(r'\b\d{3,4}\b', text))
        has_divinity_and_humanity = (('divinity' in lowered or 'divine nature' in lowered) and ('humanity' in lowered or 'human nature' in lowered)) or ('christology' in lowered)
        is_transition = bool(analysis.get('is_transition', False))

        prompts = []
        analysis_parts = []
        if has_figures:
            analysis_parts.append('historical figures')
        if has_map:
            analysis_parts.append('locations or movement')
        if has_event:
            analysis_parts.append('council/event context')
        if has_theology:
            analysis_parts.append('theological concepts')
        if has_quote:
            analysis_parts.append('quote treatment')
        if has_timeline:
            analysis_parts.append('timeline/date reference')
        if not analysis_parts:
            analysis_parts.append('general conceptual illustration')

        if is_transition:
            prompt = (
                f"Lightweight transitional scholarly parchment scene for section {section_title}, with subtle manuscripts, "
                "gentle architectural framing, and space for a small side label only. "
                f"{style_prompt}"
            )
            prompts.append({
                'visual_concept': 'transition context scene',
                'image_prompt': prompt,
                'on_screen_text': _overlay_text(text, prefer_quote=False),
                'placement': 'side label',
                'arrows_connections': 'no',
                'additional_notes': 'Transition paragraph: keep visual simple and avoid extra scene inflation.',
            })
        elif has_map or has_figures or has_event:
            composition = []
            if has_figures:
                composition.append(
                    f"historically grounded figures related to this paragraph ({', '.join(named_figures[:3])}) in period-appropriate attire"
                )
            if has_event:
                composition.append('a focused theological discussion setting with manuscripts, lecterns, and context-aware symbolism')
            if has_map:
                if locations:
                    location_text = ', '.join(locations[:4])
                    map_text = f"a parchment historical map featuring {location_text} with subtle labeled place markers"
                else:
                    map_text = 'a parchment regional map with subtle labeled place markers'
                if movement:
                    map_text += ' and thin dotted directional arrows'
                composition.append(map_text)
            if has_timeline:
                composition.append('subtle date/period cues integrated near map or background margins')
            base = '; '.join(composition) or f"scholarly visual scene for {section_title}"
            if has_quote:
                base += '; reserve elegant centered quote-box area with softly dimmed scholarly background'
            prompt = f"{base}. Keep it paragraph-specific and avoid generic placeholders. {style_prompt}"
            prompts.append({
                'visual_concept': 'historical or geographic scene',
                'image_prompt': prompt,
                'on_screen_text': _overlay_text(text, prefer_quote=has_quote),
                'placement': 'center quote box' if has_quote else ('map label' if has_map else 'side label'),
                'arrows_connections': 'yes' if has_map or has_theology else 'no',
                'additional_notes': 'Use this prompt in Canva. Add polished labels in Canva rather than relying on generated text.',
            })

        if has_theology and (has_figures or has_map or has_event):
            theology_bits = ['Symbolic theological composition tied directly to the paragraph']
            if 'divinity' in lowered or 'christ' in lowered or 'christology' in lowered:
                theology_bits.append('emphasizing Christ or divine reality')
            if 'humanity' in lowered or 'human will' in lowered or 'human nature' in lowered:
                theology_bits.append('humanity and human will')
            if 'grace' in lowered or 'salvation' in lowered:
                theology_bits.append('grace, salvation, and restoration')
            if 'original sin' in lowered or 'sin' in lowered:
                theology_bits.append('original sin, guilt, damaged desire, or broken order')
            if has_divinity_and_humanity:
                theology_bits.append(
                    'Include a distinct blue symbolic sphere for divinity and a distinct red symbolic sphere for humanity, overlapping but not blending into purple, with subtle connector arrows where needed.'
                )
            theology_bits.append('use universal symbolic imagery unless named figures are explicitly needed')
            theology_bits.append('include connector arrows or layered circles when concepts need comparison')
            if has_quote:
                theology_bits.append('full quote treatment with elegant centered serif quote box area reserved')
            prompt = f"{', '.join(theology_bits)}. Scholarly parchment background with concise label areas reserved for Canva overlays. {style_prompt}"
            prompts.append({
                'visual_concept': 'symbolic theological diagram',
                'image_prompt': prompt,
                'on_screen_text': _overlay_text(text, prefer_quote=has_quote),
                'placement': 'side explainer box' if not has_quote else 'center quote box',
                'arrows_connections': 'yes',
                'additional_notes': 'Keep symbols clear and concept-driven. Add final text overlays manually in Canva.',
            })

        if not prompts:
            topic_terms = named_figures[:2] + locations[:2] + theological_concepts[:2] + events[:2]
            topic_phrase = ', '.join(topic_terms) if topic_terms else section_title
            base = (
                f"scholarly charcoal illustration for the paragraph focused on {topic_phrase}, "
                "with manuscript texture, contextual architecture, and subtle labels only where necessary"
            )
            if has_divinity_and_humanity:
                base += ', include distinct blue and red symbolic spheres, overlapping but not blending into purple'
            if has_quote:
                base += ', reserve an elegant centered serif quote box area with softly dimmed background'
            prompt = f"{base}. {style_prompt}"
            prompts.append({
                'visual_concept': 'contextual scholarly illustration',
                'image_prompt': prompt,
                'on_screen_text': _overlay_text(text, prefer_quote=has_quote),
                'placement': 'center quote box' if has_quote else 'side label',
                'arrows_connections': 'no',
                'additional_notes': 'Use this as a single Canva prompt for the paragraph.',
            })

        prompts = prompts[:2]
        analysis_line = f"Key visual elements: {', '.join(analysis_parts)}. Use {len(prompts)} Canva prompt(s) for this paragraph."
        if self.disabled_reason:
            analysis_line = f"{analysis_line} WARNING: {self.disabled_reason}"
        return {
            'paragraph_analysis': analysis_line,
            'prompt_count': len(prompts),
            'prompts': prompts,
        }

def _overlay_text(text: str, prefer_quote: bool = False) -> str:
    if prefer_quote:
        m = re.search(r'["“](.*?)["”]', text)
        if m:
            q = m.group(1).strip()
            if q:
                return q
    compact = text.strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", compact)
    if not words:
        return ''
    if len(words) <= 8:
        return compact
    label = ' '.join(words[:8])
    return label.title()


def _normalize_image_prompt_result(result: dict[str, Any], style_prompt: str) -> dict[str, Any]:
    paragraph_analysis = str(result.get('paragraph_analysis', '')).strip()
    prompts: list[dict[str, str]] = []
    effective_style = (style_prompt or BRAND_RENDERING_DEFAULT).strip()

    if isinstance(result.get('prompts'), list):
        for item in result.get('prompts', []):
            if not isinstance(item, dict):
                continue
            prompt = str(item.get('image_prompt', '')).strip()
            prompt = re.sub(VIBRANT_STYLE_PATTERN, ' ', prompt, flags=re.IGNORECASE).strip()
            if effective_style:
                prompt = ensure_brand_block(prompt)
            prompts.append(
                {
                    'visual_concept': str(item.get('visual_concept', 'Canva image scene')).strip(),
                    'image_prompt': prompt,
                    'on_screen_text': str(item.get('on_screen_text', '')).strip(),
                    'placement': str(item.get('placement', 'side label')).strip(),
                    'arrows_connections': str(item.get('arrows_connections', 'no')).strip(),
                    'additional_notes': str(item.get('additional_notes', '')).strip(),
                }
            )
    elif isinstance(result.get('image_prompts'), list):
        for idx, prompt in enumerate(result.get('image_prompts', []), start=1):
            prompt_text = str(prompt).strip()
            prompt_text = re.sub(VIBRANT_STYLE_PATTERN, ' ', prompt_text, flags=re.IGNORECASE).strip()
            if effective_style:
                prompt_text = ensure_brand_block(prompt_text)
            prompts.append(
                {
                    'visual_concept': f'Scene {idx}',
                    'image_prompt': prompt_text,
                    'on_screen_text': '',
                    'placement': 'side label',
                    'arrows_connections': 'no',
                    'additional_notes': '',
                }
            )

    prompt_count = int(result.get('prompt_count', len(prompts) or 1))
    if prompt_count < 1:
        prompt_count = 1
    if prompt_count > 3:
        prompt_count = 3
    prompts = prompts[:prompt_count]

    return {
        'paragraph_analysis': paragraph_analysis,
        'prompt_count': len(prompts),
        'prompts': prompts,
    }
