#!/usr/bin/env python3
"""Recompile a Python 3.12 PyInstaller app using a verified universal runtime.

The supplied runtime must already contain every dependency imported by source.
Only the main script, bundle identity, source digest and outer signatures change.
Run on macOS with Python 3.12, lipo and codesign. Output must not exist.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import marshal
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import zlib

MAGIC = b'MEI\014\013\012\013\016'
ARCHES = {0x1000007: 'x86_64', 0x100000c: 'arm64'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle_version(version):
    """Map the product label (v1.0.1) to Apple's numeric bundle version."""
    numeric = version.removeprefix('v')
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', numeric):
        raise ValueError('Use a three-part numeric version, optionally prefixed with v')
    return numeric


def slices(data):
    magic, count = struct.unpack_from('>II', data)
    if magic != 0xcafebabe:
        raise ValueError('Expected a universal Mach-O with 32-bit fat headers')
    result = {}
    for i in range(count):
        cpu, sub, offset, size, align = struct.unpack_from('>IIIII', data, 8 + i * 20)
        result[ARCHES[cpu]] = data[offset:offset + size]
    if set(result) != {'arm64', 'x86_64'}:
        raise ValueError('Both supported architectures are required')
    return result


def archive(data):
    cookie = data.rfind(MAGIC)
    if cookie < 0:
        raise ValueError('Missing PyInstaller cookie')
    magic, length, toc_offset, toc_length, pyversion, pylib = struct.unpack_from('!8sIIII64s', data, cookie)
    if pyversion != 312:
        raise ValueError('Runtime is not Python 3.12')
    start = cookie + 88 - length
    cursor = start + toc_offset
    end = cursor + toc_length
    entries = []
    while cursor < end:
        size, offset, packed, unpacked, compressed, kind = struct.unpack_from('!iIIIBB', data, cursor)
        if size < 18 or cursor + size > end:
            raise ValueError('Invalid TOC')
        name = data[cursor + 18:cursor + size].split(b'\0')[0].decode('utf-8')
        entries.append(dict(name=name, kind=kind, compressed=compressed, unpacked=unpacked,
                            data=data[start + offset:start + offset + packed]))
        cursor += size
    return start, entries, pylib


def main_entry(entries):
    candidates = [e for e in entries if e['kind'] == ord('s') and not e['name'].startswith(('pyi_', 'pyiboot'))]
    if len(candidates) != 1:
        raise ValueError('Ambiguous application entry point')
    return candidates[0]


def unpack(entry):
    return zlib.decompress(entry['data']) if entry['compressed'] else entry['data']


def rebuild_thin(data, source, filename, entry_name):
    start, entries, pylib = archive(data)
    main = main_entry(entries)
    old_name = main['name']
    raw = marshal.dumps(compile(source, filename, 'exec', optimize=0))
    main.update(name=entry_name, data=zlib.compress(raw, 9), unpacked=len(raw), compressed=1)
    packed = bytearray()
    toc = bytearray()
    for e in entries:
        name = e['name'].encode() + b'\0'
        size = (18 + len(name) + 15) // 16 * 16
        toc += struct.pack('!iIIIBB', size, len(packed), len(e['data']), e['unpacked'], e['compressed'], e['kind'])
        toc += name + b'\0' * (size - 18 - len(name))
        packed += e['data']
    cookie = struct.pack('!8sIIII64s', MAGIC, len(packed) + len(toc) + 88, len(packed), len(toc), 312, pylib)
    rebuilt = bytearray(data[:start]) + packed + toc + cookie
    if struct.unpack_from('<I', rebuilt)[0] != 0xfeedfacf:
        raise ValueError('Expected little-endian Mach-O 64')
    pos = 32
    for _ in range(struct.unpack_from('<I', rebuilt, 16)[0]):
        cmd, size = struct.unpack_from('<II', rebuilt, pos)
        if cmd == 0x1d:
            raise ValueError('Remove the old code signature before rebuilding')
        if cmd == 0x19 and rebuilt[pos + 8:pos + 24].rstrip(b'\0') == b'__LINKEDIT':
            fileoff = struct.unpack_from('<Q', rebuilt, pos + 40)[0]
            filesize = len(rebuilt) - fileoff
            struct.pack_into('<Q', rebuilt, pos + 32, (filesize + 16383) // 16384 * 16384)
            struct.pack_into('<Q', rebuilt, pos + 48, filesize)
        if cmd == 0x2:
            stroff = struct.unpack_from('<I', rebuilt, pos + 16)[0]
            struct.pack_into('<I', rebuilt, pos + 20, len(rebuilt) - stroff)
        pos += size
    return bytes(rebuilt), dict(main_bytecode_sha256=sha(raw), original_entry_name=old_name,
                               unchanged_archive_entries=len(entries) - 1)


def same_code(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, types.CodeType):
        fields = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
                  'co_flags', 'co_code', 'co_names', 'co_varnames', 'co_filename', 'co_name', 'co_qualname',
                  'co_firstlineno', 'co_linetable', 'co_exceptiontable', 'co_freevars', 'co_cellvars')
        return all(getattr(a, f) == getattr(b, f) for f in fields) and same_code(a.co_consts, b.co_consts)
    if isinstance(a, tuple):
        return len(a) == len(b) and all(same_code(x, y) for x, y in zip(a, b))
    return a == b


