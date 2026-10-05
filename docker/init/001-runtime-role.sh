#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=database_name="$POSTGRES_DB" \
  --set=reader_password="$MIMIC_READER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE mimic_reader LOGIN PASSWORD %L', :'reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mimic_reader')\gexec
GRANT CONNECT ON DATABASE :"database_name" TO mimic_reader;
GRANT USAGE ON SCHEMA public TO mimic_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mimic_reader;
ALTER ROLE mimic_reader SET default_transaction_read_only = on;
SQL
