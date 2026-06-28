#!/usr/bin/env bash
# ArgusAI bare-metal (systemd) deploy — safe pull → migrate → restart → verify.
#
# Codifies the correct deploy sequence so deploys cannot skip database
# migrations (the root cause of the 2026-06-28 login 500: a refresh-token
# migration was never applied to prod) and so health is actually verified
# before the deploy is declared done (a crash loop can leave systemd reporting
# "active" mid-restart — see the NRestarts check below).
#
# Usage (run on the production server, e.g. argusai.bengtson.local):
#   sudo ./scripts/deploy-baremetal.sh
#
# Env overrides:
#   APP_DIR (default /ArgusAI)   BACKEND_SVC (default argusai-backend)
#   FRONTEND_SVC (default argusai-frontend)   HEALTH_URL (default http://127.0.0.1:8000/health)
#   REBUILD_FRONTEND=1 to force a frontend npm build + restart
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/ArgusAI}"
BACKEND_SVC="${BACKEND_SVC:-argusai-backend}"
FRONTEND_SVC="${FRONTEND_SVC:-argusai-frontend}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mDEPLOY FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

cd "$APP_DIR" || die "APP_DIR $APP_DIR not found"

OLD_REF="$(git rev-parse --short HEAD)"
log "Current revision: $OLD_REF"

# --- 1. Pull ---------------------------------------------------------------
log "Pulling latest (fast-forward only)"
git pull --ff-only || die "git pull failed (diverged history?)"
NEW_REF="$(git rev-parse --short HEAD)"
log "New revision: $NEW_REF"
if [ "$OLD_REF" = "$NEW_REF" ]; then
  log "No new commits. Continuing (will still verify migrations + health)."
fi

# Detect what changed so we only rebuild the frontend when needed.
CHANGED="$(git diff --name-only "$OLD_REF" "$NEW_REF" 2>/dev/null || true)"
DEPS_CHANGED="$(echo "$CHANGED" | grep -E '^backend/requirements.txt$' || true)"
FRONTEND_CHANGED="$(echo "$CHANGED" | grep -E '^frontend/' || true)"

# --- 2. Backend deps + MIGRATION GATE -------------------------------------
cd "$APP_DIR/backend"
# shellcheck disable=SC1091
source venv/bin/activate || die "could not activate backend venv"

if [ -n "$DEPS_CHANGED" ]; then
  log "requirements.txt changed — installing backend deps"
  pip install -r requirements.txt || die "pip install failed"
fi

# Back up the SQLite DB (if SQLite) before migrating — instant rollback point.
DB_URL="$(python -c 'from app.core.config import settings; print(settings.DATABASE_URL)')"
if [[ "$DB_URL" == sqlite* ]]; then
  DB_PATH="${DB_URL#sqlite:///}"
  if [ -f "$DB_PATH" ]; then
    BK="${DB_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$DB_PATH" "$BK" && log "DB backed up: $BK"
  fi
fi

log "Applying database migrations (alembic upgrade head) — THE GATE"
alembic upgrade head || die "alembic upgrade failed — NOT restarting (DB unchanged-safe)"

# --- 3. Frontend (only if changed or forced) ------------------------------
if [ -n "$FRONTEND_CHANGED" ] || [ "${REBUILD_FRONTEND:-0}" = "1" ]; then
  log "Frontend changed — npm ci + build"
  cd "$APP_DIR/frontend"
  npm ci || die "npm ci failed"
  npm run build || die "frontend build failed"
fi

# --- 4. Restart services ---------------------------------------------------
log "Restarting $BACKEND_SVC"
systemctl restart "$BACKEND_SVC" || die "failed to restart $BACKEND_SVC"
if [ -n "$FRONTEND_CHANGED" ] || [ "${REBUILD_FRONTEND:-0}" = "1" ]; then
  log "Restarting $FRONTEND_SVC"
  systemctl restart "$FRONTEND_SVC" || die "failed to restart $FRONTEND_SVC"
fi

# --- 5. Verify health (poll /health AND confirm no crash loop) -------------
log "Verifying backend health (a bare 'active' can lie mid-restart)"
R0="$(systemctl show "$BACKEND_SVC" -p NRestarts --value)"
HEALTHY=0
for i in $(seq 1 30); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null)" = "200" ]; then
    HEALTHY=1; log "Health 200 after ~$((i*3))s"; break
  fi
  sleep 3
done
[ "$HEALTHY" = "1" ] || die "health never returned 200 — backend likely crash-looping. Inspect: journalctl -u $BACKEND_SVC -n 50"

sleep 12
R1="$(systemctl show "$BACKEND_SVC" -p NRestarts --value)"
[ "$R0" = "$R1" ] || die "NRestarts climbing ($R0 -> $R1) — crash loop after startup. Inspect: journalctl -u $BACKEND_SVC -n 50"

log "Deploy OK: $OLD_REF -> $NEW_REF, migrations at head, $BACKEND_SVC healthy and stable."
