# restaurant-finance-and-inventory-management-system deployment guide

[Back to README](../README.md) · English | [简体中文](DEPLOYMENT.zh-CN.md)

This guide covers `Oct30LingChen`. Use the Docker Compose configuration at the repository root for a new instance. An existing native Ubuntu installation has a separate upgrade procedure based on a release archive. These two procedures use different directory layouts, environments and commands.

The host paths below are installation conventions, not production credentials. The instructions explain how to install and verify an instance; they do not certify an existing production deployment.

## 1. Start a new instance from source

Install Git, Docker Engine, Docker Compose v2, Python 3 and curl on the host, and run the commands below in a POSIX shell. The first build downloads container images and Python dependencies. Generated browser files are already included in the repository, so deployment does not require Node.js. After editing browser business logic, rebuild `web/` using the steps in the README.

Business-script sources live in `build/web-exact-source/`. Maintain the shared decimal runtime `web/money.js` and HTML/CSS assets directly in `web/`; the compiler does not generate or duplicate them.

```bash
git clone https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system.git
cd restaurant-finance-and-inventory-management-system
```

The root `.env.example` configures Compose; `backend/.env.example` configures a directly launched Python API. They serve different purposes. The following command creates a private configuration from the root template and generates separate values for the database password, JWT secret and initial administrator password:

```bash
python3 - <<'PY'
import os
import secrets
from pathlib import Path

content = Path('.env.example').read_text()
for name in ('POSTGRES_PASSWORD', 'SECRET_KEY', 'ADMIN_PASSWORD'):
    content = content.replace(name + '=\n', name + '=' + secrets.token_hex(24) + '\n')
fd = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(content)
print('Created .env with three independent random values.')
PY
```

This command neither prints the generated values nor overwrites an existing `.env`. Use a local editor to retrieve the administrator password and change `ADMIN_USERNAME` if needed. Compose inserts the database password into `DATABASE_URL`; the generated hexadecimal characters avoid the need to escape reserved URL characters.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

The first build and API startup can take some time. If the health check initially fails, inspect `docker compose logs --tail=100 backend` and retry after the service starts. A successful response reports `status` as `ok` and `version` as `Oct30LingChen`.

Open <http://127.0.0.1:8080> and sign in with the administrator configured in `.env`. Create an independent book, then create other accounts and assign their book memberships. Startup creates the initial administrator only when that username does not already exist. Changing `ADMIN_PASSWORD` in `.env` does not reset an existing database account's password.

### Services and persistent data

| Service or data | Configuration | Purpose |
| --- | --- | --- |
| `database` | PostgreSQL 16 | Stores accounts, books, business records, audit entries and permissions |
| `backend` | Python 3.12 and Uvicorn | Serves the API on port 8000 inside the container network |
| `web` | Nginx | Serves static files and proxies the API on the same origin |
| `postgres-data` volume | PostgreSQL data directory | Preserves the database when containers are recreated |
| `payment-secrets` volume | API path `/data/payment-secrets` | Stores merchant files received by the application |
| `recovery-files` volume | API path `/opt/restaurant-cloud/backups` | Stores recovery material produced by the application |

Compose does not publish the database or API port directly to the host. The web server binds to `127.0.0.1:8080` by default, suitable for local verification or as an upstream for the host's HTTPS reverse proxy. For public access, proxy your domain's HTTPS endpoint to that address. Changing `WEB_BIND` changes who can reach the service. This repository does not contain personal domain, certificate or DNS settings.

`TEST_LOGIN_ENABLED=false` disables the Test shortcut login by default. Keep this setting and use accounts you create. The current startup path does not enable the legacy WeChat bill scheduler; configuring merchant files does not start scheduled imports.

Use `docker compose stop` to stop the containers and `docker compose up -d` to restart them. A normal `docker compose down` preserves named volumes. Options that remove volumes also delete the persistent data listed above and are not part of a routine update.

### Why the API uses the same origin

The browser requests `/api/v1`. The relevant part of `deploy/nginx.conf` is:

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

There is no trailing `/` on `proxy_pass`, so `/api/v1/auth/login` reaches the API with its original path. Static files come from the mounted `web/` directory. A static HTTP server alone can display the page but cannot provide real login or data operations.

The complete Compose Nginx configuration also sets a 26 MB upload limit and requires browser cache revalidation. `deploy/restaurant-cloud-upload.conf` is an upload/cache snippet for native installations, not the complete Compose `server` configuration.

## 2. Run the native Python API directly

Use this approach for debugging or with your own process manager and Nginx configuration. It requires Python 3.12, a reachable PostgreSQL server, and an existing database and database role. Normal operation depends on PostgreSQL `JSONB`; the SQLite adaptation used in tests is not a production deployment option.

For example, on a new Ubuntu PostgreSQL instance, create the role using an interactive password prompt so that the password is not placed in a shell command:

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

