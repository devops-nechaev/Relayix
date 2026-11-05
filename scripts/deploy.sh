#!/usr/bin/env bash
# Run on the deployment host; GitHub CI never invokes this script.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RELAYIX_DEPLOY_IMAGE:?Set an explicit image reference}"
: "${RELAYIX_EXPECTED_VERSION:?Set the version expected from healthz}"
[[ "$RELAYIX_EXPECTED_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
export COMPOSE_PROJECT_NAME="${RELAYIX_COMPOSE_PROJECT:-relayix}"
export RELAYIX_HEALTH_URL="${RELAYIX_HEALTH_URL:-http://127.0.0.1:8080/healthz}"
# Image references and versions are arguments, never shell code.
[[ "$RELAYIX_DEPLOY_IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]+$ ]]
export RELAYIX_CONFIG_FILE="${RELAYIX_CONFIG_FILE:-$PWD/../private/relayix-config/deployment.json}"
test -f "$RELAYIX_CONFIG_FILE"
compose=("$PWD/scripts/compose.sh")
unset RELAYIX_IMAGE
umask 077
backup_root="${RELAYIX_BACKUP_DIR:-../private/relayix-backups}"
mkdir -p "$backup_root"
chmod 700 "$backup_root"
stamp="$(date -u +%Y%m%d-%H%M%S)-$$"
backup_env="$backup_root/config-before-deploy-$stamp.json"
cp "$RELAYIX_CONFIG_FILE" "$backup_env"
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_root/db-before-deploy-$stamp.dump"
# Pull before changing the running service or its persistent configuration.
RELAYIX_IMAGE_OVERRIDE="$RELAYIX_DEPLOY_IMAGE" "${compose[@]}" pull app
export RELAYIX_DEPLOY_BACKUP_ENV="$backup_env"
rollback() {
  status=$?
  trap - ERR
  cp "$RELAYIX_DEPLOY_BACKUP_ENV" "$RELAYIX_CONFIG_FILE"
  chmod 600 "$RELAYIX_CONFIG_FILE"
  "${compose[@]}" up -d --no-deps app || true
  echo 'Deployment failed; previous environment restored and previous app restart requested.' >&2
  exit "$status"
}
trap rollback ERR
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
path=Path(os.environ['RELAYIX_CONFIG_FILE'])
config=json.loads(path.read_text())
candidate=os.environ.get('RELAYIX_DEPLOY_CONFIG_CANDIDATE')
if candidate:
    incoming=json.loads(Path(candidate).read_text())
    if incoming.get('POSTGRES_PASSWORD')!=config.get('POSTGRES_PASSWORD'):
        raise SystemExit('GitHub database secret differs from the active database password; refusing deployment')
    config=incoming
config['RELAYIX_IMAGE']=os.environ['RELAYIX_DEPLOY_IMAGE']
config['COMPOSE_PROJECT_NAME']=os.environ['COMPOSE_PROJECT_NAME']
path.write_text(json.dumps(config,indent=2)+'\n');path.chmod(0o600)
PY
"${compose[@]}" up -d --no-deps app
python3 - <<'PY'
import json, os, time
from urllib.request import urlopen
for attempt in range(30):
    try:
        with urlopen(os.environ['RELAYIX_HEALTH_URL'], timeout=3) as response:
            health = json.load(response)
        if health.get('status') == 'ok' and health.get('version') == os.environ['RELAYIX_EXPECTED_VERSION']:
            print('Deployment healthy: Relayix ' + health['version'])
            break
    except Exception:
        pass
    if attempt == 29:
        raise SystemExit('Expected healthy application version did not start')
    time.sleep(1)
PY
trap - ERR
