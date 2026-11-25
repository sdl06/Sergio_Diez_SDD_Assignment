#!/usr/bin/env bash
set -euo pipefail

case "${SERVICE:?Set SERVICE to the built service name}" in
  attendance) probe_path=/api/trips/1/attendance/ ;;
  trip_ops) probe_path=/accounts/login/ ;;
  *) echo "Unknown service: $SERVICE" >&2; exit 1 ;;
esac

sql_image=mcr.microsoft.com/mssql/server:2022-latest
zap_image=ghcr.io/zaproxy/zaproxy:stable

docker pull --platform linux/amd64 "$sql_image"
docker pull "$zap_image"

network=$(docker network create --internal "schoolrun-dast-${GITHUB_RUN_ID:-$$}-$SERVICE")
suffix=${network:0:12}
sql_container="schoolrun-sql-$suffix"
app_container="schoolrun-app-$suffix"
zap_container="schoolrun-zap-$suffix"

cleanup() {
  docker rm -f -v "$zap_container" "$app_container" "$sql_container" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null
}
trap cleanup EXIT

export MSSQL_SA_PASSWORD
MSSQL_SA_PASSWORD="SchoolRun1-$(openssl rand -hex 24)"
if [[ ${GITHUB_ACTIONS:-} == true ]]; then
  echo "::add-mask::$MSSQL_SA_PASSWORD"
fi
docker run --detach --platform linux/amd64 --name "$sql_container" --network "$network" --network-alias sql \
  --env ACCEPT_EULA=Y --env MSSQL_PID=Developer --env MSSQL_SA_PASSWORD "$sql_image"

create_database() {
  docker exec "$sql_container" sh -c '
    SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd \
      -S localhost -U sa -C -b -l 2 -Q "CREATE DATABASE schoolrun_ci"
  '
}

wait_until_ready() {
  local deadline=$((SECONDS + 120))
  until "$@" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 2
  done
}

if ! wait_until_ready create_database; then
  docker logs "$sql_container"
  exit 1
fi

export DATABASE_URL="mssql://sa:$MSSQL_SA_PASSWORD@sql:1433/schoolrun_ci"
docker run --detach --name "$app_container" --network "$network" --network-alias schoolrun-app \
  --env DATABASE_URL --env 'SQL_EXTRA_PARAMS=Encrypt=yes;TrustServerCertificate=yes' \
  --env 'DJANGO_ALLOWED_HOSTS=localhost,schoolrun-app' --env DJANGO_DEBUG=false \
  "schoolrun-$SERVICE"
unset DATABASE_URL MSSQL_SA_PASSWORD

if ! wait_until_ready docker exec "$app_container" curl --fail --silent --max-time 3 http://localhost:8000/health; then
  docker logs "$app_container"
  exit 1
fi

scan_status=0
docker run --name "$zap_container" --network "$network" \
  --env "ZAP_PROBE_PATH=$probe_path" \
  --volume "$PWD/.github/zap-passive.yml:/zap/plan.yml:ro" \
  "$zap_image" zap.sh -cmd -silent -autorun /zap/plan.yml || scan_status=$?
docker cp "$zap_container:/tmp/zap-report.html" "${RUNNER_TEMP:?Set the runner temporary directory}/zap-report.html"
exit "$scan_status"