Create a Python environment at the repository root, then enter the backend directory:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
cp .env.example .env
chmod 600 .env
```

Copy the template only when creating a new configuration. Edit `backend/.env` to supply the actual PostgreSQL connection string, a random `SECRET_KEY` and the initial administrator password. Keep `TEST_LOGIN_ENABLED=false`. Percent-encode reserved URL characters in the database password when constructing the connection string. Set `PAYMENT_SECRET_ROOT` to a directory the application process can write to, outside the public source directory.

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

`uvicorn[standard]` includes `python-dotenv`, which loads the environment file. Check the API from another terminal:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

Configure the host's Nginx with this repository's `web/` directory as the static root and `proxy_pass http://127.0.0.1:8000;` to preserve the original `/api/` path. A production installation also needs a service account, writable directories and process supervision. The upgrade script described below expects those paths and a systemd service to exist; it does not create this environment.

At startup, the application uses SQLAlchemy `create_all` to create missing tables and adds specific legacy timing fields stored as JSONB. This is not a general database migration framework. Changes to existing column structures need a separate migration. Startup also handles the initial account, legacy account memberships and the 366-day audit retention policy, so a restart is not guaranteed to leave the database unchanged.

## 3. Back up a Compose instance

Excel exports do not contain the complete account, permission, audit or runtime configuration data. A complete recovery requires at least the database, private `.env`, merchant files and application recovery material. Keep the source commit or release archive used for the installation as well.

Run the following from the repository root to create a separate local backup. Pause business writes until the backup completes so that the database and associated files represent the same operational point in time.

```bash
umask 077
mkdir -p ../restaurant-finance-backups
chmod 700 ../restaurant-finance-backups
finance_backup_dir="$(mktemp -d ../restaurant-finance-backups/manual-XXXXXXXX)"
docker compose exec -T database pg_dump -U restaurant -d restaurant -Fc > "$finance_backup_dir/database.dump"
docker compose exec -T backend tar -C /data -czf - payment-secrets > "$finance_backup_dir/payment-secrets.tar.gz"
docker compose exec -T backend tar -C /opt/restaurant-cloud -czf - backups > "$finance_backup_dir/recovery-files.tar.gz"
cp .env "$finance_backup_dir/runtime.env"
git rev-parse HEAD > "$finance_backup_dir/source-commit.txt"
docker compose exec -T database pg_restore --list < "$finance_backup_dir/database.dump" > "$finance_backup_dir/database-contents.txt"
```

Confirm that each command succeeded before copying the backup to restricted, durable storage. Backups contain credentials and business data and must stay out of Git. `pg_restore --list` only checks that the archive can be read. To establish that recovery works, restore it into a separate database and check login, books and inventory.

For a native installation, use your PostgreSQL backup procedure and also preserve the runtime environment and merchant directory. The upgrade script below backs up the API and browser programs; it does not automatically create a database dump.

## 4. Build a release archive for a native service

First complete the browser build, API regression tests and FIFO contract checks listed in the README. Then run this from the repository root:

```bash
python3 build/make_release.py --output dist/restaurant-cloud-Oct30LingChen-deploy.tar.gz
```

The path shown is also the default output path. The packager creates the archive exclusively and refuses to overwrite an existing file. Use a new output filename when rebuilding.

The archive root is `restaurant-cloud-Oct30LingChen/`, containing:

```text
api/app/                           Python API source
api/requirements.txt               API dependencies
web_frontend/                      Generated browser files
nginx/restaurant-cloud-upload.conf Native Nginx upload/cache settings
VERSION                            Release version
MANIFEST.json                      SHA-256 hashes of packaged files
deploy_from_home_ubuntu.sh          Native upgrade script
verify_deployment.py               PostgreSQL before/after evidence
verify_release_files.py            File and HTTP verification
```

All three scripts are at the release root. A matching `.sha256` checksum file is written beside the archive. The packager selects runtime files from the specified source paths; it excludes databases, `.env`, merchant keys, test modules and dependency caches. The manifest checks file contents and is not a digital signature of the release.

Upload the archive and its `.sha256` file to the target host, then verify and extract them from their containing directory:

```bash
sha256sum -c restaurant-cloud-Oct30LingChen-deploy.tar.gz.sha256
mkdir restaurant-finance-release-check
tar -xzf restaurant-cloud-Oct30LingChen-deploy.tar.gz -C restaurant-finance-release-check
```

On macOS, the equivalent checksum command is `shasum -a 256 -c ...`. Extract into a new, empty directory. The upgrade script accepts the extracted release root, not the Git checkout or the `.tar.gz` file.

## 5. Upgrade an existing native Ubuntu installation

`deploy_from_home_ubuntu.sh` expects the following installation layout:

| Component | Location |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| Private runtime environment | `/opt/restaurant-cloud/.env.runtime` |
| Browser files | `/var/www/restaurant-web` |
| Nginx upload/cache snippet | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| Running systemd service | `restaurant-cloud.service` |
| Program backup and default evidence directory | `/opt/restaurant-cloud/backups/Oct30LingChen-UTCSTAMP-UNIQUE/` |

