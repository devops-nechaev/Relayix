"""Private deployment settings shared by Compose and operational scripts."""
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode
import ipaddress

ROOT = Path(__file__).resolve().parents[1]
CA_PATH = '/run/relayix/postgres-ca.crt'


def read_config():
    path = Path(os.environ.get('RELAYIX_CONFIG_FILE', ROOT.parent / 'private/relayix-config/deployment.json')).resolve()
    if path.is_relative_to(ROOT):
        raise SystemExit('Deployment configuration must be outside the source checkout')
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        raise SystemExit('Private deployment configuration unavailable; set RELAYIX_CONFIG_FILE') from None
    if not isinstance(config, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in config.items()):
        raise SystemExit('Deployment configuration must be a JSON object of string values')
    if any(any(char in k + v for char in '\x00\n\r') for k, v in config.items()):
        raise SystemExit('Invalid multiline deployment configuration')
    return config


def database_settings(config):
    mode = config.get('DATABASE_MODE', 'local')
    if mode not in ('local', 'external'):
        raise SystemExit('DATABASE_MODE must be local or external')
    host = 'db' if mode == 'local' else config.get('POSTGRES_HOST', '').strip()
    if not host or any(char.isspace() or char in '/@?#\\' for char in host):
        raise SystemExit('Set POSTGRES_HOST to the external database hostname or IP address')
    host = host.removeprefix('[').removesuffix(']')
    if ':' in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise SystemExit('POSTGRES_HOST must contain only a hostname or IP; set POSTGRES_PORT separately') from None
    try:
        port = 5432 if mode == 'local' else int(config.get('POSTGRES_PORT', '5432'))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit('POSTGRES_PORT must be between 1 and 65535') from None
    user = config.get('POSTGRES_USER', 'relayix')
    database = config.get('POSTGRES_DB', 'relayix')
    password = config.get('POSTGRES_PASSWORD', '')
    if not user or not database or not password:
        raise SystemExit('Set POSTGRES_USER, POSTGRES_DB and POSTGRES_PASSWORD in the private configuration')
    sslmode = 'disable' if mode == 'local' else config.get('POSTGRES_SSLMODE') or 'verify-full'
    if sslmode not in ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'):
        raise SystemExit('Invalid POSTGRES_SSLMODE')
    ca = config.get('POSTGRES_SSLROOTCERT', '') if mode == 'external' else ''
    if ca:
        if not Path(ca).expanduser().is_absolute():
            raise SystemExit('POSTGRES_SSLROOTCERT must be an absolute path on the Docker host')
        ca = str(Path(ca).expanduser().resolve())
        if not Path(ca).is_file():
            raise SystemExit('POSTGRES_SSLROOTCERT must name an existing CA certificate file on the Docker host')
    if sslmode == 'verify-ca' and not ca:
        raise SystemExit('POSTGRES_SSLMODE=verify-ca requires POSTGRES_SSLROOTCERT')
    query = {'sslmode': sslmode}
    if ca:
        query['sslrootcert'] = CA_PATH
    uri_host = '[' + host + ']' if ':' in host else host
    url = 'postgres://' + quote(user, safe='') + ':' + quote(password, safe='') + '@' + uri_host + ':' + str(port) + '/' + quote(database, safe='') + '?' + urlencode(query)
    return {'mode': mode, 'host': host, 'port': str(port), 'user': user, 'database': database, 'password': password,
            'sslmode': sslmode, 'ca': ca, 'url': url}


def compose_environment(config):
    db = database_settings(config)
    env = {**os.environ, **config}
    env.update(RELAYIX_DATABASE_URL=db['url'], PGHOST=db['host'], PGPORT=db['port'], PGUSER=db['user'],
               PGDATABASE=db['database'], PGPASSWORD=db['password'], PGSSLMODE=db['sslmode'],
               PGSSLROOTCERT=CA_PATH if db['ca'] else ('system' if db['sslmode'] == 'verify-full' else ''))
    if 'RELAYIX_IMAGE_OVERRIDE' in os.environ:
        env['RELAYIX_IMAGE'] = os.environ['RELAYIX_IMAGE_OVERRIDE']
    if 'RELAYIX_COMPOSE_PROJECT' in os.environ:
        env['COMPOSE_PROJECT_NAME'] = os.environ['RELAYIX_COMPOSE_PROJECT']
    files = [ROOT / ('compose.yaml' if db['mode'] == 'local' else 'compose.external.yaml')]
    if db['ca']:
        env['POSTGRES_SSLROOTCERT'] = db['ca']
        files.append(ROOT / 'compose.tls.yaml')
    return env, files
