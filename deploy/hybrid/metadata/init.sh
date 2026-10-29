#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=mb_password="$METABASE_METADATA_PASSWORD" --set=ss_password="$SUPERSET_METADATA_PASSWORD" <<'SQL'
CREATE ROLE hybrid_metabase LOGIN PASSWORD :'mb_password';
CREATE ROLE hybrid_superset LOGIN PASSWORD :'ss_password';
CREATE DATABASE hybrid_metabase OWNER hybrid_metabase;
CREATE DATABASE hybrid_superset OWNER hybrid_superset;
REVOKE ALL ON DATABASE hybrid_metabase FROM PUBLIC;
REVOKE ALL ON DATABASE hybrid_superset FROM PUBLIC;
SQL
