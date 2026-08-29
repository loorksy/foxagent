#!/usr/bin/env bash
# Add a new nginx vhost for FoxAgent. Never edits other site files.
set -euo pipefail

DOMAIN="${FOXAGENT_DOMAIN:-foxagent.lork.cloud}"
UPSTREAM="${FOXAGENT_UPSTREAM:-127.0.0.1:18180}"
APP_DIR="${FOXAGENT_DIR:-/opt/foxagent}"
SRC="${APP_DIR}/deploy/nginx/foxagent.lork.cloud.conf"
DEST="/etc/nginx/sites-available/${DOMAIN}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi

install -m 0644 "$SRC" "$DEST"
ln -sfn "$DEST" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t
systemctl reload nginx

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
  --register-unsafely-without-email || true

nginx -t
systemctl reload nginx
echo "Bound https://${DOMAIN} -> ${UPSTREAM}"
