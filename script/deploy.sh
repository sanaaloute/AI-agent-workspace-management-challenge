#!/usr/bin/env bash
# AI File Agent — fresh one-shot deployment on an Ubuntu/Debian VPS.
#
# Does everything needed for a first install:
#   1. installs Docker + the compose plugin (skipped if already present)
#   2. creates .env from .env.example (you edit the key afterwards)
#   3. installs the nginx site + rate-limit snippet and reloads nginx
#   4. builds and starts the app container
#
# Assumes: nginx is ALREADY installed and running on the host.
# Run from the repo root:  bash script/deploy.sh
set -euo pipefail

DOMAIN="agent.barkosem.com"
APP_PORT="${PORT:-8000}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> AI File Agent deploy (repo: $REPO_ROOT)"

# --- 1. Docker ---------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "==> Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER" || true
    echo "    NOTE: you were added to the docker group. If docker commands below"
    echo "    fail with permission errors, log out/in (or run: newgrp docker)."
else
    echo "==> Docker already installed: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "==> Installing the docker compose plugin..."
    sudo apt-get update -qq
    sudo apt-get install -y docker-compose-plugin
fi

DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"
fi

# --- 2. .env -----------------------------------------------------------------
if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Created .env from .env.example"
    echo "    *** Edit .env and set LLM_PROVIDER + LLM_API_KEY before real runs ***"
else
    echo "==> .env already exists, keeping it"
fi

# --- 3. nginx ----------------------------------------------------------------
echo "==> Installing nginx config for $DOMAIN..."
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agent
sudo cp deploy/nginx-http-snippet.conf /etc/nginx/conf.d/agent-limit.conf
[ -L /etc/nginx/sites-enabled/agent ] || \
    sudo ln -s /etc/nginx/sites-available/agent /etc/nginx/sites-enabled/agent
sudo nginx -t
sudo systemctl reload nginx
echo "==> nginx reloaded"

# --- 4. app ------------------------------------------------------------------
echo "==> Building and starting the app (port $APP_PORT)..."
$DOCKER compose up -d --build
$DOCKER compose ps

cat <<EOF

==> Done.

Next steps:
  1. Edit .env: set LLM_PROVIDER and LLM_API_KEY (then: $DOCKER compose up -d)
  2. Point the DNS A record for $DOMAIN at this server (if not done already)
  3. TLS:  sudo apt install certbot python3-certbot-nginx
           sudo certbot --nginx -d $DOMAIN
  4. EC2 security group: open 80/443 to the world, keep $APP_PORT closed.

The app should already answer on http://$DOMAIN (and http://<server-ip>:$APP_PORT).
EOF
