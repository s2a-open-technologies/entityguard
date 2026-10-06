#!/bin/sh
set -e

# Als root gestartet (Standard): Besitzer von /app/data korrigieren und auf den
# unprivilegierten Benutzer wechseln. Nötig, weil Volumes aus älteren Images
# (die als root liefen) root-eigene Dateien enthalten -> sonst "readonly database".
if [ "$(id -u)" = "0" ]; then
    find /app/data -xdev ! -user entityguard -exec chown -h entityguard:entityguard {} +
    exec setpriv --reuid=entityguard --regid=entityguard --init-groups \
        /usr/local/bin/docker-entrypoint.sh "$@"
fi

# Schema/Seed-Daten bei jedem Start aktualisieren (Volume kann von älterem Image stammen)
alembic upgrade head

exec "$@"