def verify(executable, source):
    result = {}
    for arch, data in slices(executable.read_bytes()).items():
        _, entries, _ = archive(data)
        raw = unpack(main_entry(entries))
        code = marshal.loads(raw)
        match = same_code(code, compile(source, code.co_filename, 'exec', optimize=0))
        if not match:
            raise ValueError(f'Source mismatch: {arch}')
        result[arch] = dict(main_bytecode_sha256=sha(raw), source_matches=True)
    return result


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-app', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', default='v1.0.1')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        numeric_version = bundle_version(args.version)
    except ValueError as exc:
        parser.error(str(exc))
    if sys.version_info[:2] != (3, 12):
        parser.error('Use Python 3.12 to match the packaged runtime')
    if args.output.exists():
        parser.error('Output already exists; choose an unused path')
    runtime = args.runtime_app.resolve()
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', str(runtime))
    original_info = plistlib.loads((runtime / 'Contents/Info.plist').read_bytes())
    old_exe = runtime / 'Contents/MacOS' / original_info['CFBundleExecutable']
    original_slices = slices(old_exe.read_bytes())
    source = args.source.read_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime, args.output, symlinks=True)
    name = args.output.stem
    new_exe = args.output / 'Contents/MacOS' / name
    copied_exe = args.output / 'Contents/MacOS' / original_info['CFBundleExecutable']
    copied_exe.unlink()
    details = {}
    with tempfile.TemporaryDirectory(prefix='v1_0_1-build-', dir=args.output.parent) as temporary:
        thin_paths = []
        for arch, data in original_slices.items():
            thin = Path(temporary) / arch
            thin.write_bytes(data)
            thin.chmod(0o755)
            run('/usr/bin/codesign', '--remove-signature', str(thin))
            rebuilt, details[arch] = rebuild_thin(thin.read_bytes(), source, 'desktop/restaurant_cost_manager.py', name)
            thin.write_bytes(rebuilt)
            # Runtime/PYZ/bootstrap entries are preserved byte for byte.
            original_entries = archive(data)[1]
            original_main = main_entry(original_entries)
            before = {e['name']: e['data'] for e in original_entries if e is not original_main}
            after_entries = archive(rebuilt)[1]
            after_main = main_entry(after_entries)
            after = {e['name']: e['data'] for e in after_entries if e is not after_main}
            if before != after:
                raise ValueError('A runtime archive entry changed')
            thin_paths.append(str(thin))
        run('/usr/bin/lipo', '-create', *thin_paths, '-output', str(new_exe))
    new_exe.chmod(0o755)
    info = dict(original_info)
    info.update(CFBundleDisplayName=name, CFBundleName=name, CFBundleExecutable=name,
                CFBundleIdentifier='com.restaurant.costmanager.' + args.version.lower(),
                CFBundleShortVersionString=numeric_version, CFBundleVersion=numeric_version,
                RestaurantReleaseVersion=args.version,
                LSMinimumSystemVersion='15.0')
    (args.output / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    (args.output / 'Contents/Resources/source-sha256.txt').write_text(sha(source) + '\n')
    run('/usr/bin/codesign', '--force', '--sign', '-', str(new_exe))
    run('/usr/bin/codesign', '--force', '--sign', '-', str(args.output))
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', str(args.output))
    checked = verify(new_exe, source)
    for arch in details:
        details[arch].update(checked[arch])
    report = dict(version=args.version, source_sha256=sha(source),
                  build_method='Recompiled main script, preserving verified universal Python/Qt runtime',
                  architectures=details, codesign_verified=True, signature='ad-hoc; not Apple notarized')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
