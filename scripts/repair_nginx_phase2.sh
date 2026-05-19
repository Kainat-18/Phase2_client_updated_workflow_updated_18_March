#!/bin/bash
# One-shot repair: fix broken nginx after bad patch (run on VPS)
set -e

CONF="/etc/nginx/sites-available/phase2-undz"
ENABLED="/etc/nginx/sites-enabled/000-phase2-undz.conf"

# .bak files in sites-enabled break nginx - move them out
mkdir -p /etc/nginx/_disabled_backups
for f in /etc/nginx/sites-enabled/*.bak*; do
  [ -e "$f" ] || continue
  mv "$f" /etc/nginx/_disabled_backups/
  echo "Moved out of sites-enabled: $f"
done

cat > "$CONF" << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name phase2.undz.shop;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
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

nginx -t
systemctl reload nginx
systemctl restart phase2
sleep 1

echo "=== checks ==="
systemctl is-active phase2
curl -sf http://127.0.0.1:8001/login | grep -o "Theology Academy" | head -1
curl -sk https://phase2.undz.shop/login | grep -o "Theology Academy" | head -1
echo "REPAIR OK"
