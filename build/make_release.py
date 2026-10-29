#!/usr/bin/env python3
"""Package runtime files and deployment tools; never copies credentials or databases."""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    version = (ROOT / 'VERSION').read_text().strip()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / f'dist/restaurant-cloud-{version}-deploy.tar.gz')
    args = parser.parse_args()
    if not version or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in version):
        parser.error('Invalid VERSION')
    files = {'VERSION': ROOT/'VERSION', 'api/requirements.txt': ROOT/'backend/requirements.txt',
             'nginx/restaurant-cloud-upload.conf': ROOT/'deploy/restaurant-cloud-upload.conf'}
    for name in ('deploy_from_home_ubuntu.sh', 'verify_deployment.py', 'verify_release_files.py'):
        files[name] = ROOT/'deploy'/name
    for f in sorted((ROOT/'backend/app').rglob('*.py')):
        files['api/app/' + str(f.relative_to(ROOT/'backend/app'))] = f
    for f in sorted((ROOT/'web').iterdir()):
        if f.suffix in ('.js', '.css', '.html', '.md') and not f.name.startswith('test_'):
            files['web_frontend/' + f.name] = f
    # Local source-shaped files must not silently enter a public release.
    try:
        tracked = set(subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT
        ).decode().split('\0'))
    except (OSError, subprocess.CalledProcessError):
        parser.error('Build from a Git checkout so release sources can be verified')
    for name, file in files.items():
        if not file.is_file() or file.is_symlink():
            parser.error(f'Missing or symlinked source: {name}')
        if str(file.relative_to(ROOT)) not in tracked:
            parser.error(f'Release source has not been added to Git: {name}')
    manifest = {name: hashlib.sha256(f.read_bytes()).hexdigest() for name, f in sorted(files.items())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of a reviewed release.
    with args.output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz', format=tarfile.PAX_FORMAT) as archive:
        prefix = f'restaurant-cloud-{version}/'
        for name, file in sorted(files.items()):
            info = archive.gettarinfo(str(file), arcname=prefix+name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            with file.open('rb') as data:
                archive.addfile(info, data)
        data = (json.dumps({'version':version, 'sha256':manifest},indent=2)+'\n').encode()
        info = tarfile.TarInfo(prefix+'MANIFEST.json'); info.size = len(data); info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_name(args.output.name+'.sha256').write_text(f'{digest}  {args.output.name}\n')
    print(json.dumps({'archive':str(args.output),'files':len(files),'sha256':digest},indent=2))


if __name__ == '__main__':
    main()
