#!/bin/sh
# Apply migrations against the (volume-backed) SQLite DB, then run the given command.
set -e

python manage.py migrate --noinput

exec "$@"
