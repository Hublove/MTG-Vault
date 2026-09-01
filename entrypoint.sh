#!/bin/sh
# Apply migrations against the (volume-backed) SQLite DB, then run the given command.
set -e

# Opt-in redeploy-on-restart for the NAS: AUTO_DEPLOY=true makes a plain
# container stop/start pull the latest pushed commit before serving it, so
# there's no separate SSH-in-and-rebuild step. Unset/false locally, so the
# dev docker-compose.yml (bind-mounted working tree, uncommitted edits) is
# never touched by this.
if [ "${AUTO_DEPLOY:-}" = "true" ]; then
    echo "AUTO_DEPLOY: resetting /app to origin/main..."
    git config --global --add safe.directory /app
    if [ -n "${GIT_PAT:-}" ]; then
        git remote set-url origin "https://${GIT_PAT}@github.com/Hublove/MTG-Vault.git"
    fi
    git fetch origin main
    git reset --hard origin/main
    pip install --no-cache-dir -r requirements.txt
fi

python manage.py migrate --noinput

exec "$@"
