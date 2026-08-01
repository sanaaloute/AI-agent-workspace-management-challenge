#!/usr/bin/env bash
# AI File Agent — upgrade an existing deployment.
#
# Pulls the latest code (if this is a git checkout), rebuilds and restarts
# the app container, and refreshes the nginx config files (in case they
# changed). Does NOT touch .env, the workspace bind-mounts, or system packages.
#
# Run from the repo root:  bash script/upgrade.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> AI File Agent upgrade (repo: $REPO_ROOT)"

# --- 1. latest code -----------------------------------------------------------
if [ -d .git ]; then
    echo "==> Pulling latest code (fast-forward only)..."
    git pull --ff-only || echo "    git pull skipped/failed — continuing with current code"
else
    echo "==> Not a git checkout — using current files as-is"
fi

# --- 2. app -------------------------------------------------------------------
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"
fi

echo "==> Rebuilding and restarting the app..."
$DOCKER compose up -d --build
$DOCKER compose ps

# --- 3. nginx -----------------------------------------------------------------
echo "==> Refreshing nginx config..."
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agent
sudo cp deploy/nginx-http-snippet.conf /etc/nginx/conf.d/agent-limit.conf
sudo nginx -t
sudo systemctl reload nginx
echo "==> nginx reloaded"

echo
echo "==> Upgrade complete. Logs: $DOCKER compose logs -f"
