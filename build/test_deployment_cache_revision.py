"""Offline deployment gates: revised and legacy web cache keys must agree."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'deploy'
SCRIPT = (DEPLOY / 'deploy_from_home_ubuntu.sh').read_text()
GUARD = SCRIPT.split("<<'PY'\n", 1)[1].split('\nPY\n}', 1)[0]
SPEC = importlib.util.spec_from_file_location('release_verifier_under_test', DEPLOY / 'verify_release_files.py')
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
VERSION = 'v1.0.2'
REVISION = '20261110-final-five-kpis'
CACHE = VERSION + '-' + REVISION
ASSETS = ['analytics-oct30.css', 'analytics-oct30.js', 'charts-oct30.js',
          'dashboard-oct30.js', 'reporting-oct30.css'] + [f'fixture-{i}.js' for i in range(27)]


class DeploymentCacheRevision(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-cache-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'api/app').mkdir(parents=True)
        (self.root / 'web_frontend').mkdir()
        (self.root / 'nginx').mkdir()
        (self.root / 'VERSION').write_text(VERSION + '\n')
        (self.root / 'api/requirements.txt').write_text('fixture==1\n')
        (self.root / 'api/app/main.py').write_text('app = FastAPI(version="v1.0.2")\n')
        for i in range(15):
            (self.root / 'api/app' / f'fixture_{i}.py').write_text('VALUE = 1\n')
        (self.root / 'nginx/restaurant-cloud-upload.conf').write_text('# isolated fixture\n')
        for asset in ASSETS:
            (self.root / 'web_frontend' / asset).write_text('/* isolated fixture */\n')
        self.write_index()

    def write_index(self, revision=REVISION, version=VERSION, keys=None):
        marker = '' if revision is None else f' data-build-revision="{revision}"'
        cache = VERSION if revision is None else VERSION + '-' + revision
        references = []
        for asset in ASSETS:
            key = (keys or {}).get(asset, cache)
            references.append(f'<link rel="stylesheet" href="{asset}?v={key}">' if asset.endswith('.css')
                              else f'<script src="{asset}?v={key}"></script>')
        html = f'<html data-build="{version}"{marker}><head>' + ''.join(references) + '</head></html>'
        (self.root / 'web_frontend/index.html').write_text(html)

    def preflight(self):
        # Execute just the existing script's pure-Python guard, never its sudo,
        # systemd, filesystem swap, credentials, or database operations.
        return subprocess.run([sys.executable, '-B', '-c', GUARD, 'preflight', str(self.root), VERSION],
                              capture_output=True, text=True, check=False)

    def verifier_cache_errors(self):
        parser = VERIFY.Assets()
        parser.feed((self.root / 'web_frontend/index.html').read_text())
        parser.close()
        try:
            key = VERIFY.release_cache_version(parser, VERSION)
        except ValueError as exc:
            return [str(exc)]
        return VERIFY.validate_asset_cache_versions(parser.paths, key)

    def run_http_verifier_offline(self):
        root = self.root
        class OfflineOpener:
            def open(self, url, timeout=10):
                path = urlsplit(url).path
                if path == '/openapi.json':
                    routes = {f'/api/v1/datasets/{{dataset_id}}/inventory/name-corrections/{suffix}': {'post': {}}
                              for suffix in ('preview', 'apply')}
                    data = json.dumps({'info': {'version': VERSION}, 'paths': routes}).encode()
                elif path == '/api/v1/health':
                    data = json.dumps({'version': VERSION, 'status': 'ok'}).encode()
                else:
                    data = (root / 'web_frontend' / path.lstrip('/')).read_bytes()
                return io.BytesIO(data)
        argv = ['verify_release_files.py', '--release-dir', str(root), '--api-dir', str(root/'api'),
                '--web-dir', str(root/'web_frontend'), '--nginx-conf', str(root/'nginx/restaurant-cloud-upload.conf'),
                '--evidence-dir', str(root/'evidence')]
        with patch.object(sys, 'argv', argv), patch.object(VERIFY, 'build_opener', return_value=OfflineOpener()), contextlib.redirect_stdout(io.StringIO()):
            status = VERIFY.main()
        return status, json.loads((root/'evidence/release-check.json').read_text())

    def test_final_revision_passes_preflight_and_full_offline_verifier(self):
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['cache_version'], CACHE)
        self.assertEqual(self.verifier_cache_errors(), [])
        status, evidence = self.run_http_verifier_offline()
        self.assertEqual(status, 0, evidence)
        self.assertEqual(evidence['cache_version'], CACHE)
        self.assertEqual(evidence['failures'], [])

    def test_legacy_version_only_passes_both_gates(self):
        self.write_index(revision=None)
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['cache_version'], VERSION)
        self.assertEqual(self.verifier_cache_errors(), [])
        status, evidence = self.run_http_verifier_offline()
        self.assertEqual(status, 0, evidence)
        self.assertEqual(evidence['cache_version'], VERSION)

    def test_mixed_or_stale_cache_keys_are_rejected(self):
        for key in (VERSION, 'v1.0.2-older-build', 'v1.0.1', CACHE + '&v=' + VERSION):
            with self.subTest(key=key):
                self.write_index(keys={'charts-oct30.js': key})
                self.assertNotEqual(self.preflight().returncode, 0)
                self.assertEqual(self.verifier_cache_errors(), ['cache version: charts-oct30.js'])
                status, evidence = self.run_http_verifier_offline()
                self.assertEqual(status, 1)
                self.assertIn('cache version: charts-oct30.js', evidence['failures'])

    def test_html_build_version_mismatch_is_rejected_with_valid_cache_keys(self):
        self.write_index(version='v1.0.1')
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HTML build version mismatch', result.stderr)
        self.assertIn('HTML build version mismatch', self.verifier_cache_errors())
        status, evidence = self.run_http_verifier_offline()
        self.assertEqual(status, 1)
        self.assertIn('HTML build version mismatch', evidence['failures'])

    def test_invalid_revision_is_not_treated_as_legacy(self):
        for revision in ('', '../stale', 'contains space', 'x' * 81):
            with self.subTest(revision=revision):
                self.write_index(revision=revision)
                self.assertNotEqual(self.preflight().returncode, 0)
                self.assertIn('Invalid HTML build revision', self.verifier_cache_errors())

    def test_api_and_package_version_checks_remain_enforced(self):
        (self.root / 'api/app/main.py').write_text('app = FastAPI(version="v1.0.1")\n')
        self.assertIn('API version mismatch', self.preflight().stderr)
        (self.root / 'VERSION').write_text('v1.0.1\n')
        self.assertIn('VERSION mismatch', self.preflight().stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
