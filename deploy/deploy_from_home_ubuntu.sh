#!/usr/bin/env bash
# Deploy Oct30LingChen using the existing environment. Never removes backups.
set -Eeuo pipefail
umask 077

usage() {
  cat <<'EOF'
sudo bash deploy_from_home_ubuntu.sh --release-dir /home/ubuntu/RELEASE \
  --release-verifier /home/ubuntu/RELEASE/verify_release_files.py \
  --db-verifier /home/ubuntu/RELEASE/verify_deployment.py

Optional: --evidence-dir NEW_DIRECTORY --base-url http://127.0.0.1
The evidence directory must not already exist. API/web backups are retained in
/opt/restaurant-cloud/backups/Oct30LingChen-TIMESTAMP-UNIQUE. No pip install,
Nginx changes, backup deletion, or database restore is performed.
EOF
}

release_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
release_verifier=""
db_verifier=""
evidence_dir=""
base_url="http://127.0.0.1"
while (($#)); do
  case "$1" in
    --release-dir|--release-verifier|--db-verifier|--evidence-dir|--base-url)
      (($# >= 2)) || { usage >&2; exit 2; }
      case "$1" in
        --release-dir) release_dir="$2" ;;
        --release-verifier) release_verifier="$2" ;;
        --db-verifier) db_verifier="$2" ;;
        --evidence-dir) evidence_dir="$2" ;;
        --base-url) base_url="${2%/}" ;;
      esac
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

