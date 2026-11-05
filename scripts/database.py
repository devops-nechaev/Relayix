#!/usr/bin/env python3
"""Run an explicitly requested PostgreSQL client using the active private settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
from deployment import ROOT, CA_PATH, read_config, database_settings

if len(sys.argv) < 2 or sys.argv[1] not in ('psql', 'pg_dump', 'pg_isready'):
    raise SystemExit('Usage: scripts/database.py {psql|pg_dump|pg_isready} [arguments]')
config = read_config()
db = database_settings(config)
result = subprocess.run([str(ROOT / 'scripts/compose.sh'), 'ps', '-a', '-q', 'app'],
                        capture_output=True, text=True)
container = result.stdout.strip()
if result.returncode or not container or '\n' in container:
    raise SystemExit('Cannot find the active Relayix app container')
result = subprocess.run(['docker', 'inspect', container, '--format', '{{json .NetworkSettings.Networks}}'],
                        capture_output=True, text=True)
try:
    networks = json.loads(result.stdout)
    network = next(iter(networks))
except (ValueError, StopIteration, TypeError):
    raise SystemExit('Cannot determine the app database network') from None
if result.returncode:
    raise SystemExit('Cannot inspect the app database network')
env = {**os.environ, 'PGHOST': db['host'], 'PGPORT': db['port'], 'PGUSER': db['user'],
       'PGDATABASE': db['database'], 'PGPASSWORD': db['password'], 'PGSSLMODE': db['sslmode'],
       'PGSSLROOTCERT': CA_PATH if db['ca'] else ('system' if db['sslmode'] == 'verify-full' else '')}
args = ['docker', 'run', '--rm', '-i', '--network', network]
for key in ('PGHOST', 'PGPORT', 'PGUSER', 'PGDATABASE', 'PGPASSWORD', 'PGSSLMODE', 'PGSSLROOTCERT'):
    args += ['-e', key]
if db['ca']:
    args += ['--mount', 'type=bind,source=' + db['ca'] + ',target=' + CA_PATH + ',readonly']
args += [config.get('POSTGRES_CLIENT_IMAGE', 'postgres:17.11-trixie'), *sys.argv[1:]]
os.execvpe('docker', args, env)
