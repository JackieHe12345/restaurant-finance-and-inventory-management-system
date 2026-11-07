#!/usr/bin/env python3
"""Read-only verification of an extracted complete v1.0.1 distribution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


def inventory(root):
    entries = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if relative == 'PACKAGE_MANIFEST.json':
            continue
        metadata = path.lstat()
        item = {'mode': format(stat.S_IMODE(metadata.st_mode), '04o')}
        if path.is_symlink():
            target = os.readlink(path)
            item.update(type='symlink', target=target,
                        sha256=hashlib.sha256(os.fsencode(target)).hexdigest())
            if not path.exists() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Broken or external symlink: ' + relative)
        elif path.is_file():
            item.update(type='file', size=metadata.st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        elif path.is_dir():
            item.update(type='directory')
        else:
            raise ValueError('Unsupported file type: ' + relative)
        entries[relative] = item
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'PACKAGE_MANIFEST.json').read_text())
    actual = inventory(root)
    expected = manifest['entries']
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
    result = {'version': manifest['version'], 'checked_entries': len(expected),
              'missing': missing, 'extra': extra, 'changed': changed,
              'passed': not (missing or extra or changed)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
