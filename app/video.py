from __future__ import annotations

from pathlib import Path

from app.models import Storyboard


def make_preview_video(storyboard: Storyboard, out_dir: Path) -> Path:
    from moviepy.editor import ImageClip, concatenate_videoclips

    clips = []
    for section in storyboard.sections:
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                if scene.image_path:
                    duration = min(3.0, max(1.2, scene.scene_duration_sec))
                    clip = ImageClip(str(out_dir / scene.image_path)).set_duration(duration)
                    clips.append(clip)
    if not clips:
        raise ValueError('No images found. Generate images first.')
    video = concatenate_videoclips(clips, method='compose')
    output_path = out_dir / 'preview.mp4'
    video.write_videofile(str(output_path), fps=24, codec='libx264', audio=False, logger=None)
    return output_path
