# Deployment Guide

**[← Back to README](../README.en.md)** · [简体中文](DEPLOYMENT.zh-CN.md)

This guide covers v1.0.2, web build `20261112-daily-pl`. For a new installation, Docker Compose starts the web server, API, and PostgreSQL database together. For an existing Ubuntu installation managed by systemd, use the release archive and upgrade procedure in sections 4 and 5.

| Deployment task | Procedure |
| --- | --- |
| Install the system on a new host | [Start the Compose services](#1-start-a-new-instance-from-source) |
| Run the Python API for development | [Set up Python and PostgreSQL](#2-run-the-native-python-api-directly) |
| Back up a Compose installation | [Save the database, configuration, and files](#3-back-up-a-compose-instance) |
| Update an Ubuntu server that already runs the API under systemd | [Build the archive](#4-build-a-release-archive-for-a-native-service), then [upgrade the service](#5-upgrade-an-existing-native-ubuntu-installation) |
| Verify a running installation | [Verify the files and database](#6-run-verification-separately), then [check application workflows](#7-check-the-running-application) |

The [Engineering Reference](ENGINEERING_REFERENCE.md) describes how the application stores ledger entries and calculates costs.

## 1. Start a new instance from source

Install Git, Docker Engine with Compose v2, Python 3, and curl. Run the commands below in a POSIX-compatible shell. The first build downloads container images and Python dependencies.

The repository includes the compiled web application in `web/`. Compose can serve these files without Node.js. If you have edited business logic in `build/web-exact-source/`, [rebuild the browser scripts](../README.en.md#running-the-tests) first. Maintain `web/money.js`, HTML, and CSS directly in `web/`. Before starting Compose, confirm the build marker below to distinguish this build from earlier revisions of v1.0.2.

```bash
cd /path/to/restaurant-finance-and-inventory-management-system
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html || exit 1
```

From the repository root, run the script below to create `.env` with owner-only permissions. It generates separate values for the database password, token-signing key, and initial administrator password. Compose uses the root `.env.example` template. The template under `backend/` is for a standalone API.

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

Read the initial administrator password from the local `.env` file. To choose a different administrator username, set `ADMIN_USERNAME` before the first start. The script stops if `.env` already exists and never prints the generated values. Its hexadecimal database password needs no URL escaping.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

A healthy API returns `status: ok` and `version: v1.0.2`. If the first request fails, inspect the startup log with `docker compose logs --tail=100 backend` and retry after the service starts.

**First sign-in.** On the host, open <http://127.0.0.1:8080> and sign in with the administrator account from `.env`. Create a ledger for the store, then assign each staff account the ledgers it may access. Startup creates an administrator only if the configured username does not exist. Change existing passwords in the user management screen.

### Services and persistent data

| Service or data | Configuration | Purpose |
| --- | --- | --- |
| `database` | PostgreSQL 16 | Stores accounts, ledgers, business records, audit entries, and permissions |
| `backend` | Python 3.12 and Uvicorn | Serves the API on port 8000 inside the container network |
| `web` | Nginx | Serves static files and proxies the API on the same origin |
| `postgres-data` volume | PostgreSQL data directory | Preserves the database when containers are recreated |
| `payment-secrets` volume | API path `/data/payment-secrets` | Stores merchant files received by the application |
| `recovery-files` volume | API path `/opt/restaurant-cloud/backups` | Stores recovery material produced by the application |

By default, the web server listens on the host at `127.0.0.1:8080`. The API and PostgreSQL are accessible only within the Compose network. To make the site available under your domain, configure the host’s HTTPS reverse proxy to forward requests to `127.0.0.1:8080`. To change the listening address or port, set `WEB_BIND` or `WEB_PORT` in `.env`.

The default `TEST_LOGIN_ENABLED=false` disables the demo sign-in shortcut. Staff sign in with their own accounts. The legacy WeChat bill scheduler remains disabled at startup even when merchant files are present.

Stop the services with `docker compose stop` and restart them with `docker compose up -d`. Removing the containers with `docker compose down` preserves the named volumes. Adding `-v` deletes those volumes, including the database.

### Why the API uses the same origin

The browser sends all API requests to `/api/v1` on the same host that served the page. Nginx forwards those requests to the backend using this block in `deploy/nginx.conf`.

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Leave the trailing slash off `proxy_pass`. Nginx will then preserve the full request path, including `/api/v1/auth/login`. It serves static files from the mounted `web/` directory. If the page loads but sign-in fails, check whether requests to `/api/` reach the backend.

The Compose configuration also sets a 26 MB upload limit and tells browsers to revalidate cached files. On native installations `deploy/restaurant-cloud-upload.conf` supplies only those upload and cache settings. The host still needs its own Nginx `server` block.

## 2. Run the native Python API directly

A standalone API is useful for debugging or for an installation with its own process manager and Nginx configuration. Install Python 3.12 and provision a PostgreSQL role and database that the application can reach. Business records use PostgreSQL’s `JSONB` type. The SQLite adapter is used only in tests.

On a fresh Ubuntu PostgreSQL installation, use these commands to create the application role and a database it owns. Enter the password at the interactive prompt.

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

From the repository root, create the Python virtual environment and install the dependencies. For an initial installation, create `backend/.env` from its template.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
(umask 077; set -C; cat .env.example > .env)
```

In `backend/.env`, set the PostgreSQL connection string, a random `SECRET_KEY`, and the initial administrator password. Keep `TEST_LOGIN_ENABLED=false`. Percent-encode any URL-reserved characters in the database password. Point `PAYMENT_SECRET_ROOT` to a directory outside the public source tree where the API can write merchant files.

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Uvicorn loads `.env` through the `python-dotenv` dependency included in `uvicorn[standard]`. Leave the process running and check both endpoints from a second terminal.

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

To connect the website to this API, set Nginx’s static root to `web/` and use `proxy_pass http://127.0.0.1:8000;` under `location /api/`. A long-running installation also needs a service account, writable directories, and a process manager. The Ubuntu upgrade procedure in section 5 assumes they are already in place.

At startup, SQLAlchemy’s `create_all` creates any missing tables. The application adds compatibility fields for older entry timing records, creates the initial administrator, fills in missing staff assignments on legacy installations with a single business ledger, and removes audit entries older than 366 days. Changes to existing column definitions require a separate database migration.

## 3. Back up a Compose instance

An Excel export can restore entries for a ledger. To recover the full installation, retain the PostgreSQL database, private `.env` file, merchant files, application recovery files, and the source commit or release archive in use. PostgreSQL also holds staff accounts, permissions, and audit records.

Pause all writes for the duration of the backup so the database and related files reflect the same state. Run the following commands from the repository root to create a new backup directory.

```bash
(
  set -e
  umask 077
  mkdir -p ../restaurant-finance-backups
  chmod 700 ../restaurant-finance-backups
  finance_backup_dir="$(mktemp -d ../restaurant-finance-backups/manual-XXXXXXXX)"
  docker compose exec -T database pg_dump -U restaurant -d restaurant -Fc > "$finance_backup_dir/database.dump"
  docker compose exec -T backend tar -C /data -czf - payment-secrets > "$finance_backup_dir/payment-secrets.tar.gz"
  docker compose exec -T backend tar -C /opt/restaurant-cloud -czf - backups > "$finance_backup_dir/recovery-files.tar.gz"
  cp .env "$finance_backup_dir/runtime.env"
  cp VERSION "$finance_backup_dir/VERSION"
  if [ -e .git ] && git rev-parse --verify HEAD >/dev/null 2>&1; then
    git rev-parse HEAD > "$finance_backup_dir/source-commit.txt"
  fi
  if [ -f ../PACKAGE_MANIFEST.json ]; then
    cp ../PACKAGE_MANIFEST.json "$finance_backup_dir/PACKAGE_MANIFEST.json"
  fi
  docker compose exec -T database pg_restore --list < "$finance_backup_dir/database.dump" > "$finance_backup_dir/database-contents.txt"
  printf '%s\n' "$finance_backup_dir"
)
```

On success, the script prints the backup directory. It saves `VERSION`, the complete-package manifest if available, and the commit ID for a checkout with a Git HEAD. If you deployed a source ZIP, retain the archive or an exact copy of the deployed source as well. A ZIP does not contain Git history.

Copy the backup to access-controlled, durable storage outside the repository. The database and configuration contain business records and credentials. `pg_restore --list` checks whether PostgreSQL can read the archive. To test recovery, restore it to a separate database, sign in, open a ledger, and verify its inventory.

For a native installation, back up PostgreSQL, the runtime environment file, and the merchant directory as part of your backup procedure. The upgrade script separately copies the installed API and web files.

## 4. Build a release archive for a native service

On the build machine, follow the [README instructions for building the browser scripts, running the API regression tests, and checking FIFO inventory costing](../README.en.md#running-the-tests). Use the same checkout for the dashboard tests and the server archive below.

```bash
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html &&
  node web/test_v1_0_2_dashboard.js &&
  python3 build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

The path above is the default output location. The packager creates a new archive on each run and stops if the filename already exists. Choose another output filename to keep the previous archive.

The archive has the following layout under `restaurant-cloud-v1.0.2/`.

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

The packager writes a `.sha256` file alongside the archive. It packages the runtime files and three scripts listed above. Databases, private `.env` files, merchant keys, test modules, and dependency caches are excluded. The manifest records file hashes for integrity checks. Authenticating the publisher requires a separate digital signature.

Transfer the archive and its `.sha256` file to the target host. From the directory containing both files, verify the checksum, extract the archive into a new directory, and confirm the web build marker.

```bash
sha256sum -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256 &&
mkdir restaurant-finance-release-check &&
tar -xzf restaurant-cloud-v1.0.2-deploy.tar.gz -C restaurant-finance-release-check &&
grep -Fq 'data-build-revision="20261112-daily-pl"' \
  restaurant-finance-release-check/restaurant-cloud-v1.0.2/web_frontend/index.html || exit 1
```

On macOS, verify the checksum with `shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256`. Pass the extracted `restaurant-cloud-v1.0.2/` directory to the Ubuntu upgrade script.

## 5. Upgrade an existing native Ubuntu installation

Use `deploy_from_home_ubuntu.sh` on a host with the following existing services and directories. Compose installations have a different layout.

| Component | Location |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| Private runtime configuration | `/opt/restaurant-cloud/.env.runtime` |
| Browser files | `/var/www/restaurant-web` |
| Nginx upload/cache snippet | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| Running systemd service | `restaurant-cloud.service` |
| Program backup and verification reports (default location) | `/opt/restaurant-cloud/backups/v1.0.2-UTCSTAMP-UNIQUE/` |

The script renames directories to switch versions. Symbolic links are unsupported for the API and web root directories. Both must be on the same filesystem as the backup and staging directories. If either the installed `requirements.txt` or the Nginx configuration snippet differs from its release copy, the script stops. Resolve the difference before upgrading.

The upgrade uses the existing Python environment, including `python-dotenv`, SQLAlchemy, and the PostgreSQL driver. It also checks for systemd, Nginx, `flock`, curl, and the other host utilities it needs. Install Python dependencies or update Nginx separately when required.

**Before upgrading**, verify the database backup and save the runtime configuration. Pause writes from staff accounts, background jobs, and other database clients. The upgrade compares protected records before and after the switch. A sale recorded during the maintenance window would appear as a discrepancy.

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2 \
  --base-url http://127.0.0.1
```

Replace `/home/ubuntu/...` with the upload directory on the target host. By default, the script runs both verification tools included in the release. Use `--release-verifier` and `--db-verifier` to specify other paths. It writes the results to `evidence/` in the backup directory for this upgrade. To choose another destination, pass an unused absolute path to `--evidence-dir`.

**Upgrade sequence**

1. Check dependencies, Nginx configuration, and service status. Acquire the deployment lock and validate the release and filesystem layout.
2. Copy and verify the installed programs. Stage the API by overlaying the release on a copy of the existing API. Stage the web directory from the release and check that the staged Python sources compile.
3. Stop the API and confirm that the service is inactive. Record the database baseline and switch the API and web directories.
4. Start the service. Compare the reported version, installed files, HTTP assets, OpenAPI routes, and protected database records with their expected values.
5. Once all checks pass, write `DEPLOYED_VERSION` in the evidence directory. The program backups and check results remain available.

If the switch fails, the script attempts to restore the previous API and web directories, then checks service health. If rollback fails, it reports the error and retains the directories for manual recovery. Database recovery requires a PostgreSQL backup.

The script retains old backups. When you clean them up, keep the files needed for your recovery plan and the evidence for the current deployment.

## 6. Run verification separately

The upgrade script runs both verification tools automatically. Run them individually to investigate an existing installation or capture a separate verification report. The examples use the Ubuntu paths in section 5.

### Release files and HTTP

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/verify_release_files.py \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2 \
  --api-dir /opt/restaurant-cloud/api \
  --web-dir /var/www/restaurant-web \
  --nginx-conf /etc/nginx/conf.d/restaurant-cloud-upload.conf \
  --base-url http://127.0.0.1 \
  --api-base-url http://127.0.0.1:8000 \
  --expected-version v1.0.2 \
  --evidence-dir /opt/restaurant-cloud/backups/manual-release-check-001
```

Set `--evidence-dir` to a new, private directory for each run. The verifier writes `release-check.json` there. It checks the installed API and web files, Python requirements, Nginx settings, browser asset URLs and cache versions, the health response, and the routes for correcting ingredient names.

Use the website URL for `--base-url` and the API URL that serves `/openapi.json` for `--api-base-url`. The Ubuntu upgrade script uses `http://127.0.0.1:8000` for the API by default. The Compose Nginx server forwards only paths under `/api/`, so use the direct API address for the OpenAPI document.

### Same-version build revisions

The footer and the health endpoint identify the release as `v1.0.2`. Multiple web builds share that version number. To identify this build, check the HTML returned by the server for `data-build-revision="20261112-daily-pl"` and check its local asset URLs for `?v=v1.0.2-20261112-daily-pl`. The deployment preflight and file verifier check the build marker, asset versions, and file contents. Older releases without a build marker use the version number alone in the asset URLs.

Store host details, credentials, backups, and deployment reports in access-controlled storage.

### PostgreSQL evidence before and after an upgrade

Pause business writes and run `before` to record a baseline. After the upgrade, run `after` against the same evidence directory before allowing writes to resume.

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/verify_deployment.py before \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001

# Run after updating the application:
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/verify_deployment.py after \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001
```

The verifier reads PostgreSQL in a read-only transaction at `REPEATABLE READ` isolation. It loads the database configuration without starting the application. When hashing JSONB records, it uses PostgreSQL’s text representation to preserve numeric precision. The report contains row counts, table hashes, the runtime configuration file’s hash, and check results. It omits ledger contents, account password hashes, and configuration values.

`before` writes a new baseline. `after` uses it to compare business records, timing fields, ingredient-name correction receipts, accounts, ledgers, memberships, and temporary permissions. Audit retention is checked by count. The decrease may be no greater than the number of audit entries already older than 366 days at baseline. Counts cannot identify individual deleted rows.

The target database must contain the tables and columns used by the verifier. Apply any necessary schema migration separately. Startup may add compatibility fields or purge expired audit entries. Investigate discrepancies in protected tables before resuming writes.

## 7. Check the running application

Once server verification passes, reload an existing browser tab and open the dashboard in a new tab. Use a dedicated test ledger or separate instance for any checks that write or import data.

| Check | Procedure and expected result |
| --- | --- |
| Dashboard in both languages | The dashboard has five cards. Card 4 shows **Estimated daily profit/loss this month** with **(Estimated month-end profit/loss ÷ days in the month)** on the next line. Below the heading, it shows an amount in CNY/day and a month-over-month comparison. Card 5 shows actual net profit and the net margin. In the [January/February 2024 example](ENGINEERING_REFERENCE.md#month-end-profitloss), card 4 rises from CNY 10.00/day to CNY 20.00/day, up 100.0%. |
| Daily trend and weekday charts | Both open on revenue. Switch only the weekday chart to ingredient cost. The daily trend should still show revenue. |
| Forecast details | For the same ledger and month, open **ⓘ** on the dashboard card and in the full monthly report. Both show the two months’ fixed costs, daily ingredient costs, and daily other costs. Each panel identifies the values used. The last three lines give projected daily total cost, total cost, and revenue. A completed month shows actuals, with profit equal to actual revenue less actual total cost. |
| Mobile cost breakdown | Choose a day with several expenses. The ring colors match the legend. The amount and unit sit together in the center. |
| Save a purchase | In a test ledger with last month’s costs and revenue recorded before today in the current month, add a purchase dated today large enough to raise this month’s daily ingredient cost above last month’s. Both forecast panels should now use this month’s ingredient cost. Add revenue dated today. Projected revenue should still use income through yesterday. |
| Everyday operations | Sign in, switch ledgers, check phone, tablet, and desktop layouts, filter labour expenses by month, inspect an inventory batch and its FIFO cost, and test Excel import and export. Compare what each assigned role can view or change. |
