#!/usr/bin/env bash
# Idempotent local Postgres bootstrap for Five Guys Telegram bot.
set -euo pipefail

CLUSTER_VERSION="$(ls /etc/postgresql 2>/dev/null | sort -V | tail -1 || true)"
if [[ -z "${CLUSTER_VERSION}" ]]; then
  echo "PostgreSQL is not installed."
  exit 1
fi

if ! pg_isready -q 2>/dev/null; then
  sudo pg_ctlcluster "${CLUSTER_VERSION}" main start || sudo service postgresql start
fi

# Wait briefly for readiness
for _ in $(seq 1 30); do
  if pg_isready -q; then
    break
  fi
  sleep 0.5
done
pg_isready -q

sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fiveguys') THEN
    CREATE ROLE fiveguys LOGIN PASSWORD 'fiveguys' SUPERUSER;
  END IF;
END
$$;

SELECT 'CREATE DATABASE fiveguys OWNER fiveguys'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'fiveguys')\gexec
SQL

echo "Postgres ready: postgresql://fiveguys:fiveguys@localhost:5432/fiveguys"
