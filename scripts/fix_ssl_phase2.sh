#!/bin/bash
set -e

CONF="/etc/nginx/sites-available/phase2-undz"
ENABLED="/etc/nginx/sites-enabled/000-phase2-undz.conf"
CERT="/etc/letsencrypt/live/phase2.undz.shop/fullchain.pem"

if [ ! -f "$CERT" ]; then
  echo "=== Obtaining SSL cert for phase2.undz.shop ==="
  certbot certonly --nginx -d phase2.undz.shop --non-interactive --agree-tos \
    --register-unsafely-without-email || certbot certonly --webroot -w /var/www/html -d phase2.undz.shop --non-interactive --agree-tos \
    --register-unsafely-without-email
fi

# Ensure phase2 app is running
systemctl restart phase2
sleep 1

echo "=== App on 8001 (must be Theology Academy) ==="
curl -sf http://127.0.0.1:8001/login | grep -E "Theology Academy|Welcome back" | head -2 || echo "WARN: wrong app on 8001"

# Nginx vhost: ONLY phase2.undz.shop, correct SSL + proxy 8001
cat > "$CONF" << 'NGINX'
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

ln -sf "$CONF" "$ENABLED"
rm -f /etc/nginx/sites-enabled/phase2 2>/dev/null || true

# Remove phase2 from default.conf again
if [ -f /etc/nginx/sites-enabled/default.conf ]; then
  python3 << 'PY'
from pathlib import Path
import re
path = Path("/etc/nginx/sites-enabled/default.conf")
lines = path.read_text().splitlines(keepends=True)
out, i = [], 0
while i < len(lines):
    if re.match(r"^\s*server\s*\{", lines[i]):
        block, depth = [], 0
        while i < len(lines):
            block.append(lines[i])
            depth += lines[i].count("{") - lines[i].count("}")
            i += 1
            if depth <= 0 and "{" in "".join(block):
                break
        if "phase2.undz.shop" not in "".join(block):
            out.extend(block)
    else:
        out.append(lines[i])
        i += 1
path.write_text("".join(out))
print("default.conf cleaned")
PY
fi

nginx -t
systemctl reload nginx

echo "=== SSL certificate served for phase2.undz.shop ==="
echo | openssl s_client -connect 127.0.0.1:443 -servername phase2.undz.shop 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || echo "openssl check failed"

echo "=== HTTPS test ==="
curl -sk https://phase2.undz.shop/login | grep -E "Theology Academy|Welcome back" | head -2 || curl -sk https://phase2.undz.shop/login | head -3

echo "DONE - refresh https://phase2.undz.shop/login"
