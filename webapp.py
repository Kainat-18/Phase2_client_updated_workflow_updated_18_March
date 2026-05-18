from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.parse import quote
import csv

from fastapi import FastAPI, File, Form, Request, UploadFile, HTTPException, Body
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    authenticate_user,
    create_user,
    delete_user,
    ensure_default_admin,
    get_user_by_id,
    init_auth_db,
    list_users,
)
from app.config import settings
from app.llm import LLMPlanner
from app.pipeline import StoryboardPipeline
from app.utils import ensure_dir, safe_slug, zip_folder

app = FastAPI(title="Theology Academy Studio")
BOOT_SESSION_ID = str(int(time.time()))
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,
    max_age=settings.session_idle_timeout_seconds,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pipeline = StoryboardPipeline()
ensure_dir(settings.upload_dir)
ensure_dir(settings.output_dir)
init_auth_db(settings.auth_db_path)
ensure_default_admin(settings.auth_db_path, settings.admin_username, settings.admin_password)


def _current_user(request: Request) -> dict | None:
    session_boot_id = request.session.get("boot_session_id")
    if session_boot_id != BOOT_SESSION_ID:
        request.session.clear()
        return None

    now = time.time()
    timeout_seconds = max(int(settings.session_idle_timeout_seconds), 60)
    last_active_raw = request.session.get("last_active_at")
    if last_active_raw is not None:
        try:
            last_active = float(last_active_raw)
        except (TypeError, ValueError):
            request.session.clear()
            return None
        if now - last_active > timeout_seconds:
            request.session.clear()
            return None

    raw_user_id = request.session.get("user_id")
    if raw_user_id is None:
        return None
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        request.session.clear()
        return None
    user = get_user_by_id(settings.auth_db_path, user_id)
    if not user:
        request.session.clear()
        return None
    request.session["last_active_at"] = now
    return user


def _login_redirect(request: Request) -> RedirectResponse:
    next_path = quote(request.url.path)
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _base_template_context(request: Request, extra: dict | None = None) -> dict:
    context = {"request": request, "current_user": _current_user(request)}
    if extra:
        context.update(extra)
    return context


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    user = _current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        _base_template_context(
            request,
            {
                "next": next,
                "error": "",
            },
        ),
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = authenticate_user(settings.auth_db_path, username=username, password=password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            _base_template_context(
                request,
                {
                    "next": next,
                    "error": "Invalid username or password.",
                },
            ),
            status_code=401,
        )
    request.session["user_id"] = user["id"]
    request.session["last_active_at"] = time.time()
    request.session["boot_session_id"] = BOOT_SESSION_ID
    safe_next = next if next.startswith("/") else "/"
    return RedirectResponse(url=safe_next or "/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    users = list_users(settings.auth_db_path)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        _base_template_context(
            request,
            {
                "users": users,
                "message": "",
                "error": "",
                "current_user_id": user["id"],
            },
        ),
    )


@app.post("/admin/users", response_class=HTMLResponse)
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str | None = Form(None),
):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    created, feedback = create_user(
        settings.auth_db_path,
        username=username,
        password=password,
        is_admin=bool(is_admin),
    )
    users = list_users(settings.auth_db_path)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        _base_template_context(
            request,
            {
                "users": users,
                "message": feedback if created else "",
                "error": "" if created else feedback,
                "current_user_id": user["id"],
            },
        ),
        status_code=200 if created else 400,
    )


@app.post("/admin/users/{target_user_id}/delete", response_class=HTMLResponse)
def admin_delete_user(request: Request, target_user_id: int):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    deleted, feedback = delete_user(
        settings.auth_db_path,
        target_user_id=target_user_id,
        actor_user_id=user["id"],
    )
    users = list_users(settings.auth_db_path)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        _base_template_context(
            request,
            {
                "users": users,
                "message": feedback if deleted else "",
                "error": "" if deleted else feedback,
                "current_user_id": user["id"],
            },
        ),
        status_code=200 if deleted else 400,
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)

    jobs = []
    output_path = Path(settings.output_dir)
    if output_path.exists():
        for item in sorted(output_path.iterdir(), reverse=True):
            if item.is_dir() and item.name != "auth":
                jobs.append(
                    {
                        "id": item.name,
                        "title": item.name.replace("_", " ").title(),
                        "path": f"/jobs/{item.name}",
                    }
                )
    return templates.TemplateResponse(request, "index.html", _base_template_context(request, {"jobs": jobs}))


