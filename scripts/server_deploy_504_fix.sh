#!/bin/bash
set -e
cd /var/www/Phase2_client_updated_workflow_updated_18_March
git pull
bash scripts/repair_nginx_phase2.sh
sleep 2
echo "=== phase2 service ==="
systemctl is-active phase2
echo "=== login page ==="
curl -sf http://127.0.0.1:8001/login | grep -E "Theology Academy|Welcome back" | head -1 || echo "WARN: app check failed"
echo "=== nginx timeouts on phase2 vhost ==="
grep -E "proxy_read_timeout|phase2.undz" /etc/nginx/sites-available/phase2 /etc/nginx/sites-enabled/000-phase2-undz.conf 2>/dev/null | head -6 || true
echo "Deployed — upload again; you should see a processing page instead of 504."
