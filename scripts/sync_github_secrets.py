#!/usr/bin/env python3
"""Upload private deployment credentials to GitHub Secrets via authenticated gh."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--repo',default='devops-nechaev/Relayix');args=parser.parse_args()
if not shutil.which('gh'):raise SystemExit('An authenticated GitHub CLI is required; no secrets were uploaded')
root=Path(__file__).resolve().parents[1]
config=json.loads(Path(os.environ.get('RELAYIX_CONFIG_FILE',root.parent/'private'/'relayix-config'/'deployment.json')).read_text())
status=subprocess.run(['gh','auth','status'],capture_output=True)
if status.returncode:raise SystemExit('GitHub authentication is required; no secrets were uploaded')
# Do not pass secret bodies on argv or print API responses.
result=subprocess.run(['gh','api',f'repos/{args.repo}/environments/production'],capture_output=True)
if result.returncode:
    if b'404' not in result.stderr:raise SystemExit('Cannot inspect production environment; no secrets were uploaded')
    result=subprocess.run(['gh','api','--method','PUT',f'repos/{args.repo}/environments/production'],capture_output=True)
    if result.returncode:raise SystemExit('Cannot create production environment; no secrets were uploaded')
for key in ['POSTGRES_PASSWORD','ADMIN_TOKEN','ADMIN_PASSWORD']:
    value=config.get(key)
    if not value:raise SystemExit('Required private deployment value missing')
    result=subprocess.run(['gh','secret','set','RELAYIX_'+key,'--repo',args.repo,'--env','production'],input=value,text=True,capture_output=True)
    if result.returncode:raise SystemExit('GitHub rejected a secret update; secret values omitted')
    print('Configured production secret RELAYIX_'+key)