@app.post("/process")
async def process_upload(
    request: Request,
    source_file: UploadFile = File(...),
    academic_file: UploadFile | None = File(None),
    style_prompt: str = Form(settings.default_style_prompt),
    title_override: str = Form(""),
):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)

    suffix = Path(source_file.filename or "upload.txt").suffix.lower()
    if suffix not in {".pdf", ".docx", ".md", ".txt"}:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, MD, and TXT are supported.")

    base_name = safe_slug(Path(source_file.filename or "upload").stem)
    upload_name = f"{base_name}{suffix}"
    upload_path = Path(settings.upload_dir) / upload_name

    with upload_path.open("wb") as f:
        shutil.copyfileobj(source_file.file, f)

    academic_upload_path = None
    if academic_file and academic_file.filename:
        academic_suffix = Path(academic_file.filename).suffix.lower()
        if academic_suffix not in {".pdf", ".docx", ".md", ".txt"}:
            raise HTTPException(status_code=400, detail="Academic script must be PDF, DOCX, MD, or TXT.")
        academic_base = safe_slug(Path(academic_file.filename).stem)
        academic_name = f"{academic_base}{academic_suffix}"
        academic_upload_path = Path(settings.upload_dir) / f"academic_{academic_name}"
        with academic_upload_path.open("wb") as f:
            shutil.copyfileobj(academic_file.file, f)

    try:
        out_dir = pipeline.run(
            str(upload_path),
            academic_input_path=str(academic_upload_path) if academic_upload_path else None,
            provider='xai',
            style_prompt=style_prompt.strip() or settings.default_style_prompt,
            title_override=title_override.strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job_id = Path(out_dir).name
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)

    job_dir = Path(settings.output_dir) / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    preview_file = job_dir / "storyboard_preview.html"
    storyboard_file = job_dir / "storyboard.json"
    manifest_file = job_dir / "final_scene_manifest.json"
    preferred_files = [
        "canva_simple.csv",
        "final_scene_manifest.csv",
        "final_scene_manifest.json",
        "canva_prompts.csv",
        "book_timeline.json",
        "animator_instruction_packet.json",
        "RUN_THIS_NEXT.md",
        "storyboard_preview.html",
        "storyboard.json",
        "storyboard.csv",
        "phase2_paragraph_outputs.csv",
        "compliance_report.json",
    ]
    generated_files: list[dict[str, str]] = []
    seen_files: set[str] = set()
    for name in preferred_files:
        file_path = job_dir / name
        if file_path.exists() and file_path.is_file():
            generated_files.append({"name": name, "path": f"/files/{job_id}/{name}"})
            seen_files.add(name)
    for file_path in sorted(job_dir.iterdir()):
        if not file_path.is_file() or file_path.name in seen_files:
            continue
        generated_files.append({"name": file_path.name, "path": f"/files/{job_id}/{file_path.name}"})
    manifest_scenes: list[dict] = []
    if manifest_file.exists():
        try:
            manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest_scenes = manifest_payload.get("scenes", []) if isinstance(manifest_payload, dict) else []
        except (json.JSONDecodeError, OSError):
            manifest_scenes = []

    return templates.TemplateResponse(
        request,
        "result.html",
        _base_template_context(
            request,
            {
                "job_id": job_id,
                "preview_path": f"/files/{job_id}/storyboard_preview.html",
                "json_path": f"/files/{job_id}/storyboard.json",
                "csv_path": f"/files/{job_id}/storyboard.csv",
                "canva_csv_path": f"/files/{job_id}/canva_prompts.csv",
                "manifest_csv_path": f"/files/{job_id}/final_scene_manifest.csv",
                "manifest_json_path": f"/files/{job_id}/final_scene_manifest.json",
                "timeline_path": f"/files/{job_id}/book_timeline.json",
                "animator_packet_path": f"/files/{job_id}/animator_instruction_packet.json",
                "run_next_path": f"/files/{job_id}/RUN_THIS_NEXT.md",
                "compliance_path": f"/files/{job_id}/compliance_report.json",
                "download_path": f"/download/{job_id}",
                "storyboard_exists": storyboard_file.exists(),
                "preview_exists": preview_file.exists(),
                "manifest_scenes": manifest_scenes,
                "manifest_total": len(manifest_scenes),
                "generated_files": generated_files,
            },
        ),
    )


@app.get("/files/{job_id}/{filename}")
def serve_job_file(request: Request, job_id: str, filename: str):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)

    job_dir = Path(settings.output_dir) / job_id
    file_path = job_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "text/html" if filename.endswith(".html") else None
    return FileResponse(file_path, media_type=media_type)


@app.get("/download/{job_id}")
def download_job(request: Request, job_id: str):
    user = _current_user(request)
    if not user:
        return _login_redirect(request)

    job_dir = Path(settings.output_dir) / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    zip_path = Path(settings.output_dir) / f"{job_id}.zip"
    zip_folder(job_dir, zip_path)
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


