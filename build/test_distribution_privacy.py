"""Synthetic-only regression tests for the distribution privacy scanner."""
import gzip
import io
import marshal
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from audit_distribution_privacy import Auditor, COOKIE

CANARY = 'PRIVATE_TEST_CANARY'

def auditor():return Auditor([CANARY], 2 * 1024 * 1024, 20 * 1024 * 1024)

def carchive(payload):
    name=b'PYZ.pyz\0'
    entry_size=18+len(name)
    toc=struct.pack('!iIIIBB',entry_size,0,len(payload),len(payload),0,ord('z'))+name
    cookie=struct.pack('!8sIIII64s',COOKIE,len(payload)+len(toc)+88,len(payload),len(toc),312,b'libpython')
    return b'\xcf\xfa\xed\xfe'+b'\0'*28+payload+toc+cookie

class PrivacyAudit(unittest.TestCase):
    def test_utf_encodings_and_report_do_not_reveal_values(self):
        scan=auditor();scan.scan_bytes('note.txt',CANARY.encode('utf-16le'))
        self.assertEqual(scan.findings[0]['rule'],'forbidden_identifier')
        self.assertIn('utf16le',scan.findings[0]['representations'])
        self.assertNotIn(CANARY,str(scan.findings))

    def test_complete_private_key_armor_only(self):
        scan=auditor()
        # Synthetic base64, not a generated or real cryptographic key.
        marker=b'-----BEGIN '+b'RSA PRIVATE KEY-----\n'+b'QUJD'*24+b'\n-----END '+b'RSA PRIVATE KEY-----\n'
        scan.scan_bytes('synthetic.key',marker)
        self.assertTrue(any(row['rule']=='complete_private_key' for row in scan.findings))
        scan=auditor()
        scan.scan_bytes('qt-declaration.h',b'const char *header = "-----BEGIN RSA PRIVATE KEY-----";')
        self.assertFalse(any(row['rule']=='complete_private_key' for row in scan.findings))

    def test_nested_zip_and_tar_are_scanned_without_extraction(self):
        tar_data=io.BytesIO()
        with tarfile.open(fileobj=tar_data,mode='w:gz') as archive:
            member=tarfile.TarInfo('nested.txt');data=CANARY.encode();member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
        zip_data=io.BytesIO()
        with zipfile.ZipFile(zip_data,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('inside.tar.gz',tar_data.getvalue())
        scan=auditor();scan.scan_bytes('bundle.zip',zip_data.getvalue())
        self.assertEqual(scan.counts['archives'],2)
        self.assertTrue(any(row['path']=='bundle.zip!/inside.tar.gz!/nested.txt' for row in scan.findings))

    def test_both_macho_architectures_and_pyz_modules_are_scanned(self):
        compressed=zlib.compress(b'compiled module bytes '+CANARY.encode())
        pyz=b'PYZ\0'+b'\0'*4+struct.pack('!i',12+len(compressed))+compressed
        pyz+=marshal.dumps([('synthetic_module',(0,12,len(compressed)))])
        thin=carchive(pyz)
        offset=48
        fat=struct.pack('>II',0xcafebabe,2)
        fat+=struct.pack('>IIIII',0x1000007,0,offset,len(thin),0)
        fat+=struct.pack('>IIIII',0x100000c,0,offset+len(thin),len(thin),0)
        fat+=thin+thin
        scan=auditor();scan.scan_bytes('Synthetic.app/Contents/MacOS/Synthetic',fat)
        self.assertEqual(scan.counts['macho_slices'],2)
        self.assertEqual(scan.counts['pyinstaller_entries'],2)
        self.assertEqual(scan.counts['pyz_modules'],2)
        self.assertEqual(sum('/PYZ/synthetic_module' in row['path'] for row in scan.findings),2)
        self.assertFalse(any(row['rule'].startswith('unreadable') for row in scan.findings))

    def test_external_links_are_flagged_and_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'root';root.mkdir()
            secret=base/'outside.txt';secret.write_text(CANARY)
            (root/'external').symlink_to('../outside.txt')
            scan=auditor();scan.tree(root)
            self.assertEqual(scan.counts['files'],0)
            self.assertTrue(any(row['rule']=='filesystem_link_escapes_root' for row in scan.findings))

    def test_oversized_archive_member_is_a_blocker(self):
        scan=Auditor([CANARY],100,10000)
        scan.scan_bytes('oversize.txt',b'x'*101)
        self.assertEqual(scan.findings[0]['rule'],'payload_limit_exceeded')

if __name__=='__main__':unittest.main(verbosity=2)
