#!/bin/bash
set -e
APP_DIR="/var/www/Phase2_client_updated_workflow_updated_18_March"
cd "$APP_DIR"

# Git pull (ownership fix)
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
git pull origin main || git pull

# Starlette 1.0 template fix (if pull missed any file)
python3 << 'PY'
from pathlib import Path
p = Path("webapp.py")
t = p.read_text()
if 'TemplateResponse(\n        request,\n        "login.html"' not in t:
    t = t.replace(
        'templates.TemplateResponse(\n        "login.html",',
        'templates.TemplateResponse(\n        request,\n        "login.html",',
    )
    t = t.replace(
        'templates.TemplateResponse(\n            "login.html",',
        'templates.TemplateResponse(\n            request,\n            "login.html",',
    )
    t = t.replace(
        'templates.TemplateResponse(\n        "admin_dashboard.html",',
        'templates.TemplateResponse(\n        request,\n        "admin_dashboard.html",',
    )
    t = t.replace(
        'templates.TemplateResponse(\n        "result.html",',
        'templates.TemplateResponse(\n        request,\n        "result.html",',
    )
    t = t.replace(
        'TemplateResponse("index.html",',
        'TemplateResponse(request, "index.html",',
    )
    p.write_text(t)
    print("Patched webapp.py")
else:
    print("webapp.py already patched")
PY

chown -R www-data:www-data "$APP_DIR"
mkdir -p uploads output output/auth
chmod -R 775 uploads output output/auth 2>/dev/null || true

# Nginx: single config for phase2.undz.shop -> port 8001
cat > /etc/nginx/sites-available/phase2 << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name phase2.undz.shop;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name phase2.undz.shop;

    ssl_certificate /etc/letsencrypt/live/phase2.undz.shop/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/phase2.undz.shop/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/phase2 /etc/nginx/sites-enabled/phase2

# Remove certbot duplicate phase2 block from default.conf (lines with phase2.undz.shop server blocks)
if grep -q "phase2.undz.shop" /etc/nginx/sites-enabled/default.conf 2>/dev/null; then
  python3 << 'PY2'
from pathlib import Path
import re
p = Path("/etc/nginx/sites-enabled/default.conf")
text = p.read_text()
# Remove server blocks that mention phase2.undz.shop
parts = re.split(r'(server\s*\{)', text)
out = []
i = 0
while i < len(parts):
    if i + 1 < len(parts) and parts[i].strip() == 'server':
        block = parts[i] + parts[i + 1]
        if 'phase2.undz.shop' in block:
            i += 2
            continue
        out.append(block)
        i += 2
    else:
        out.append(parts[i])
        i += 1
new_text = ''.join(out)
if new_text != text:
    p.write_text(new_text)
    print("Cleaned default.conf")
PY2
fi

nginx -t
systemctl reload nginx
systemctl restart phase2
sleep 2
systemctl is-active phase2
curl -sf http://127.0.0.1:8001/login | head -3
echo "DONE - open https://phase2.undz.shop/login"
