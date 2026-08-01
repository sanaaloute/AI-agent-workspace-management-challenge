FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first for layer caching (no dev deps in requirements.txt).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code. Tests are not needed at runtime (excluded via .dockerignore).
COPY agent/ agent/
COPY ui/ ui/
COPY cli.py .

# Seed workspaces (the compose file bind-mounts host dirs over these, so the
# image copies only matter when run without the mounts).
COPY workspace/ workspace/
COPY workspace_original/ workspace_original/

# Run as non-root; the bind-mounted workspaces must stay writable by uid 1000.
RUN useradd --create-home --uid 1000 agent && chown -R agent:agent /app
USER agent

EXPOSE 8000

# Inside the container the app always listens on 8000; the host-side port is
# chosen in docker-compose.yml (${PORT:-8000}:8000).
CMD ["uvicorn", "ui.server:app", "--host", "0.0.0.0", "--port", "8000"]
