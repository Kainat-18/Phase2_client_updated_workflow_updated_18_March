#!/bin/bash
# Fix 504 Gateway Timeout on /process (LLM pipeline can run 10–30+ minutes)
set -e

for CONF in /etc/nginx/sites-available/phase2-undz /etc/nginx/sites-available/phase2; do
  [ -f "$CONF" ] || continue
  if grep -q proxy_read_timeout "$CONF"; then
    sed -i 's/proxy_connect_timeout [0-9]*s;/proxy_connect_timeout 600s;/' "$CONF"
    sed -i 's/proxy_send_timeout [0-9]*s;/proxy_send_timeout 1800s;/' "$CONF"
    sed -i 's/proxy_read_timeout [0-9]*s;/proxy_read_timeout 1800s;/' "$CONF"
  else
    sed -i '/proxy_set_header X-Forwarded-Proto/a\        proxy_connect_timeout 600s;\n        proxy_send_timeout 1800s;\n        proxy_read_timeout 1800s;\n        send_timeout 1800s;' "$CONF"
  fi
  echo "Patched: $CONF"
done

nginx -t
systemctl reload nginx
echo "OK — nginx now waits up to 30 minutes for /process"
