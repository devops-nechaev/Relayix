"""Validate both deployment models and TLS without touching running services."""
from pathlib import Path
import json,os,secrets,subprocess,sys,tempfile
from urllib.parse import urlsplit,unquote,parse_qs
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from deployment import database_settings
with tempfile.TemporaryDirectory(prefix='relayix-compose-model-') as directory:
 root=Path(directory)
 config={'POSTGRES_PASSWORD':secrets.token_hex(24)+'@:#%/\'"$','POSTGRES_USER':'test user','POSTGRES_DB':'test/db','COMPOSE_PROJECT_NAME':'relayix-test-model'}
 path=root/'deployment.json'
 def model(settings):
  path.write_text(json.dumps(settings));path.chmod(0o600)
  result=subprocess.run([str(ROOT/'scripts/compose.sh'),'--profile','tools','config','--format','json'],env={**os.environ,'RELAYIX_CONFIG_FILE':str(path)},capture_output=True,text=True,check=True)
  assert settings['POSTGRES_PASSWORD'] not in result.stderr
  return json.loads(result.stdout)
 local=model({**config,'RELAYIX_IMAGE':'unused-legacy-image:0.6.1'})
 assert local['services']['app']['image']=='ghcr.io/devops-nechaev/relayix:0.6.2'
 assert set(local['services'])=={'app','db','db-tools'}
 uri=urlsplit(local['services']['app']['environment']['DATABASE_URL'])
 assert uri.hostname=='db' and unquote(uri.password)==config['POSTGRES_PASSWORD']
 assert unquote(uri.username)==config['POSTGRES_USER'] and unquote(uri.path[1:])==config['POSTGRES_DB']
 assert local['services']['db-tools']['profiles']==['tools']
 remote={**config,'DATABASE_MODE':'external','POSTGRES_HOST':'host.docker.internal','POSTGRES_PORT':'6543'}
 external=model(remote)
 assert set(external['services'])=={'app','db-tools'} and not external.get('volumes')
 app=external['services']['app'];uri=urlsplit(app['environment']['DATABASE_URL'])
 assert not app.get('depends_on') and uri.hostname=='host.docker.internal' and uri.port==6543
 assert parse_qs(uri.query)['sslmode']==['verify-full']
 assert external['services']['db-tools']['environment']['PGSSLROOTCERT']=='system'
 assert any(item.replace('=',':')=='host.docker.internal:host-gateway' for item in app['extra_hosts'])
 ca=root/'postgres-ca.crt';ca.write_text('test certificate path only')
 custom=model({**remote,'POSTGRES_SSLROOTCERT':str(ca)})
 assert parse_qs(urlsplit(custom['services']['app']['environment']['DATABASE_URL']).query)['sslrootcert']==['/run/relayix/postgres-ca.crt']
 for service in ['app','db-tools']:
  assert custom['services'][service]['volumes'][0]['read_only'] is True
  assert custom['services'][service]['volumes'][0]['source']==str(ca)
 for bad in [{**remote,'POSTGRES_HOST':''},{**remote,'POSTGRES_PORT':'0'},{**remote,'POSTGRES_HOST':'https://db.example.org'},{**remote,'DATABASE_MODE':'wrong'}]:
  try:database_settings(bad)
  except SystemExit as error:assert bad['POSTGRES_PASSWORD'] not in str(error)
  else:raise AssertionError('Invalid database settings were accepted')
 blank=root/'external-template.json'
 clean_env={k:v for k,v in os.environ.items() if k not in ['POSTGRES_PASSWORD','POSTGRES_HOST','DATABASE_MODE']}
 subprocess.run([sys.executable,str(ROOT/'scripts/write_config.py'),str(blank),'--database','external','--generate'],env=clean_env,capture_output=True,check=True)
 template=json.loads(blank.read_text())
 assert template['DATABASE_MODE']=='external' and template['POSTGRES_PASSWORD']=='' and template['ADMIN_PASSWORD']
print('PASS: local/external Compose selection, no bundled remote DB/volume, special-character credentials, host gateway, TLS CA mounts and external config template')
