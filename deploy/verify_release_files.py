#!/usr/bin/env python3
"""Compare the installed release and HTTP responses with the tested source."""
import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

class Assets(HTMLParser):
    def __init__(self):
        super().__init__(); self.paths = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if (tag == 'script' and key == 'src') or (tag == 'link' and key == 'href'):
                if value and not urlsplit(value).scheme:
                    self.paths.append(value)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release-dir', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--api-dir', type=Path, default=Path('/opt/restaurant-cloud/api'))
    p.add_argument('--web-dir', type=Path, default=Path('/var/www/restaurant-web'))
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--expected-version', default='Oct30LingChen')
    p.add_argument('--base-url', default='http://127.0.0.1')
    p.add_argument('--api-base-url', default='http://127.0.0.1:8000')
    p.add_argument('--nginx-conf', type=Path, default=Path('/etc/nginx/conf.d/restaurant-cloud-upload.conf'))
    a = p.parse_args()
    failures = []; disk_count = 0; http_count = 0
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for source, dest in ((a.release_dir/'api/app', a.api_dir/'app'), (a.release_dir/'web_frontend', a.web_dir)):
        for f in sorted(source.rglob('*')):
            if not f.is_file() or f.suffix not in ('.py','.js','.css','.html') or '__pycache__' in f.parts or f.name.startswith('test_'):
                continue
            disk_count += 1
            target = dest / f.relative_to(source)
            if not target.is_file() or digest(f.read_bytes()) != digest(target.read_bytes()):
                failures.append('disk: ' + str(target))
    for source, target in ((a.release_dir/'api/requirements.txt',a.api_dir/'requirements.txt'), (a.release_dir/'nginx/restaurant-cloud-upload.conf', a.nginx_conf)):
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            failures.append('configuration: ' + str(target))
    index = a.release_dir/'web_frontend/index.html'
    parser = Assets(); parser.feed(index.read_text())
    expected_assets = {'analytics-oct30.js','analytics-oct30.css','dashboard-oct30.js','charts-oct30.js','reporting-oct30.css'}
    if not expected_assets <= {urlsplit(x).path for x in parser.paths}:
        failures.append('missing Oct30 statistics references')
    opener = build_opener(ProxyHandler({}))
    base = a.base_url.rstrip('/')
    for asset in ['index.html'] + parser.paths:
        relative = urlsplit(asset).path
        if relative.startswith('/') or '..' in Path(relative).parts:
            failures.append('unsafe asset: ' + relative); continue
        if asset != 'index.html' and urlsplit(asset).query != 'v=' + a.expected_version:
            failures.append('cache version: ' + relative)
        with opener.open(base + '/' + asset, timeout=10) as r:
            actual = r.read()
        http_count += 1
        if digest(actual) != digest((a.release_dir/'web_frontend'/relative).read_bytes()):
            failures.append('http: ' + relative)
    with opener.open(a.api_base_url.rstrip('/')+'/openapi.json',timeout=10) as r: schema = json.load(r)
    with opener.open(base+'/api/v1/health',timeout=10) as r: health = json.load(r)
    expected_routes = ['/api/v1/datasets/{dataset_id}/inventory/name-corrections/preview','/api/v1/datasets/{dataset_id}/inventory/name-corrections/apply']
    routes = all('post' in schema.get('paths',{}).get(path,{}) for path in expected_routes)
    if disk_count < 48 or http_count < 32 or not routes or schema['info']['version'] != a.expected_version or health.get('version') != a.expected_version or health.get('status') != 'ok':
        failures.append('release count/version/route/health gate')
    result = {'installed_files_checked':disk_count,'http_assets_checked':http_count,'failures':failures,'openapi_version':schema['info']['version'],'correction_routes_registered':routes,'health':health}
    a.evidence_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    (a.evidence_dir/'release-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
