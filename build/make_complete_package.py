#!/usr/bin/env python3
"""Build the complete distribution ZIP with UTF-8 names and Unix symlinks.

Run after rebuilding/verifying the server tar and universal macOS app, writing
release metadata, and removing temporary Git/dependency/cache directories.
The manifest is refreshed; existing output archives are never overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

from verify_package import inventory


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    root=a.root.resolve()
    if a.output.exists():p.error('Output exists; choose an unused output path')
    if a.output.resolve().is_relative_to(root):p.error('Output must be outside package root')
    version=(root/'VERSION').read_text().strip()
    info=json.loads((root/'RELEASE_INFO.json').read_text())
    for item in root.rglob('*'):
        if any(part in {'.git','node_modules','__pycache__','.pytest_cache','.DS_Store'} for part in item.relative_to(root).parts):
            p.error('Remove local-only build material before packaging: '+str(item.relative_to(root)))
    manifest={'version':version,'build_revision':info.get('build_revision'),
              'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'entries':inventory(root)}
    (root/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for item in [root,*sorted(root.rglob('*'))]:
            metadata=item.lstat()
            name=item.relative_to(root.parent).as_posix()
            if stat.S_ISDIR(metadata.st_mode):name+='/'
            modified=datetime.fromtimestamp(metadata.st_mtime)
            zi=zipfile.ZipInfo(name,modified.timetuple()[:6])
            zi.create_system=3
            zi.external_attr=metadata.st_mode<<16
            if stat.S_ISDIR(metadata.st_mode):zi.external_attr|=0x10
            zi.compress_type=zipfile.ZIP_DEFLATED
            if stat.S_ISLNK(metadata.st_mode):data=os.fsencode(os.readlink(item))
            elif stat.S_ISREG(metadata.st_mode):data=item.read_bytes()
            elif stat.S_ISDIR(metadata.st_mode):data=b''
            else:raise ValueError('Unsupported file type: '+str(item))
            archive.writestr(zi,data,compresslevel=6)
    digest=hashlib.sha256(a.output.read_bytes()).hexdigest()
    a.output.with_name(a.output.name+'.sha256').write_text(f'{digest}  {a.output.name}\n')
    print(json.dumps({'archive':str(a.output),'version':version,'revision':info.get('build_revision'),
                      'manifest_entries':len(manifest['entries']),'bytes':a.output.stat().st_size,'sha256':digest},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
