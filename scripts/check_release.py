#!/usr/bin/env python3
"""Reject mismatched release versions before building or publishing an image."""
from pathlib import Path
import json
import re

root=Path(__file__).resolve().parents[1]
version=re.search(r'(?m)^version = "(\d+\.\d+\.\d+)"$',(root/'Cargo.toml').read_text()).group(1)
expected={
 'Cargo.lock':r'name = "relayix"\nversion = "'+re.escape(version)+r'"',
 'Dockerfile':r'org\.opencontainers\.image\.version="'+re.escape(version)+r'"',
 'compose.app.yaml':r'(?m)^    image: [^\s]+:'+re.escape(version)+r'$',
 'web/src/main.jsx':r"const VERSION='"+re.escape(version)+r"';",
 'CHANGELOG.md':r'(?m)^## '+re.escape(version)+r' Beta — \d{4}-\d{2}-\d{2}$',
 'README.md':r'^# Relayix '+re.escape(version)+r' Beta\n',
}
for name,pattern in expected.items():
 if not re.search(pattern,(root/name).read_text()):raise SystemExit('Release version mismatch: '+name)
for name in ['web/package.json','web/package-lock.json']:
 data=json.loads((root/name).read_text())
 if data['version']!=version:raise SystemExit('Release version mismatch: '+name)
 if 'packages' in data and data['packages']['']['version']!=version:raise SystemExit('Release version mismatch: '+name+' root package')
print('PASS: release '+version+' matches application, locks, Docker label, Compose image, README and CHANGELOG')
