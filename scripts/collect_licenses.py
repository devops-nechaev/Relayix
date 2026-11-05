#!/usr/bin/env python3
"""Collect upstream license files and SPDX metadata for shipped dependencies."""
from pathlib import Path
import json,shutil,sys
mode,source,dest=sys.argv[1:]
root=Path(dest);root.mkdir(parents=True,exist_ok=True)
rows=[]
if mode=='rust':
    packages=json.loads(Path(source).read_text())['packages']
    for pkg in packages:
        if not pkg.get('source'):continue
        home=Path(pkg['manifest_path']).parent
        target=root/'rust'/(pkg['name']+'-'+pkg['version']);target.mkdir(parents=True,exist_ok=True)
        candidates=[p for p in home.iterdir() if p.is_file() and p.name.lower().startswith(('license','licence','copying','copyright','notice'))]
        if pkg.get('license_file'):candidates.append(home/pkg['license_file'])
        for folder in home.iterdir():
            if folder.is_dir() and folder.name.lower().startswith(('license','licence')):shutil.copytree(folder,target/folder.name,dirs_exist_ok=True)
        for p in candidates:
            if p.is_file():shutil.copyfile(p,target/p.name)
        rows.append({k:pkg.get(k) for k in ['name','version','license','repository']})
elif mode=='python':
    import importlib.metadata as metadata,re
    names=re.findall(r'^([A-Za-z0-9_.-]+)==',Path(source).read_text(),re.M)
    for name in names:
        pkg=metadata.distribution(name);version=pkg.version
        target=root/'python'/(name+'-'+version);target.mkdir(parents=True,exist_ok=True)
        for item in pkg.files or []:
            if any(part.lower().startswith(('license','licence','copying','copyright','notice')) for part in item.parts):
                src=pkg.locate_file(item)
                if src.is_file():
                    relative=Path(*item.parts[item.parts.index(next(part for part in item.parts if part.lower().startswith(('license','licence','copying','copyright','notice')))):])
                    out=target/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
        value=pkg.metadata.get('License-Expression') or pkg.metadata.get('License') or 'See upstream license files'
        rows.append({'name':name,'version':version,'license':value if len(value)<200 else 'See upstream license text'})
else:
    for pkg in sorted(Path(source).rglob('package.json')):
        data=json.loads(pkg.read_text());name=data.get('name');version=data.get('version')
        if not name or not version:continue
        home=pkg.parent;target=root/'npm'/(name.replace('/','_')+'-'+version)
        candidates=[p for p in home.iterdir() if p.is_file() and p.name.lower().startswith(('license','licence','copying','copyright','notice'))]
        if not candidates:continue
        target.mkdir(parents=True,exist_ok=True)
        for p in candidates:shutil.copyfile(p,target/p.name)
        rows.append({'name':name,'version':version,'license':data.get('license')})
(root/(mode+'-inventory.json')).write_text(json.dumps(sorted(rows,key=lambda d:(d['name'],d['version'])),indent=2)+'\n')
print(f'Collected {len(rows)} {mode} license records.')
