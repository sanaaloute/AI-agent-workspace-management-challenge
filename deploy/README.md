# Deploying behind nginx on a VPS (e.g. AWS EC2)

Assumes: Ubuntu/Debian-ish box, nginx already installed, the app running on
`127.0.0.1:8000` (bare metal via `uvicorn ui.server:app`, or
`docker compose up` with the default `PORT=8000` mapping).

## 0. Scripted install (recommended)

```bash
bash script/deploy.sh    # fresh install: docker, .env, nginx config, app build
bash script/upgrade.sh   # later updates: pull code, rebuild app, refresh nginx
```

The manual steps below are exactly what `deploy.sh` automates.


## 1. Run the app

Bare metal (with a venv):

```bash
cd /opt/ai-file-agent            # wherever you cloned
cp .env.example .env             # fill in LLM_PROVIDER + LLM_API_KEY
uvicorn ui.server:app --host 127.0.0.1 --port 8000
```

Or Docker:

```bash
cp .env.example .env             # fill in LLM_PROVIDER + LLM_API_KEY
docker compose up -d --build     # serves 127.0.0.1:${PORT:-8000}
docker compose ps                # healthcheck should go "healthy"
```

For bare metal, put uvicorn under systemd or supervisor so it restarts on
crash/reboot (compose already does `restart: unless-stopped`).

## 2. Install the nginx config

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agent
sudo cp deploy/nginx-http-snippet.conf /etc/nginx/conf.d/agent-limit.conf
sudo ln -s /etc/nginx/sites-available/agent /etc/nginx/sites-enabled/agent
sudo nginx -t && sudo systemctl reload nginx
```

Edit `/etc/nginx/sites-available/agent` first: `server_name` is already set
to `agent.barkosem.com` — just make sure its DNS A record points at this VPS.
The rate-limit zone lives in the conf.d snippet because `limit_req_zone` is
only legal in the `http{}` context — if you ever move the server block into
a different include scheme, keep the two together.

## 3. TLS with certbot

```bash
sudo apt install certbot python3-certbot-nginx   # once
sudo certbot --nginx -d agent.barkosem.com
sudo nginx -t && sudo systemctl reload nginx
```

Certbot rewrites the server block to 443 and adds the HTTP->HTTPS redirect;
the commented SSL lines in `nginx.conf` show the equivalent manual form.

## Notes

- No secrets live in these files — the LLM API key stays in `.env`, which
  nginx never sees. The demo API itself is unauthenticated; abuse is bounded
  by the app's per-session token budget and the rate-limit zone above.
- Timeouts are generous (300 s) but mostly unnecessary: `/api/run` returns
  202 immediately and the UI polls `/api/trace` every second, so agent runs
  that take minutes never hold a single HTTP request open.