die() { echo "Deployment stopped: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo."
release_dir="$(realpath -e -- "$release_dir")"
release_verifier="${release_verifier:-$release_dir/verify_release_files.py}"
db_verifier="${db_verifier:-$release_dir/verify_deployment.py}"
api_target=/opt/restaurant-cloud/api
web_target=/var/www/restaurant-web
venv_python=/opt/restaurant-cloud/.venv/bin/python
runtime_env=/opt/restaurant-cloud/.env.runtime
nginx_target=/etc/nginx/conf.d/restaurant-cloud-upload.conf
service_name=restaurant-cloud.service
expected_version=Oct30LingChen
backup_root=""
transaction_started=0
committed=0

# A requirements mismatch exits before creating even a lock or evidence file.
[[ -f "$release_dir/api/requirements.txt" && -f "$api_target/requirements.txt" ]] || die "requirements.txt missing."
cmp -s -- "$release_dir/api/requirements.txt" "$api_target/requirements.txt" || die "requirements differ; the shared virtual environment will not be changed."
for command_name in flock nginx systemctl curl cp chmod stat mktemp realpath mkdir find tee date sleep; do
  command -v "$command_name" >/dev/null || die "missing command: $command_name"
done
[[ -x "$venv_python" && -f "$runtime_env" ]] || die "existing Python environment/runtime configuration missing."
[[ -d "$api_target" && ! -L "$api_target" && -d "$web_target" && ! -L "$web_target" ]] || die "API/web must be existing physical directories."
[[ -f "$release_verifier" && ! -L "$release_verifier" && -f "$db_verifier" && ! -L "$db_verifier" ]] || die "verification scripts missing or symlinked."
[[ -f "$nginx_target" ]] || die "installed upload configuration missing."
cmp -s -- "$release_dir/nginx/restaurant-cloud-upload.conf" "$nginx_target" || die "Nginx upload configuration differs; reconcile it separately before deployment."
systemctl is-active --quiet "$service_name" || die "existing API service is not active."
nginx -t
exec 9>/run/lock/restaurant-cloud-deploy.lock
flock -n 9 || die "another deployment holds the lock."
cmp -s -- "$release_dir/api/requirements.txt" "$api_target/requirements.txt" || die "requirements changed while acquiring the lock."

# Small standard-library checks; this helper never imports application code.
guard() {
  "$venv_python" -B - "$@" <<'PY'
import ast, hashlib, json, os, shutil, stat, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

mode, *args = sys.argv[1:]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def manifest(root):
    root = Path(root)
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        entry = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
        if stat.S_ISLNK(info.st_mode):
            entry.update(kind='link', target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            entry.update(kind='file', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        elif stat.S_ISDIR(info.st_mode):
            entry.update(kind='directory')
        else:
            raise SystemExit(f'Unsupported special file: {path}')
        result[str(path.relative_to(root))] = entry
    return result

if mode == 'preflight':
    root, expected = Path(args[0]), args[1]
    require((root/'VERSION').read_text().strip() == expected, 'VERSION mismatch')
    for tree in ('api', 'web_frontend'):
        for path in [root/tree, *(root/tree).rglob('*')]:
            require(not path.is_symlink() and (path.is_dir() or path.is_file()), f'Unsupported release entry: {path}')
    main = ast.parse((root/'api/app/main.py').read_bytes())
    versions = [kw.value.value for node in ast.walk(main)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'FastAPI'
                for kw in node.keywords if kw.arg == 'version' and isinstance(kw.value, ast.Constant)]
    require(versions == [expected], 'API version mismatch')
    web = (root/'web_frontend').resolve()
    expected_assets = {'analytics-oct30.css', 'analytics-oct30.js', 'charts-oct30.js',
                       'dashboard-oct30.js', 'reporting-oct30.css'}
    referenced, references = set(), []
    class Assets(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'html' and self.document.name == 'index.html':
                require(attrs.get('data-build') == expected, 'HTML build version mismatch')
                self.build_seen = True
            fields = ['src', 'poster']
            if tag in ('link', 'use', 'image'):
                fields += ['href', 'xlink:href']
            if tag == 'object':
                fields.append('data')
            values = [attrs[key] for key in fields if attrs.get(key)]
            if attrs.get('srcset'):
                values += [part.strip().split()[0] for part in attrs['srcset'].split(',') if part.strip()]
            for value in values:
                if value.startswith(('data:', '#')):
                    continue
                url = urlsplit(value)
                require(not url.scheme and not url.netloc, f'Non-local HTML asset: {value}')
                decoded = unquote(url.path)
                candidate = (web/decoded.lstrip('/') if decoded.startswith('/') else self.document.parent/decoded).resolve()
                require(candidate.is_relative_to(web), f'Asset escapes web directory: {value}')
                require(candidate.is_file() and candidate.stat().st_size > 0, f'Missing/empty HTML asset: {value}')
                if candidate.suffix in ('.js', '.css'):
                    require(parse_qs(url.query).get('v') == [expected], f'Asset cache version mismatch: {value}')
                referenced.add(candidate.name)
                references.append(str(candidate.relative_to(web)))
        handle_startendtag = handle_starttag
    html_files = sorted(web.rglob('*.html'))
    require(web/'index.html' in html_files, 'index.html missing')
    for document in html_files:
        parser = Assets()
        parser.document, parser.build_seen = document, False
        parser.feed(document.read_text(encoding='utf-8'))
        parser.close()
        if document.name == 'index.html':
            require(parser.build_seen, 'HTML build marker missing')
    require(expected_assets <= referenced, 'An Oct30 asset is not referenced by HTML')
    for name in expected_assets:
        require((web/name).is_file() and (web/name).stat().st_size > 0, f'Missing Oct30 asset: {name}')
    print(json.dumps({'version': expected, 'html_files': len(html_files), 'asset_references': len(references), 'oct30_assets': sorted(expected_assets)}))
elif mode == 'compare':
    left, right = manifest(args[0]), manifest(args[1])
    require(left == right, f'Backup verification mismatch: {args[1]}')
    print(json.dumps({'verified_copy': args[1], 'entries': len(left)}))
elif mode == 'overlay':
    source, target = Path(args[0]), Path(args[1])
    # Reject an overlay through any local symlink before copying any source file.
    for path in sorted(source.rglob('*')):
        dest = target/path.relative_to(source)
        for ancestor in [dest, *dest.parents]:
            if ancestor == target.parent:
                break
            require(not ancestor.is_symlink(), f'Overlay crosses local symlink: {ancestor}')
        require(not dest.exists() or path.is_dir() == dest.is_dir(), f'Overlay changes entry type: {dest}')
    shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)
    for path in source.rglob('*'):
        if path.is_file():
            require(path.read_bytes() == (target/path.relative_to(source)).read_bytes(), f'Overlay mismatch: {path}')
elif mode == 'compile':
    count = 0
    for path in sorted(Path(args[0]).rglob('*.py')):
        require(not path.is_symlink(), f'Symlinked Python source: {path}')
        compile(path.read_bytes(), str(path), 'exec')
        count += 1
    require(count > 0, 'No staged Python source found')
    print(json.dumps({'staged_python_files_compiled': count}))
elif mode == 'rename':
    source, target = map(Path, args)
    require(not target.exists() and not target.is_symlink(), f'Rename target already exists: {target}')
    require(source.stat().st_dev == target.parent.stat().st_dev, 'Atomic rename requires the same filesystem')
    os.rename(source, target)
elif mode == 'health':
    data = json.loads(Path(args[0]).read_text())
    require(data.get('status') == 'ok', 'Health status is not ok')
    if len(args) > 1:
        require(data.get('version') == args[1], 'Health version mismatch')
else:
    raise SystemExit('Unknown guard operation')
PY
}

health_check() {
  local version="${1:-}" output="$2" attempt
  for attempt in {1..20}; do
    if curl --noproxy '*' --connect-timeout 2 --max-time 3 --fail --silent --show-error \
      "$base_url/api/v1/health" -o "$output" 2>/dev/null; then
      if [[ -n "$version" ]]; then
        guard health "$output" "$version" >/dev/null 2>&1 && return 0
      else
        guard health "$output" >/dev/null 2>&1 && return 0
      fi
    fi
    sleep 1
  done
  return 1
}

finish() {
  local status=$? rollback_failed=0 item target
  trap - EXIT INT TERM
  set +e
  if ((status != 0 && transaction_started && ! committed)); then
    echo "Deployment failed; restoring original program directories." >&2
    systemctl stop "$service_name"
    if [[ "$(systemctl show -p ActiveState --value "$service_name")" != inactive ]]; then
      echo "Recovery cannot move directories while the API service is still running." >&2
      rollback_failed=1
    else
      for item in api web; do
        if [[ "$item" == api ]]; then target="$api_target"; else target="$web_target"; fi
        if [[ -d "$backup_root/$item.before" ]]; then
          if [[ -e "$target" || -L "$target" ]]; then
            guard rename "$target" "$backup_root/$item.failed" || rollback_failed=1
          fi
          if [[ ! -e "$target" && ! -L "$target" ]]; then
            guard rename "$backup_root/$item.before" "$target" || rollback_failed=1
          else
            rollback_failed=1
          fi
        fi
      done
    fi
    if ((rollback_failed == 0)); then
      systemctl start "$service_name" || rollback_failed=1
      systemctl is-active --quiet "$service_name" || rollback_failed=1
      health_check "" "$evidence_dir/rollback-health.json" || rollback_failed=1
    fi
    if ((rollback_failed)); then
      echo "CRITICAL: automatic recovery incomplete; inspect retained originals: $backup_root" >&2
    else
      echo "Original API/web restored and service healthy. Database changes are not rolled back." >&2
    fi
    printf '%s\n' "$rollback_failed" > "$evidence_dir/rollback-failed.txt"
  fi
  if [[ -n "$backup_root" ]]; then
    echo "Retained backup/staging: $backup_root"
    echo "Evidence: $evidence_dir"
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guard preflight "$release_dir" "$expected_version"
# Both old directories will be moved into the same backup directory atomically.
device="$(stat -c %d /opt/restaurant-cloud)"
for path in "$api_target" "$(dirname -- "$api_target")" "$web_target" "$(dirname -- "$web_target")"; do
  [[ "$(stat -c %d "$path")" == "$device" ]] || die "API, web and backup must be on the same filesystem."
done
backup_parent=/opt/restaurant-cloud/backups
if [[ -e "$backup_parent" || -L "$backup_parent" ]]; then
  [[ -d "$backup_parent" && ! -L "$backup_parent" && "$(stat -c %d "$backup_parent")" == "$device" ]] || die "backup parent must be a physical directory on the same filesystem."
else
  mkdir -m 0700 -- "$backup_parent"
fi
backup_root="$(mktemp -d "$backup_parent/Oct30LingChen-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
evidence_dir="${evidence_dir:-$backup_root/evidence}"
[[ "$evidence_dir" == /* ]] || die "evidence directory must be absolute."
[[ ! -e "$evidence_dir" && ! -L "$evidence_dir" ]] || die "evidence directory already exists."
mkdir -m 0700 -- "$evidence_dir"
stage_root="$backup_root/staged"
mkdir -m 0700 -- "$stage_root"
[[ "$(stat -c %d "$stage_root")" == "$device" ]] || die "staging filesystem mismatch."
exec > >(tee -a "$evidence_dir/deploy.log") 2>&1
export PYTHONDONTWRITEBYTECODE=1

echo "Preparing and verifying copies before stopping the service."
cp -a -- "$api_target" "$backup_root/api.snapshot"
cp -a -- "$web_target" "$backup_root/web.snapshot"
guard compare "$api_target" "$backup_root/api.snapshot" > "$evidence_dir/api-backup-check.json"
guard compare "$web_target" "$backup_root/web.snapshot" > "$evidence_dir/web-backup-check.json"
cp -a -- "$api_target" "$stage_root/api"
guard compare "$api_target" "$stage_root/api" > "$evidence_dir/api-stage-base-check.json"
guard overlay "$release_dir/api" "$stage_root/api"
cp -a -- "$release_dir/web_frontend" "$stage_root/web"
guard compare "$release_dir/web_frontend" "$stage_root/web" > "$evidence_dir/web-stage-check.json"
guard compile "$stage_root/api" > "$evidence_dir/python-compile.json"
find "$stage_root/web" -type d -exec chmod 0755 {} +
find "$stage_root/web" -type f -exec chmod 0644 {} +
guard preflight "$release_dir" "$expected_version" > "$evidence_dir/release-preflight.json"
cmp -s -- "$release_dir/api/requirements.txt" "$api_target/requirements.txt" || die "requirements changed during staging."
cmp -s -- "$release_dir/nginx/restaurant-cloud-upload.conf" "$nginx_target" || die "Nginx upload configuration changed during staging."
nginx -t

echo "Stopping API briefly for the database baseline and directory switch."
transaction_started=1
systemctl stop "$service_name"
[[ "$(systemctl show -p ActiveState --value "$service_name")" == inactive ]] || die "API did not stop."
# Ensure local files did not change after the staged copy was prepared.
guard compare "$api_target" "$backup_root/api.snapshot" > "$evidence_dir/api-before-switch.json"
guard compare "$web_target" "$backup_root/web.snapshot" > "$evidence_dir/web-before-switch.json"
"$venv_python" -B "$db_verifier" before --env-file "$runtime_env" --app-dir "$api_target" \
  --evidence-dir "$evidence_dir" > "$evidence_dir/db-before.log"
guard rename "$api_target" "$backup_root/api.before"
guard rename "$stage_root/api" "$api_target"
guard rename "$web_target" "$backup_root/web.before"
guard rename "$stage_root/web" "$web_target"
systemctl start "$service_name"
systemctl is-active --quiet "$service_name"
health_check "$expected_version" "$evidence_dir/health.json" || die "health JSON did not report status=ok and version=$expected_version."
"$venv_python" -B "$release_verifier" --release-dir "$release_dir" --api-dir "$api_target" \
  --web-dir "$web_target" --evidence-dir "$evidence_dir" --expected-version "$expected_version" \
  --base-url "$base_url" > "$evidence_dir/release-verifier.log"
"$venv_python" -B "$db_verifier" after --env-file "$runtime_env" --app-dir "$api_target" \
  --evidence-dir "$evidence_dir" > "$evidence_dir/db-after.log"
printf '%s\n' "$expected_version" > "$evidence_dir/DEPLOYED_VERSION"
committed=1
echo "Deployment verified: $expected_version. All previous files and evidence retained."
