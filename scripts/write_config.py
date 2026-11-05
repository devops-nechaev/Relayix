#!/usr/bin/env python3
"""Render a private candidate config from GitHub Secrets/Variables or fresh values."""
import argparse
import json
import os
from pathlib import Path
import secrets

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('output');parser.add_argument('--generate',action='store_true');parser.add_argument('--base');args=parser.parse_args()
path=Path(args.output).resolve()
if path.is_relative_to(ROOT):raise SystemExit('Configuration output must be outside the source checkout')
if path.exists():raise SystemExit('Refusing to overwrite existing configuration')
config=json.loads((ROOT/'config'/'deployment.example.json').read_text())
if args.base:
    base=Path(args.base).resolve()
    if base.is_relative_to(ROOT):raise SystemExit('Base config must be outside checkout')
    config.update(json.loads(base.read_text()))
keys=set(config)|{'POSTGRES_PASSWORD','ADMIN_TOKEN','ADMIN_PASSWORD'}
for key in keys:
    if os.environ.get(key):config[key]=os.environ[key]
if args.generate:
    config.setdefault('POSTGRES_PASSWORD',secrets.token_hex(32))
    config.setdefault('ADMIN_TOKEN',secrets.token_urlsafe(48))
    config.setdefault('ADMIN_PASSWORD','A7!b'+secrets.token_hex(24))
if not config.get('POSTGRES_PASSWORD'):raise SystemExit('POSTGRES_PASSWORD is required from GitHub Secrets or --generate')
if any('\n' in v or '\r' in v or '\x00' in v for v in config.values()):raise SystemExit('Multiline configuration values are not allowed')
os.umask(0o077);path.parent.mkdir(parents=True,exist_ok=True);path.parent.chmod(0o700)
path.write_text(json.dumps(config,indent=2)+'\n');path.chmod(0o600)
print('Private configuration written; secret values omitted.')
