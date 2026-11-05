"""Remove ephemeral test credentials from text artifacts before upload/cleanup."""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);credentials=Path(sys.argv[2])
if credentials.exists():
    values=json.loads(credentials.read_text()).values()
    for path in root.rglob('*'):
        if path.is_file() and path.suffix in {'.log','.txt','.json','.html'}:
            data=path.read_bytes()
            for value in values:
                if isinstance(value,str) and value:data=data.replace(value.encode(),b'[REDACTED]')
            path.write_bytes(data)
