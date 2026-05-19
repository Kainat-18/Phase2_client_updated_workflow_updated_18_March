from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.utils import ensure_dir, safe_slug


class JobRunner:
    def __init__(self, status_dir: str) -> None:
        self._status_dir = Path(status_dir)
        ensure_dir(str(self._status_dir))
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self._status_dir / f"{safe_slug(job_id)}.json"

    def read(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write(self, job_id: str, payload: dict[str, Any]) -> None:
        path = self._path(job_id)
        with self._lock:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_job_id(self, label: str) -> str:
        base = safe_slug(label) or "job"
        return f"{base}_{int(time.time())}"

    def start(self, job_id: str, worker: Callable[[], str]) -> None:
        self.write(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "message": "Waiting to start...",
                "result_job_id": "",
                "error": "",
                "updated_at": time.time(),
            },
        )

        def run() -> None:
            self.write(
                job_id,
                {
                    "job_id": job_id,
                    "status": "running",
                    "message": "Generating storyboard (this may take several minutes)...",
                    "result_job_id": "",
                    "error": "",
                    "updated_at": time.time(),
                },
            )
            try:
                result_job_id = worker()
                self.write(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "done",
                        "message": "Complete",
                        "result_job_id": result_job_id,
                        "error": "",
                        "updated_at": time.time(),
                    },
                )
            except Exception as exc:
                self.write(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "message": "Processing failed",
                        "result_job_id": "",
                        "error": str(exc),
                        "updated_at": time.time(),
                    },
                )

        thread = threading.Thread(target=run, daemon=True, name=f"job-{job_id}")
        thread.start()
