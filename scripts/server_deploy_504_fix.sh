#!/bin/bash
set -e
cd /var/www/Phase2_client_updated_workflow_updated_18_March
git pull
bash scripts/patch_nginx_timeouts.sh
systemctl restart phase2
echo "Deployed — upload again; you should see a processing page instead of 504."