This script cannot update Compose containers. The API, browser, backup and staging directories must be on the same filesystem so that directory renames can switch the installation. The existing API and browser paths must be physical directories. The installed requirements file and Nginx snippet must match the release byte for byte. If they differ, the script stops; review dependency or Nginx changes separately first.

The script uses the existing Python environment, including `python-dotenv`, SQLAlchemy and the PostgreSQL driver. It also requires systemd, Nginx, `flock`, `curl` and the other host tools it checks. It neither installs Python dependencies nor changes Nginx configuration.

Confirm that a usable database backup exists, then pause writes from other clients, background tasks and external database connections. The post-upgrade checks require protected business records to match the pre-upgrade baseline. Normal business writes during deployment can therefore cause verification to fail.

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen \
  --base-url http://127.0.0.1
```

Replace `/home/ubuntu/...` with the actual upload location. By default, the script uses the two verifiers included in the release. Override them with `--release-verifier` and `--db-verifier` when needed. `--evidence-dir` accepts a new absolute directory path that must not already exist; the default is an `evidence/` directory inside the current backup directory.

The upgrade proceeds as follows:

1. Check the version, HTML asset references, dependencies, Nginx and directory conditions, then acquire the deployment lock.
2. Copy and verify the existing programs, prepare the staged directories and check that Python source compiles. The staged API overlays release files onto a copy of the old API; the staged browser directory is created from the release.
3. Stop the API and confirm it has stopped, capture the database baseline, then switch the API and browser directories.
4. Start the service and verify the health version, installed file hashes, HTTP static assets, OpenAPI routes and database state against the baseline.
5. After all checks pass, write `DEPLOYED_VERSION` into the evidence directory. Keep the program backups and evidence.

If deployment fails, the script attempts to restore the original API and browser directories and check service health again. Automatic rollback does not restore the database. If rollback fails, the script reports the failure and retains the original directories for recovery. Reverting application files and restoring the database are separate operations.

The script does not delete old backups. Clean up old versions separately after verification and recovery preparation. The current evidence directory and database recovery material must not be discarded as ordinary temporary files.

## 6. Run verification separately

The upgrade script already runs these checks. You can also run them separately to investigate an existing installation or retain additional evidence. The commands below use the native installation paths from the previous section.

### Release files and HTTP

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/verify_release_files.py \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen \
  --api-dir /opt/restaurant-cloud/api \
  --web-dir /var/www/restaurant-web \
  --nginx-conf /etc/nginx/conf.d/restaurant-cloud-upload.conf \
  --base-url http://127.0.0.1 \
  --api-base-url http://127.0.0.1:8000 \
  --expected-version Oct30LingChen \
  --evidence-dir /opt/restaurant-cloud/backups/manual-release-check-001
```

`--evidence-dir` is required. Choose a new private directory for each standalone check; results are written to `release-check.json`. The check covers the release's Python/browser file hashes, requirements, Nginx snippet, referenced browser assets, cache versions, health endpoint and ingredient-name correction API routes.

`--base-url` is the browser entry point. `--api-base-url` is an API address that exposes `/openapi.json` directly. The Compose Nginx configuration does not proxy `/openapi.json`, so its web address cannot be used for that argument. The native upgrade wrapper uses the default API address, `127.0.0.1:8000`.

### PostgreSQL evidence before and after an upgrade

Pause business writes before running `before`. Keep writes paused after the upgrade while running `after`. Use the same evidence directory for both:

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/verify_deployment.py before \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001

# Run after updating the application:
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/verify_deployment.py after \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001
```

This tool requires PostgreSQL and reads current data in a `REPEATABLE READ`, `READ ONLY` transaction. It imports only the configuration and database modules; it does not run application startup. Business JSONB hashes use PostgreSQL's original text representation, avoiding reserialization through Python floating-point values. The output contains record counts, table hashes, the environment-file hash and check results. It does not print ledger payloads, password hashes or environment values.

`before` refuses to overwrite an existing baseline, and `after` fails if no baseline exists. The comparison covers specified business records, entry timing, name-correction receipts, accounts, books, memberships and temporary permissions. It also checks that the decrease in audit count falls within the number of entries older than 366 days in the baseline. This is not a byte-for-byte comparison of the entire database, and it does not prove the identity of each removed audit entry.

The tool assumes that the target already has the table structure needed by its queries. It does not migrate old databases. Application startup may add compatibility fields or remove expired audit entries. If protected tables change, investigate the evidence and cause rather than ignoring differences to make the check pass.

## 7. Check the running application

After file verification and database comparisons pass, use accounts with the appropriate permissions to check actual workflows: login and book switching, phone/tablet/desktop layouts, labour-expense filtering for a selected month, inventory batches and FIFO costs, Excel import/export, and permission restrictions. Use a dedicated test book or separate instance for checks that write data.

The health endpoint shows that the API responds. File hashes show that installed content matches the release directory. Database summaries check preservation of specified business data. None of these replaces interactive acceptance testing or a database restore rehearsal.
