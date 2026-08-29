#!/usr/bin/env bash
# Isolated FoxAgent install. Never touches other compose projects, nginx sites, or Traefik files.
set -euo pipefail

APP_DIR="${FOXAGENT_DIR:-/opt/foxagent}"
DEFAULT_PORT="${FOXAGENT_HTTP_PORT:-18180}"
REPO_URL="${FOXAGENT_REPO:-https://github.com/loorksy/foxagent.git}"
REPO_REF="${FOXAGENT_REF:-main}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

pick_free_port() {
  local candidates=("$DEFAULT_PORT" 18182 18280 19180 27180)
  local used
  used="$(ss -H -tln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -u || true)"
  local p
  for p in "${candidates[@]}"; do
    if ! echo "$used" | grep -qx "$p"; then
      echo "$p"
      return 0
    fi
  done
  echo "No candidate host port is free (tried ${candidates[*]})" >&2
  return 1
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the VPS" >&2
  exit 1
fi

if ! need_cmd docker; then
  echo "Docker is required but will not be installed automatically (to avoid touching the host)." >&2
  echo "Install Docker yourself, then re-run." >&2
  exit 1
fi

PORT="$(pick_free_port)"
echo "Using unused host port ${PORT}"

mkdir -p "$APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  if [[ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" && ! -f "$APP_DIR/deploy/docker-compose.yml" ]]; then
    echo "$APP_DIR exists and is not a FoxAgent checkout. Aborting to avoid overwriting." >&2
    exit 1
  fi
  git clone --branch "$REPO_REF" --single-branch "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin "$REPO_REF"
  git -C "$APP_DIR" checkout "$REPO_REF"
  git -C "$APP_DIR" pull --ff-only origin "$REPO_REF" || true
fi

cd "$APP_DIR"
PUBLIC_IP="$(curl -4 -sS --max-time 5 https://ifconfig.me || hostname -I | awk '{print $1}')"
export FOXAGENT_HTTP_PORT="$PORT"
export FOXAGENT_PUBLIC_ORIGIN="http://${PUBLIC_IP}:${PORT}"

cd deploy
docker compose -p foxagent up -d --build

echo
echo "FoxAgent is isolated under ${APP_DIR}"
echo "Compose project: foxagent"
echo "URL: http://${PUBLIC_IP}:${PORT}"
echo "Health: http://${PUBLIC_IP}:${PORT}/api/health"
