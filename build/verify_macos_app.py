#!/usr/bin/env python3
"""Verify a universal app's source, signatures, runtime files and architectures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import struct
import subprocess
from rebuild_macos_app import verify, slices, bundle_version


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        name = str(path.relative_to(root))
        item = {'mode': stat.S_IMODE(info.st_mode)}
        if path.is_symlink():
            item.update(kind='link', target=os.readlink(path))
            if not path.exists(): raise ValueError('Broken link: '+name)
        elif path.is_file():
            item.update(kind='file', sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=info.st_size)
        else:
            item.update(kind='directory')
        result[name] = item
    return result


def macho_report(app):
    machos=[]
    versions=[]
    for path in sorted(app.rglob('*')):
        if path.is_symlink() or not path.is_file(): continue
        with path.open('rb') as stream: magic=stream.read(4)
        if magic not in (b'\xca\xfe\xba\xbe',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf'): continue
        if magic != b'\xca\xfe\xba\xbe': raise ValueError('Thin runtime component: '+str(path))
        parts=slices(path.read_bytes())
        item={'file':str(path.relative_to(app)), 'architectures':sorted(parts)}
        for arch, data in parts.items():
            pos=32
            for i in range(struct.unpack_from('<I',data,16)[0]):
                cmd,size=struct.unpack_from('<II',data,pos)
                minimum=None
                if cmd==0x32:
                    platform,minimum=struct.unpack_from('<II',data,pos+8)
                    if platform!=1: minimum=None
                elif cmd==0x24: minimum=struct.unpack_from('<I',data,pos+8)[0]
                if minimum is not None:
                    version=(minimum>>16,(minimum>>8)&255,minimum&255)
                    item[arch+'_minimum_macos']='.'.join(map(str,version));versions.append(version)
                pos+=size
        machos.append(item)
    return {'count':len(machos),'components':machos,'maximum_declared_minimum_macos':'.'.join(map(str,max(versions)))}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--runtime-app',type=Path)
    p.add_argument('--version',default='v1.0.2')
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    info=plistlib.loads((a.app/'Contents/Info.plist').read_bytes())
    assert info['CFBundleVersion']==info['CFBundleShortVersionString']==bundle_version(a.version)
    assert info['RestaurantReleaseVersion']==a.version
    executable=a.app/'Contents/MacOS'/info['CFBundleExecutable']
    source=a.source.read_bytes();digest=hashlib.sha256(source).hexdigest()
    assert (a.app/'Contents/Resources/source-sha256.txt').read_text().strip()==digest
    bytecode=verify(executable,source)
    subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(a.app)],check=True,capture_output=True)
    data={'version':a.version,'bundle_version':info['CFBundleVersion'],'source_sha256':digest,'architectures':bytecode,'signature_verified':True,
          'macho':macho_report(a.app),'signature_kind':'ad-hoc, not notarized'}
    declared=tuple(map(int,info['LSMinimumSystemVersion'].split('.')))
    declared=declared+(0,)*(3-len(declared))
    required=tuple(map(int,data['macho']['maximum_declared_minimum_macos'].split('.')))
    assert declared>=required, 'Bundle minimum system version understates runtime requirements'
    data['minimum_macos']=info['LSMinimumSystemVersion']
    if a.runtime_app:
        before=inventory(a.runtime_app);after=inventory(a.app)
        excluded=lambda name:name in ('Contents/Info.plist','Contents/Resources/source-sha256.txt','Contents/_CodeSignature/CodeResources') or name.startswith('Contents/MacOS/')
        expected={k:v for k,v in before.items() if not excluded(k)}
        actual={k:v for k,v in after.items() if not excluded(k)}
        assert expected==actual, 'Runtime content, mode or links changed'
        data['runtime_preservation']={'unchanged_entries':len(actual),'files_and_links':sum(v['kind']!='directory' for v in actual.values()),'passed':True}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in data.items() if k!='macho'},ensure_ascii=False,indent=2))
    print(json.dumps({'universal_macho_components':data['macho']['count'],'maximum_declared_minimum_macos':data['macho']['maximum_declared_minimum_macos']}))


if __name__=='__main__': main()
