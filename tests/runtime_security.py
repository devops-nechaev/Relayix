"""Check ephemeral credentials and external configuration without real secrets."""
import json,os,secrets,stat,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='relayix-runtime-security-') as folder:
    root=Path(folder)
    for name in ['first','second']:
        subprocess.run([sys.executable,str(ROOT/'tests/generate_runtime.py'),str(root/name)],check=True,capture_output=True)
    first=json.loads((root/'first/credentials.json').read_text());second=json.loads((root/'second/credentials.json').read_text())
    assert first.keys()==second.keys() and all(first[key]!=second[key] for key in first)
    assert stat.S_IMODE((root/'first/credentials.json').stat().st_mode)==0o600
    assert stat.S_IMODE((root/'first').stat().st_mode)==0o700
    artifacts=root/'artifacts';artifacts.mkdir();log=artifacts/'compose.log';log.write_text(first['admin_token']+'\n'+first['postgres_password'])
    subprocess.run([sys.executable,str(ROOT/'tests/redact_artifacts.py'),str(artifacts),str(root/'first/credentials.json')],check=True)
    assert first['admin_token'] not in log.read_text() and first['postgres_password'] not in log.read_text()
    private=root/'deployment.json'
    password=secrets.token_urlsafe(32)+'$#\'"'
    env={**os.environ,'POSTGRES_PASSWORD':password,'ADMIN_TOKEN':secrets.token_urlsafe(48),'ADMIN_PASSWORD':'A7!b'+secrets.token_hex(24)}
    result=subprocess.run([sys.executable,str(ROOT/'scripts/write_config.py'),str(private)],env=env,check=True,capture_output=True,text=True)
    assert json.loads(private.read_text())['POSTGRES_PASSWORD']==password
    assert password not in result.stdout+result.stderr
    assert stat.S_IMODE(private.stat().st_mode)==0o600
    rejected=subprocess.run([sys.executable,str(ROOT/'scripts/write_config.py'),str(ROOT/'config/deployment.json')],env=env,capture_output=True)
    assert rejected.returncode and not (ROOT/'config/deployment.json').exists()
print('PASS: unique per-run credentials, private file modes, artifact redaction, exact special-character config and source-directory rejection')
