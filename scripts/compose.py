#!/usr/bin/env python3
"""Load private deployment configuration outside the checkout, then run Compose."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
path=Path(os.environ.get('RELAYIX_CONFIG_FILE',ROOT.parent/'private'/'relayix-config'/'deployment.json')).resolve()
if path.is_relative_to(ROOT):
    raise SystemExit('Deployment configuration must be outside the source checkout')
try:
    config=json.loads(path.read_text())
except (OSError,ValueError):
    raise SystemExit('Private deployment configuration unavailable; set RELAYIX_CONFIG_FILE') from None
if not isinstance(config,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in config.items()):
    raise SystemExit('Deployment configuration must be a JSON object of string values')
if any('\x00' in k+v or '\n' in k+v or '\r' in k+v for k,v in config.items()):
    raise SystemExit('Invalid multiline deployment configuration')
env={**os.environ,**config}
if config.get('POSTGRES_PASSWORD'):
    env['RELAYIX_DATABASE_URL']='postgres://relaynest:'+quote(config['POSTGRES_PASSWORD'],safe='')+'@db:5432/relaynest'
if 'RELAYIX_IMAGE_OVERRIDE' in os.environ:env['RELAYIX_IMAGE']=os.environ['RELAYIX_IMAGE_OVERRIDE']
if 'RELAYIX_COMPOSE_PROJECT' in os.environ:env['COMPOSE_PROJECT_NAME']=os.environ['RELAYIX_COMPOSE_PROJECT']
os.chdir(ROOT)
# Disable Compose's automatic .env discovery entirely. Secrets travel via the child environment.
os.execvpe('docker',['docker','compose','--project-directory',str(ROOT),'--env-file',os.devnull,*sys.argv[1:]],env)
