#!/bin/bash
# Fix 504 Gateway Timeout — patch every nginx vhost that proxies to phase2 (port 8001)
set -e

TIMEOUT_BLOCK='        proxy_connect_timeout 600s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        send_timeout 1800s;'

patch_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  if grep -q 'proxy_pass.*8001' "$f" 2>/dev/null || grep -q 'phase2.undz.shop' "$f" 2>/dev/null; then
    if grep -q proxy_read_timeout "$f"; then
      sed -i 's/proxy_connect_timeout [0-9]*s;/proxy_connect_timeout 600s;/g' "$f"
      sed -i 's/proxy_send_timeout [0-9]*s;/proxy_send_timeout 1800s;/g' "$f"
      sed -i 's/proxy_read_timeout [0-9]*s;/proxy_read_timeout 1800s;/g' "$f"
    elif grep -q 'proxy_set_header X-Forwarded-Proto' "$f"; then
      sed -i "/proxy_set_header X-Forwarded-Proto/a\\${TIMEOUT_BLOCK}" "$f"
    fi
    echo "Patched: $f"
  fi
}

for f in /etc/nginx/sites-available/* /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  patch_file "$f"
done

# Hostinger sometimes uses default.conf only
patch_file /etc/nginx/sites-enabled/default.conf

nginx -t
systemctl reload nginx
echo "OK — nginx proxy timeouts set to 30 minutes where phase2 is proxied"
