#!/usr/bin/env python3
"""Read-only privacy audit for a distribution tree, ZIP, tar or macOS app.

Provide private identifiers in an OUTSIDE file using --forbid-file. The file may
be a JSON array of strings or one UTF-8 value per line. Neither those identifiers
nor secret excerpts are printed. Source contains no installation-specific data.

The audit checks archive members, symlink boundaries, complete private-key armor,
raw sensitive bytes (UTF-8/UTF-16), and decompressed PyInstaller script/PYZ payloads
inside both architectures of a universal Mach-O. It never executes archive code.
Images are counted, not OCRed. Workbook/database/configuration candidates require
human review; a signature scan cannot establish the absence of all private data.
"""
from __future__ import annotations
import argparse
import gzip
import io
import json
import marshal
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import struct
import sys
import tarfile
import zipfile
import zlib

KEY = re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}\s+-----END (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----')
COOKIE = b'MEI\014\013\012\013\016'
REVIEW_NAMES = {'.env', '.env.runtime', '.env.production', 'credentials.json', 'sync.json', 'database.dump'}
REVIEW_SUFFIXES = {'.xlsx', '.xls', '.sqlite', '.sqlite3', '.db', '.dump', '.p12', '.pfx', '.key'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.tiff', '.heic'}

class Auditor:
    def __init__(self, forbidden, max_payload, max_total):
        self.forbidden = forbidden
        self.max_payload, self.max_total = max_payload, max_total
        self.total = 0
        self.findings = []
        self.counts = dict(files=0, archive_members=0, archives=0, symlinks=0,
                           images=0, macho_slices=0, pyinstaller_entries=0, pyz_modules=0)
        self._seen_findings = set()

    def safe_path(self, value):
        for index, token in enumerate(self.forbidden):
            value = value.replace(token, f'<forbidden-{index + 1}>')
        return value

    def finding(self, path, rule, severity='blocker', **details):
        row = {'path': self.safe_path(str(path)), 'rule': rule, 'severity': severity, **details}
        key = json.dumps(row, sort_keys=True)
        if key not in self._seen_findings:
            self._seen_findings.add(key)
            self.findings.append(row)

    def signatures(self, name, data):
        encoded_name = name.encode('utf-8', 'surrogatepass')
        for index, token in enumerate(self.forbidden):
            encodings = [('utf8', token.encode('utf-8')), ('utf16le', token.encode('utf-16le')), ('utf16be', token.encode('utf-16be'))]
            found = [encoding for encoding, needle in encodings if needle in data]
            if found or token.encode('utf-8') in encoded_name:
                self.finding(name, 'forbidden_identifier', identifier_number=index + 1,
                             representations=found, in_path=token.encode('utf-8') in encoded_name)
        keys = len(KEY.findall(data))
        if keys:
            self.finding(name, 'complete_private_key', count=keys)

    def metadata(self, name):
        leaf = PurePosixPath(name).name.lower()
        suffix = PurePosixPath(leaf).suffix
        if leaf in REVIEW_NAMES or suffix in REVIEW_SUFFIXES:
            self.finding(name, 'configuration_or_business_data_candidate', severity='review', kind=suffix or leaf)
        if suffix in IMAGE_SUFFIXES:
            self.counts['images'] += 1

    def budget(self, name, size):
        if size > self.max_payload:
            self.finding(name, 'payload_limit_exceeded', bytes=size)
            return False
        if self.total + size > self.max_total:
            self.finding(name, 'total_scan_limit_exceeded')
            return False
        self.total += size
        return True

    @staticmethod
    def safe_member(name):
        path = PurePosixPath(name)
        return not path.is_absolute() and '..' not in path.parts

    def link(self, name, target, member_name=None):
        self.counts['symlinks'] += 1
        self.signatures(name, target.encode('utf-8', 'surrogatepass'))
        if member_name is not None:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(member_name), target))
            if target.startswith('/') or resolved == '..' or resolved.startswith('../'):
                self.finding(name, 'archive_link_escapes_root')

    def scan_bytes(self, name, data, depth=0, metadata=True):
        if depth > 14:
            self.finding(name, 'nested_payload_depth_exceeded')
            return
        if not self.budget(name, len(data)):
            return
        self.signatures(name, data)
        if metadata:
            self.metadata(name)
        if data.startswith(b'PK\x03\x04') or data.startswith(b'PK\x05\x06'):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    self.counts['archives'] += 1
                    for member in archive.infolist():
                        nested = name + '!/' + member.filename
                        self.counts['archive_members'] += 1
                        if not self.safe_member(member.filename):
                            self.finding(nested, 'archive_path_escapes_root'); continue
                        if member.is_dir(): continue
                        if member.file_size > self.max_payload:
                            self.finding(nested, 'payload_limit_exceeded', bytes=member.file_size); continue
                        payload = archive.read(member)
                        if stat.S_ISLNK(member.external_attr >> 16):
                            self.link(nested, payload.decode('utf-8', 'replace'), member.filename)
                        else:
                            self.scan_bytes(nested, payload, depth + 1)
                return
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
                self.finding(name, 'unreadable_zip', error_type=type(error).__name__)
                return
        is_tar = data[257:262] == b'ustar'
        candidate = is_tar or name.lower().endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz'))
        if candidate:
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
                    self.counts['archives'] += 1
                    for member in archive:
                        nested = name + '!/' + member.name
                        self.counts['archive_members'] += 1
                        if not self.safe_member(member.name):
                            self.finding(nested, 'archive_path_escapes_root'); continue
                        if member.issym() or member.islnk():
                            self.link(nested, member.linkname, member.name if member.issym() else '')
                        elif member.isfile():
                            if member.size > self.max_payload:
                                self.finding(nested, 'payload_limit_exceeded', bytes=member.size); continue
                            self.scan_bytes(nested, archive.extractfile(member).read(), depth + 1)
                        elif not member.isdir():
                            self.finding(nested, 'archive_special_file')
                return
            except (OSError, ValueError, tarfile.TarError) as error:
                self.finding(name, 'unreadable_tar', error_type=type(error).__name__)
                return
        if data.startswith(b'\x1f\x8b'):
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                    payload = stream.read(self.max_payload + 1)
                self.scan_bytes(name + '!/gzip-payload', payload, depth + 1, metadata=False)
            except (OSError, EOFError, zlib.error) as error:
                self.finding(name, 'unreadable_gzip', error_type=type(error).__name__)
            return
        if data[:4] == b'\xca\xfe\xba\xbe':
            count = struct.unpack_from('>I', data, 4)[0]
            if count > 32 or len(data) < 8 + 20 * count:
                self.finding(name, 'invalid_universal_macho'); return
            for index in range(count):
                cpu, _sub, offset, size, _align = struct.unpack_from('>IIIII', data, 8 + index * 20)
                if offset + size > len(data):
                    self.finding(name, 'invalid_macho_slice'); continue
                arch = {0x1000007: 'x86_64', 0x100000c: 'arm64'}.get(cpu, str(cpu))
                self.counts['macho_slices'] += 1
                self.pyinstaller(name + '!/' + arch, data[offset:offset + size], depth + 1)
            return
        if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
            self.pyinstaller(name, data, depth + 1)

    def inflate(self, name, data):
        dec = zlib.decompressobj()
        result = dec.decompress(data, self.max_payload + 1)
        if len(result) > self.max_payload or dec.unconsumed_tail:
            self.finding(name, 'decompressed_payload_limit_exceeded')
            return None
        return result

    def pyinstaller(self, name, data, depth):
        cookie = data.rfind(COOKIE)
        if cookie < 0: return
        try:
            if cookie + 88 > len(data): raise ValueError('cookie')
            _magic, size, toc_offset, toc_size, _version, _library = struct.unpack_from('!8sIIII64s', data, cookie)
            start = cookie + 88 - size
            cursor, end = start + toc_offset, start + toc_offset + toc_size
            if start < 0 or cursor < start or end > cookie: raise ValueError('bounds')
            while cursor < end:
                entry_size, offset, packed_size, raw_size, compressed, kind = struct.unpack_from('!iIIIBB', data, cursor)
                if entry_size < 18 or cursor + entry_size > end or start + offset + packed_size > cookie: raise ValueError('entry')
                member = data[cursor + 18:cursor + entry_size].split(b'\0')[0].decode('utf-8', 'replace')
                nested = name + '!/CArchive/' + member
                self.counts['pyinstaller_entries'] += 1
                if raw_size > self.max_payload:
                    self.finding(nested, 'payload_limit_exceeded', bytes=raw_size)
                else:
                    payload = data[start + offset:start + offset + packed_size]
                    if compressed: payload = self.inflate(nested, payload)
                    if payload is not None:
                        self.scan_bytes(nested, payload, depth + 1, metadata=False)
                        if kind == ord('z') or payload[:4] == b'PYZ\0':
                            self.pyz(nested, payload, depth + 1)
                cursor += entry_size
        except (ValueError, IndexError, struct.error, zlib.error) as error:
            self.finding(name, 'unreadable_pyinstaller', error_type=type(error).__name__)

    def pyz(self, name, data, depth):
        try:
            if data[:4] != b'PYZ\0' or len(data) < 12: raise ValueError('header')
            offset = struct.unpack_from('!i', data, 8)[0]
            if not 12 <= offset < len(data): raise ValueError('toc')
            table = marshal.loads(data[offset:])
            entries = table.items() if isinstance(table, dict) else table
            for module, info in entries:
                _kind, position, length = info
                if position < 0 or length < 0 or position + length > offset: raise ValueError('module')
                nested = name + '!/PYZ/' + str(module)
                payload = self.inflate(nested, data[position:position + length])
                self.counts['pyz_modules'] += 1
                if payload is not None:self.scan_bytes(nested, payload, depth + 1, metadata=False)
        except (ValueError, TypeError, EOFError, IndexError, struct.error, zlib.error) as error:
            self.finding(name, 'unreadable_pyz', error_type=type(error).__name__)

    def tree(self, root):
        root = root.resolve()
        if root.is_file():
            self.counts['files'] += 1
            self.scan_bytes(root.name, root.read_bytes())
            return
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in [*dirs, *files]:
                file = Path(directory) / name
                relative = str(file.relative_to(root))
                try:
                    if file.is_symlink():
                        target = os.readlink(file)
                        self.link(relative, target)
                        try:
                            if not file.resolve().is_relative_to(root):self.finding(relative, 'filesystem_link_escapes_root')
                            if not file.exists():self.finding(relative, 'broken_symlink')
                        except OSError:self.finding(relative, 'unresolvable_symlink')
                    elif file.is_file():
                        self.counts['files'] += 1
                        if file.stat().st_size > self.max_payload:self.finding(relative, 'payload_limit_exceeded', bytes=file.stat().st_size)
                        else:self.scan_bytes(relative, file.read_bytes())
                    elif not file.is_dir():self.finding(relative, 'special_file')
                except OSError as error:self.finding(relative, 'unreadable_file', error_type=type(error).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--forbid-file', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--max-payload-mb', type=int, default=256)
    parser.add_argument('--max-total-mb', type=int, default=2048)
    args = parser.parse_args()
    text = args.forbid_file.read_text(encoding='utf-8')
    forbidden = json.loads(text) if text.lstrip().startswith('[') else text.splitlines()
    if not isinstance(forbidden, list) or not all(isinstance(item, str) and item for item in forbidden):
        parser.error('The external forbid file must contain a nonempty string per entry.')
    if not forbidden:parser.error('At least one private identifier must be supplied externally.')
    if args.target.is_dir() and args.forbid_file.resolve().is_relative_to(args.target.resolve()):
        parser.error('Keep the private forbid file outside the distribution being scanned.')
    auditor = Auditor(forbidden, args.max_payload_mb * 1024 * 1024, args.max_total_mb * 1024 * 1024)
    auditor.tree(args.target)
    blockers = sum(row['severity'] == 'blocker' for row in auditor.findings)
    report = {'status': 'blocked' if blockers else 'no_forbidden_signatures_found',
              'counts': auditor.counts, 'bytes_scanned_including_decompressed_payloads': auditor.total,
              'forbidden_identifiers_supplied': len(forbidden), 'blocker_count': blockers,
              'review_candidate_count': sum(row['severity'] == 'review' for row in auditor.findings),
              'findings': auditor.findings,
              'limits': ['No OCR or image-content classification.', 'Unknown credentials and personal data require manual review.', 'No archive code was executed.']}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key:value for key,value in report.items() if key != 'findings'}, ensure_ascii=False, indent=2))
    return 2 if blockers else 0

if __name__ == '__main__':
    raise SystemExit(main())
