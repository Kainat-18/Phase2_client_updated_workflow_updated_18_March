#!/bin/bash
# Fix 504 Gateway Timeout — patch every nginx vhost that proxies to phase2 (port 8001)
set -e

python3 << 'PY'
from pathlib import Path
import re

TIMEOUT_LINES = [
    "        proxy_connect_timeout 600s;",
    "        proxy_send_timeout 1800s;",
    "        proxy_read_timeout 1800s;",
    "        send_timeout 1800s;",
]

def should_patch(text: str) -> bool:
    return "proxy_pass" in text and "8001" in text or "phase2.undz.shop" in text

def patch_text(text: str) -> str:
    if "proxy_read_timeout" in text:
        text = re.sub(r"proxy_connect_timeout\s+\d+s;", "proxy_connect_timeout 600s;", text)
        text = re.sub(r"proxy_send_timeout\s+\d+s;", "proxy_send_timeout 1800s;", text)
        text = re.sub(r"proxy_read_timeout\s+\d+s;", "proxy_read_timeout 1800s;", text)
        return text
    marker = "proxy_set_header X-Forwarded-Proto"
    if marker not in text:
        return text
    insert = "\n".join(TIMEOUT_LINES) + "\n"
    return text.replace(marker, marker + "\n" + insert, 1)

paths = set()
for pattern in (
    "/etc/nginx/sites-available/*",
    "/etc/nginx/sites-enabled/*",
    "/etc/nginx/conf.d/*.conf",
):
    paths.update(Path("/").glob(pattern.lstrip("/")))

paths.add(Path("/etc/nginx/sites-enabled/default.conf"))

for path in sorted(paths):
    if not path.is_file():
        continue
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    if not should_patch(original):
        continue
    updated = patch_text(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        print(f"Patched: {path}")
PY

nginx -t
systemctl reload nginx
echo "OK — nginx proxy timeouts set to 30 minutes where phase2 is proxied"