@app.post("/api/refine_prompt")
async def api_refine_prompt(
    request: Request,
    payload: dict = Body(...),
):
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    original_prompt = str(payload.get("original_prompt") or "").strip()
    change_instructions = str(payload.get("change_instructions") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip()
    style_prompt = str(payload.get("style_prompt") or settings.default_style_prompt).strip()

    if not original_prompt or not change_instructions:
        raise HTTPException(status_code=400, detail="original_prompt and change_instructions are required.")

    planner = LLMPlanner(provider="xai")
    refined = planner.refine_image_prompt(
        original_prompt=original_prompt,
        change_instructions=change_instructions,
        style_prompt=style_prompt or settings.default_style_prompt,
    )

    # Persist the refined prompt into manifest JSON/CSV if job and scene are provided.
    if job_id and scene_id:
        job_dir = Path(settings.output_dir) / job_id
        try:
            # Update final_scene_manifest.json
            manifest_json_path = job_dir / "final_scene_manifest.json"
            if manifest_json_path.exists():
                try:
                    manifest_payload = json.loads(manifest_json_path.read_text(encoding="utf-8"))
                    scenes = manifest_payload.get("scenes", [])
                    updated = False
                    for scene in scenes:
                        if str(scene.get("scene_id")) == scene_id:
                            scene["image_prompt"] = refined
                            updated = True
                            break
                    if updated:
                        manifest_json_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
                except (json.JSONDecodeError, OSError):
                    pass

            # Helper to update CSV prompts by SceneID
            def _update_csv_prompt(path: Path, id_field: str, prompt_field: str) -> None:
                if not path.exists():
                    return
                try:
                    with path.open("r", encoding="utf-8", newline="") as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                        fieldnames = reader.fieldnames or []
                    changed = False
                    for row in rows:
                        if str(row.get(id_field, "")) == scene_id:
                            row[prompt_field] = refined
                            changed = True
                    if changed and fieldnames:
                        with path.open("w", encoding="utf-8", newline="") as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            writer.writerows(rows)
                except OSError:
                    return

            # Update final_scene_manifest.csv prompt (for internal editing)
            _update_csv_prompt(job_dir / "final_scene_manifest.csv", "SceneID", "Prompt")
            # In canva_prompts.csv we removed `Prompt` and client uses `ColumnF_CanvaImagePrompts` instead.
            _update_csv_prompt(job_dir / "canva_prompts.csv", "SceneID", "ColumnF_CanvaImagePrompts")
        except Exception:
            # Do not fail the API if persistence has issues; return refined prompt anyway.
            pass

    return JSONResponse({"refined_prompt": refined})


@app.post("/api/update_scene_text")
async def api_update_scene_text(
    request: Request,
    payload: dict = Body(...),
):
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    job_id = str(payload.get("job_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip()
    overlay_content = str(payload.get("overlay_content") or "").strip()
    references_display = str(payload.get("references_display") or "").strip()

    if not job_id or not scene_id:
        raise HTTPException(status_code=400, detail="job_id and scene_id are required.")

    job_dir = Path(settings.output_dir) / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found.")

    # Update final_scene_manifest.json
    manifest_json_path = job_dir / "final_scene_manifest.json"
    try:
        if manifest_json_path.exists():
            manifest_payload = json.loads(manifest_json_path.read_text(encoding="utf-8"))
            scenes = manifest_payload.get("scenes", [])
            updated = False
            for scene in scenes:
                if str(scene.get("scene_id")) == scene_id:
                    if overlay_content:
                        scene["overlay_content"] = overlay_content
                    if references_display:
                        scene["references"] = [references_display]
                    else:
                        scene["references"] = []
                    updated = True
                    break
            if updated:
                manifest_json_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
    except (json.JSONDecodeError, OSError):
        # If JSON is unreadable, do not block the request; front-end still has latest text.
        pass

    # Helper to update overlay and references in CSV files by SceneID
    def _update_csv_overlay_and_refs(path: Path) -> None:
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames or []
            changed = False
            for row in rows:
                if str(row.get("SceneID", "")) == scene_id:
                    if overlay_content and "OverlayContent" in row:
                        row["OverlayContent"] = overlay_content
                    if "References" in row:
                        row["References"] = references_display
                    changed = True
            if changed and fieldnames:
                with path.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
        except OSError:
            return

    try:
        _update_csv_overlay_and_refs(job_dir / "final_scene_manifest.csv")
        _update_csv_overlay_and_refs(job_dir / "canva_prompts.csv")
    except Exception:
        # Non-fatal: UI still has updated values even if CSV persistence fails.
        pass

    return JSONResponse(
        {
            "status": "ok",
            "overlay_content": overlay_content,
            "references_display": references_display,
        }
    )
