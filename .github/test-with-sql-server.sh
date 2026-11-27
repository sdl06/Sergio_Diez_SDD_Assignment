#!/usr/bin/env bash
set -euo pipefail

service=${1:?Pass attendance or trip-ops}
case "$service" in
  attendance|trip-ops) ;;
  *) echo "Unknown SchoolRun service: $service" >&2; exit 1 ;;
esac
image=${2:-schoolrun-$service}

work=$(mktemp -d)
test_id="schoolrun-ci-$service-$$"
sql_container="$test_id-sql"
test_image="$test_id-test"
network=""

cleanup() {
  docker rm -fv "$sql_container" >/dev/null 2>&1 || true
  if [[ -n "$network" ]]; then
    docker network rm "$network" >/dev/null 2>&1 || true
  fi
  docker image rm "$test_image" >/dev/null 2>&1 || true
  rm -f "$work/sql-init.log"
  rmdir "$work"
}
trap cleanup EXIT

# Install coverage only in the temporary test image.
docker build --build-arg "BASE_IMAGE=$image" -t "$test_image" -f - "$work" <<'DOCKERFILE'
ARG BASE_IMAGE=python:3.14.2-slim-bookworm
FROM ${BASE_IMAGE}
USER root
RUN python -m pip install --no-cache-dir coverage==7.16.1
USER app
DOCKERFILE

network=$(docker network create --internal "$test_id")
export MSSQL_SA_PASSWORD
MSSQL_SA_PASSWORD="SchoolRun1-$(openssl rand -hex 24)"
if [[ ${GITHUB_ACTIONS:-} == true ]]; then
  echo "::add-mask::$MSSQL_SA_PASSWORD"
fi
docker run -d --platform linux/amd64 --name "$sql_container" --network "$network" --network-alias sql \
  -e ACCEPT_EULA=Y -e MSSQL_PID=Developer -e MSSQL_SA_PASSWORD \
  mcr.microsoft.com/mssql/server:2022-latest >/dev/null

deadline=$((SECONDS + 120))
until docker exec "$sql_container" sh -c '
  SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd \
    -S localhost -U sa -C -b -l 2 -Q "CREATE DATABASE schoolrun_ci"
' > "$work/sql-init.log" 2>&1; do
  if (( SECONDS >= deadline )); then
    cat "$work/sql-init.log"
    docker logs --tail 30 "$sql_container"
    exit 1
  fi
  sleep 2
done

export DATABASE_URL="mssql://sa:$MSSQL_SA_PASSWORD@sql:1433/schoolrun_ci"
docker run --rm --network "$network" -e DATABASE_URL \
  -e 'SQL_EXTRA_PARAMS=Encrypt=yes;TrustServerCertificate=yes' \
  -e COVERAGE_RCFILE=/tmp/coverage.ini -e COVERAGE_FILE=/tmp/schoolrun.coverage \
  -v "$PWD/.github/coverage.ini:/tmp/coverage.ini:ro" \
  --entrypoint sh "$test_image" -ec '
    python -m coverage run manage.py test --noinput
    python -m coverage report
  '
