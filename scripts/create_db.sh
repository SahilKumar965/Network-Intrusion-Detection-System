#!/usr/bin/env bash
# One-time local setup: creates the `nids` PostgreSQL user plus the app and test databases,
# using the password already in .env (it is never printed). Needs sudo for the postgres account.
# Safe to re-run: existing role/databases are kept and the role password is re-synced with .env.
set -euo pipefail
cd "$(dirname "$0")/.."

url=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
pw=$(printf '%s' "$url" | sed -E 's#^[^:]+://[^:]+:([^@]+)@.*#\1#')
[ -n "$pw" ] && [ "$pw" != "$url" ] || { echo "Could not read the password from DATABASE_URL in .env" >&2; exit 1; }

# Databases are copied from template0 with PostgreSQL's built-in C.UTF-8 locale: it does not depend on
# the OS C library, so it avoids "collation version mismatch" errors after OS upgrades and leaves
# the server's own template databases untouched.
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -v pw="$pw" <<'SQL'
SELECT 'CREATE ROLE nids LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nids') \gexec
ALTER ROLE nids PASSWORD :'pw';
SELECT format('CREATE DATABASE %I OWNER nids TEMPLATE template0 ENCODING ''UTF8'' LOCALE_PROVIDER builtin BUILTIN_LOCALE ''C.UTF-8''', d)
FROM unnest(ARRAY['nids', 'nids_test']) AS d
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = d) \gexec
SQL
echo "Role nids and databases nids, nids_test are ready."
