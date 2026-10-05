#!/bin/sh
set -e

# Schema/Seed-Daten bei jedem Start aktualisieren (Volume kann von älterem Image stammen)
alembic upgrade head

exec "$@"
