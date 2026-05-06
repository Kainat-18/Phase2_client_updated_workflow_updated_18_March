from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.models import Storyboard
from app.utils import ensure_dir, safe_slug


class ImageGenerator:
    def generate_for_storyboard(self, storyboard: Storyboard, out_dir: Path) -> Storyboard:
        if settings.canva_only_images or storyboard.canva_only_images:
            raise ValueError(
                'Canva-only mode is enabled. Generate final images in Canva using canva_prompts.csv.'
            )
        img_dir = ensure_dir(out_dir / 'images')
        for sec_idx, section in enumerate(storyboard.sections, start=1):
            for para in section.paragraphs:
                for scene in para.scenes:
                    name = f"{sec_idx:02d}_{scene.sentence_index:03d}_{safe_slug(scene.sentence[:40])}.png"
                    img_path = img_dir / name
                    self._make_placeholder(img_path, section.title, scene.on_screen_text or scene.sentence)
                    scene.image_path = str(img_path.relative_to(out_dir))
        return storyboard

    def _make_placeholder(self, path: Path, section_title: str, text: str) -> None:
        img = Image.new('L', (1280, 720), color=245)
        draw = ImageDraw.Draw(img)
        border = 28
        draw.rectangle((border, border, 1280-border, 720-border), outline=50, width=4)
        draw.text((80, 70), section_title[:80], fill=30)
        draw.text((80, 180), text[:220], fill=60)
        draw.text((980, 660), 'TheoEngage', fill=90)
        img.save(path)
