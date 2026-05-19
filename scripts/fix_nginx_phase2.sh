#!/bin/bash
set -e

PHASE2_CONF="/etc/nginx/sites-available/phase2"
DEFAULT_CONF="/etc/nginx/sites-enabled/default.conf"

# 1) Correct nginx config for phase2 only
cat > "$PHASE2_CONF" << 'NGINX'
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
        proxy_connect_timeout 600s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        send_timeout 1800s;
    }
}
NGINX

ln -sf "$PHASE2_CONF" /etc/nginx/sites-enabled/phase2

# 2) Remove ALL server blocks mentioning phase2.undz.shop from default.conf
if [ -f "$DEFAULT_CONF" ]; then
  cp "$DEFAULT_CONF" "${DEFAULT_CONF}.bak.$(date +%s)"
  python3 << 'PY'
from pathlib import Path
import re

path = Path("/etc/nginx/sites-enabled/default.conf")
text = path.read_text()
lines = text.splitlines(keepends=True)
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if re.match(r"^\s*server\s*\{", line):
        block = []
        depth = 0
        while i < len(lines):
            block.append(lines[i])
            depth += lines[i].count("{") - lines[i].count("}")
            i += 1
            if depth <= 0 and "{" in "".join(block):
                break
        block_text = "".join(block)
        if "phase2.undz.shop" not in block_text:
            out.extend(block)
    else:
        out.append(line)
        i += 1
new_text = "".join(out)
path.write_text(new_text)
print("Removed phase2 blocks from default.conf")
PY
fi

nginx -t
systemctl reload nginx
systemctl restart phase2

echo "=== local app ==="
curl -sf http://127.0.0.1:8001/login | head -2

echo "=== via nginx https ==="
curl -sk https://127.0.0.1/login -H "Host: phase2.undz.shop" | head -2

echo "=== via public https ==="
curl -sk https://phase2.undz.shop/login | head -2

echo "FIXED"
