#!/bin/bash
set -e
cd /var/www/Phase2_client_updated_workflow_updated_18_March
source .venv/bin/activate
python scripts/reset_admin_password.py
systemctl restart phase2
echo "Done — use ADMIN_USERNAME / ADMIN_PASSWORD from .env"
