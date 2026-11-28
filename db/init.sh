#!/bin/sh
set -eu

# These values appear in both a SQL string literal and a database URL.
for password in "$ATTENDANCE_SQL_PASSWORD" "$TRIP_OPS_SQL_PASSWORD"; do
    case "$password" in
        ''|*[!a-zA-Z0-9_-]*)
            echo "Service SQL passwords must contain only letters, digits, underscores or hyphens." >&2
            exit 1
            ;;
    esac
done
unset password

exec /opt/mssql-tools18/bin/sqlcmd -S sql -U sa -C -b -l 10 -i /init/init.sql
