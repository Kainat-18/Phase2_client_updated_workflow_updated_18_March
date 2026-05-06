from __future__ import annotations

import json
from pathlib import Path
import typer
from app.config import settings
from app.models import Storyboard
from app.pipeline import StoryboardPipeline
from app.image_generation import ImageGenerator

cli = typer.Typer(help="Theology Academy Studio CLI")


@cli.command()
def run(
    input: str = typer.Option(..., help="Path to a YouTube script file (PDF, DOCX, MD, TXT)"),
    academic_input: str = typer.Option('', help="Optional academic script for sentence alignment sync"),
) -> None:
    pipeline = StoryboardPipeline()
    out_dir = pipeline.run(input, academic_input_path=academic_input or None, provider='xai')
    typer.echo(f"Created: {out_dir}")


@cli.command()
def batch(
    input_dir: str = typer.Option(..., help="Folder containing source files"),
) -> None:
    pipeline = StoryboardPipeline()
    folder = Path(input_dir)
    supported = ["*.txt", "*.md", "*.docx", "*.pdf"]
    paths = []
    for pattern in supported:
        paths.extend(sorted(folder.glob(pattern)))
    for path in paths:
        out_dir = pipeline.run(str(path), provider='xai')
        typer.echo(f"Done: {out_dir}")


@cli.command("debug-llm")
def debug_llm() -> None:
    snap = settings.llm_debug_snapshot('xai')
    typer.echo(f"provider: {snap['provider']}")
    typer.echo(f"base_url: {snap['base_url']}")
    typer.echo(f"model: {snap['model']}")
    typer.echo(f"api_key_present: {snap['api_key_present']}")


@cli.command("generate-images")
def generate_images(storyboard: str = typer.Option(..., help="Path to storyboard.json")) -> None:
    sb = Storyboard.model_validate_json(Path(storyboard).read_text(encoding="utf-8"))
    try:
        updated = ImageGenerator().generate_for_storyboard(sb, Path(storyboard).parent)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    Path(storyboard).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    typer.echo("Draft images created.")


@cli.command("make-video")
def make_video(storyboard: str = typer.Option(..., help="Path to storyboard.json")) -> None:
    sb = Storyboard.model_validate_json(Path(storyboard).read_text(encoding="utf-8"))
    from app.video import make_preview_video
    path = make_preview_video(sb, Path(storyboard).parent)
    typer.echo(f"Video created: {path}")


@cli.command("attach-canva-images")
def attach_canva_images(
    storyboard: str = typer.Option(..., help="Path to storyboard.json"),
    images_dir: str = typer.Option(..., help="Folder with Canva-exported images"),
) -> None:
    storyboard_path = Path(storyboard)
    image_folder = Path(images_dir)
    if not image_folder.exists() or not image_folder.is_dir():
        typer.echo("images_dir does not exist or is not a directory.")
        raise typer.Exit(code=1)

    sb = Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
    out_dir = storyboard_path.parent

    supported_ext = {".png", ".jpg", ".jpeg", ".webp"}
    image_files = [p for p in sorted(image_folder.iterdir()) if p.is_file() and p.suffix.lower() in supported_ext]
    if not image_files:
        typer.echo("No supported image files found in images_dir.")
        raise typer.Exit(code=1)

    by_alignment_id: dict[str, Path] = {}
    ordered_files: list[Path] = []
    for path in image_files:
        stem_upper = path.stem.upper()
        if stem_upper.startswith("ALN-"):
            by_alignment_id[stem_upper] = path
        ordered_files.append(path)

    linked = 0
    seq_idx = 0
    for section in sb.sections:
        for paragraph in section.paragraphs:
            for scene in paragraph.scenes:
                mapped = by_alignment_id.get(scene.alignment_id.upper())
                if not mapped and seq_idx < len(ordered_files):
                    mapped = ordered_files[seq_idx]
                    seq_idx += 1
                if not mapped:
                    continue
                target = out_dir / "images" / mapped.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if mapped.resolve() != target.resolve():
                    target.write_bytes(mapped.read_bytes())
                scene.image_path = str(target.relative_to(out_dir))
                linked += 1

    storyboard_path.write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Linked {linked} images into storyboard.")


if __name__ == "__main__":
    cli()
