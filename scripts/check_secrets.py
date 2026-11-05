#!/usr/bin/env python3
"""Check publication inputs without displaying values; --local inspects the configured deployment."""
from pathlib import Path
import json, os, re, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
paths=[p for p in git('ls-files','-z').decode().split('\0') if p]
errors=[]
for name in paths:
    p=Path(name)
    if (p.name.startswith('.env')) or p.name in {'deployment.json','credentials.json','compose.env'} or any(x in p.parts for x in ['backups','private','secrets']) or p.suffix in {'.dump','.pem','.key','.p12','.pfx','.session','.sqlite','.sqlite3'}:
        errors.append(f'Private file in index: {name}')
    content=git('show',':'+name)
    if any(marker in content for marker in [b'-----BEGIN '+kind+b'-----' for kind in [b'PRIVATE KEY',b'RSA PRIVATE KEY',b'OPENSSH PRIVATE KEY']]):
        errors.append(f'Private key marker: {name}')
# Compare with local deployment credentials; CI skips this when no external private configuration is available.
values=set()
config_path=Path(os.environ.get('RELAYIX_CONFIG_FILE',ROOT.parent/'private'/'relayix-config'/'deployment.json'))
if config_path.exists():
    for key,value in json.loads(config_path.read_text()).items():
        if any(term in key.upper() for term in ['PASSWORD','TOKEN','SECRET','API_HASH']) and isinstance(value,str) and len(value)>=12:values.add(value.encode())
if '--local' in sys.argv:
    fields={'bot_token','token','url','password','user','access_token','webhook_secret','api_hash','proxy_username','proxy_password','proxy_secret','chat_access_hash'}
    configs=json.loads(subprocess.check_output([sys.executable,str(ROOT/'scripts'/'database.py'),'psql','-X','-Atc',"SELECT COALESCE(jsonb_agg(config),'[]') FROM channels"],cwd=ROOT))
    for cfg in configs:
        for key,value in cfg.items():
            if key in fields and isinstance(value,str) and len(value)>=8:values.add(value.encode())
    for backup in (ROOT.parent/'private'/'relayix-backups').glob('*.env'):
        for line in backup.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and any(term in key.upper() for term in ['PASSWORD','TOKEN','SECRET','API_HASH']):
                value=value.strip().strip('"\'')
                if len(value)>=12 and 'CHANGE_ME' not in value:values.add(value.encode())
for name in paths:
    staged=git('show',':'+name)
    worktree=(ROOT/name).read_bytes() if (ROOT/name).is_file() else b''
    if any(value in staged or value in worktree for value in values):errors.append(f'Live credential match: {name}')
if errors:
    print('\n'.join(errors));raise SystemExit(1)
print(f'PASS: {len(paths)} indexed files; no private paths, private keys or local live credential matches. Run Gitleaks for pattern/history scanning.')
