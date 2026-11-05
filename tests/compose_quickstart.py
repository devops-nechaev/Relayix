"""Exercise downloaded Compose bundles against the published image without host helpers."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def run(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0] + ' (credential values omitted)')
    return result.stdout

for mode in ('local', 'external'):
    project = 'relayix-test-quickstart-' + secrets.token_hex(5)
    database_container = project + '-external-db'
    password = secrets.token_hex(24) + '@:#%/$'
    admin_password = 'Ab7!' + secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        path = Path(directory)
        source = 'compose.yaml' if mode == 'local' else 'compose.external.yaml'
        shutil.copyfile(ROOT / 'deploy' / source, path / 'compose.yaml')
        if os.environ.get('RELAYIX_TEST_IMAGE'):
            bundle = (path / 'compose.yaml').read_text().splitlines()
            index = next(i for i, line in enumerate(bundle) if line.startswith('    image: '))
            bundle[index] = '    image: ' + os.environ['RELAYIX_TEST_IMAGE']
            (path / 'compose.yaml').write_text('\n'.join(bundle) + '\n')
        # Match a new user's standalone download: only Compose and .env.
        (path / '.env').write_text(
            'COMPOSE_PROJECT_NAME=' + project + '\n'
            "POSTGRES_PASSWORD='" + password + "'\n"
            "ADMIN_PASSWORD='" + admin_password + "'\n"
            'BIND_ADDRESS=127.0.0.1\nPORT=0\n'
            'POSTGRES_HOST=external-db\nPOSTGRES_SSLMODE=disable\n')
        (path / '.env').chmod(0o600)
        # Ignore the host's unrelated deployment variables.
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ('COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_ENV_FILES')
                     and not k.startswith(('POSTGRES_', 'ADMIN_', 'TELEGRAM_', 'RELAYIX_'))
                     and k not in ('BIND_ADDRESS', 'PORT', 'COOKIE_SECURE', 'ALLOW_INSECURE_HTTP', 'RUST_LOG')}
        compose = ['docker', 'compose', '--project-directory', str(path), '-p', project]
        def dc(*args):
            return run(*compose, *args, cwd=path, env=clean_env)
        try:
            model = json.loads(dc('config', '--format', 'json'))
            assert set(model['services']) == ({'app', 'db'} if mode == 'local' else {'app'})
            assert model['services']['app']['environment']['POSTGRES_PASSWORD'].replace('$$', '$') == password
            if mode == 'external':
                assert not model.get('volumes')
                dc('create', 'app')
                network = run('docker', 'network', 'ls', '--filter', 'label=com.docker.compose.project=' + project,
                              '--format', '{{.Name}}').strip()
                assert network and '\n' not in network
                # This independent container represents a pre-existing database.
                (path / 'pg.env').write_text('POSTGRES_USER=relayix\nPOSTGRES_DB=relayix\nPOSTGRES_PASSWORD=' + password + '\n')
                run('docker', 'run', '-d', '--name', database_container, '--network', network,
                    '--network-alias', 'external-db', '--env-file', str(path / 'pg.env'), 'postgres:17.11-trixie')
                for attempt in range(60):
                    ready = subprocess.run(['docker', 'exec', database_container, 'pg_isready', '-U', 'relayix'], capture_output=True)
                    if ready.returncode == 0:
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError('External test database did not become ready')
            dc('up', '-d', '--wait', '--wait-timeout', '90')
            container = dc('ps', '-q', 'app').strip()
            runtime_env = json.loads(run('docker', 'inspect', container, '--format', '{{json .Config.Env}}'))
            assert 'POSTGRES_PASSWORD=' + password in runtime_env
            address = dc('port', 'app', '8080').strip()
            url = 'http://' + address
            for attempt in range(90):
                try:
                    with urllib.request.urlopen(url + '/healthz', timeout=2) as response:
                        health = json.load(response)
                    assert health['status'] == 'ok'
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(1)
            else:
                raise RuntimeError('Quick-start application did not become healthy')
            request = urllib.request.Request(url + '/api/auth/login',
                data=json.dumps({'username': 'admin', 'password': admin_password}).encode(),
                headers={'Content-Type': 'application/json', 'X-Relay-Client': 'web'})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200
            # Recreating the app must preserve data and the existing login.
            dc('up', '-d', '--no-deps', '--force-recreate', 'app')
            for attempt in range(60):
                try:
                    # An ephemeral host port can change when recreating the app.
                    address = dc('port', 'app', '8080').strip()
                    with urllib.request.urlopen('http://' + address + '/healthz', timeout=2) as response:
                        assert json.load(response)['status'] == 'ok'
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(1)
            else:
                raise RuntimeError('Recreated application did not become healthy')
            print('PASS: standalone ' + mode + ' Compose, special-character database password, bootstrap login and app recreation')
        finally:
            # Remove the independent DB before deleting the Compose network.
            subprocess.run(['docker', 'rm', '-f', '-v', database_container], capture_output=True)
            subprocess.run([*compose, 'down', '--volumes', '--remove-orphans'], cwd=path, env=clean_env, capture_output=True)
