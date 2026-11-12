# Deployment guide

**[← Back to README](../README.en.md)** · [简体中文](DEPLOYMENT.zh-CN.md)

Use this guide for v1.0.2, web build `20261112-daily-pl`. If you are setting up the system for the first time, start with Docker Compose. It runs the website, API and database together.

| What do you need to do? | Where to start |
| --- | --- |
| Install the whole system on a new host | [Start with Compose](#1-start-a-new-instance-from-source) |
| Run the Python API for development | [Set up Python and PostgreSQL](#2-run-the-native-python-api-directly) |
| Back up a Compose installation | [Save the database, configuration and files](#3-back-up-a-compose-instance) |
| Update an Ubuntu server that already runs the API under systemd | [Build the archive](#4-build-a-release-archive-for-a-native-service), then [upgrade the service](#5-upgrade-an-existing-native-ubuntu-installation) |
| Check what the server is running | [Verify the files and database](#6-run-verification-separately), then [try the application](#7-check-the-running-application) |

For details about how the application stores records or calculates costs, see the [engineering reference](ENGINEERING_REFERENCE.md).

## 1. Start a new instance from source

On the host, install Git, Docker Engine with Compose v2, Python 3 and curl. Run the commands in a POSIX shell. Allow time for the first build to download the container images and Python dependencies.

The repository ships the runnable website in `web/`, so you can start Compose without Node.js. If you changed business logic in `build/web-exact-source/`, first [rebuild the web scripts](../README.en.md#run-the-tests). Edit `web/money.js`, HTML and CSS directly. Check the build marker below before starting. The version number alone also matches older v1.0.2 builds.

```bash
cd /path/to/restaurant-finance-and-inventory-management-system
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html || exit 1
```

**Create the Compose configuration.** From the repository root, use `.env.example` to create a private `.env` and generate three independent secrets. The template in `backend/` is for running the API directly.

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

Open `.env` locally to find the initial administrator password. You can also set `ADMIN_USERNAME` here before the first start. The script keeps the values out of terminal output and stops if `.env` exists. Its hexadecimal passwords can go straight into the database connection URL.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

When the API is ready, the health check returns `status: ok` and `version: v1.0.2`. If it fails on the first attempt, read `docker compose logs --tail=100 backend` and retry once the service has started.

**First sign-in.** Open <http://127.0.0.1:8080> on the host and sign in with the account in `.env`. Create a ledger for the store. When you add staff accounts, choose which ledgers each person can open. Startup creates the administrator only if the username is new. To change an existing account’s password, use account management.

### Services and persistent data

| Service or data | Configuration | Purpose |
| --- | --- | --- |
| `database` | PostgreSQL 16 | Stores accounts, books, business records, audit entries and permissions |
| `backend` | Python 3.12 and Uvicorn | Serves the API on port 8000 inside the container network |
| `web` | Nginx | Serves static files and proxies the API on the same origin |
| `postgres-data` volume | PostgreSQL data directory | Preserves the database when containers are recreated |
| `payment-secrets` volume | API path `/data/payment-secrets` | Stores merchant files received by the application |
| `recovery-files` volume | API path `/opt/restaurant-cloud/backups` | Stores recovery material produced by the application |

By default, only the website is published on the host, at `127.0.0.1:8080`. PostgreSQL and the API are reachable inside the Compose network. To serve the site over your domain, point the host’s HTTPS reverse proxy at `127.0.0.1:8080`. Set `WEB_BIND` and `WEB_PORT` in `.env` if you need a different listening address or port.

The default `TEST_LOGIN_ENABLED=false` keeps the demo login shortcut off. Staff can sign in with their own accounts. Startup leaves the legacy WeChat bill scheduler off, including when merchant files are present.

Use `docker compose stop` to pause the services and `docker compose up -d` to resume. `docker compose down` keeps the named volumes. Adding `-v` deletes those volumes, including the database.

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

Keep `proxy_pass` as shown, without a trailing slash. That preserves the full path, for example `/api/v1/auth/login`. Nginx serves everything else from the mounted `web/` directory. If the page opens but sign-in fails, check that requests under `/api/` reach the backend.

The Compose configuration also sets a 26 MB upload limit and tells browsers to revalidate cached files. On native installations `deploy/restaurant-cloud-upload.conf` supplies only those upload and cache settings. The host still needs its own Nginx `server` block.

## 2. Run the native Python API directly

Use this setup to debug the API or to run it with your own process manager and Nginx. Install Python 3.12 and give the application a role and database on a reachable PostgreSQL server. The application stores business records in PostgreSQL `JSONB`. SQLite support is limited to the test suite.

On a newly installed Ubuntu PostgreSQL server, these commands prompt for a password and create a database owned by the new role.

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

From the repository root, install the Python dependencies. Create `backend/.env` from the template on the first setup.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
(umask 077; set -C; cat .env.example > .env)
```

In `backend/.env`, set the PostgreSQL connection string, a random `SECRET_KEY` and the initial administrator password. Keep `TEST_LOGIN_ENABLED=false`. Percent-encode any reserved URL characters in the database password. Set `PAYMENT_SECRET_ROOT` to a directory outside the public source tree where the API can write merchant files.

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Uvicorn loads `.env` through the `python-dotenv` dependency included in `uvicorn[standard]`. Leave the process running and check both endpoints from a second terminal.

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

To serve the web interface alongside this API, point the host’s Nginx static root at `web/` and use `proxy_pass http://127.0.0.1:8000;` under `location /api/`. For a lasting installation, configure a service account, writable directories and a process manager. The Ubuntu upgrade script in section 5 expects that setup to exist already.

At startup, SQLAlchemy’s `create_all` creates missing tables. The application adds compatibility fields for older JSONB timing records, prepares the first administrator and legacy account memberships, and removes audit entries older than 366 days. If you change an existing column’s structure, plan a database migration for that change.

## 3. Back up a Compose instance

An Excel export can recover ledger entries. To recover the installation as a whole, also keep the database, private `.env`, merchant files, application recovery files and the source commit or release archive you deployed. The database includes staff accounts, permissions and audit records.

Pause writes while taking the backup so the database and its associated files cover the same period. Run the following in the repository root. It creates a separate directory for this backup.

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

The last line prints the backup directory. It holds `VERSION`, the complete-package manifest if present, and the commit ID if the checkout has a HEAD. A source ZIP has no Git history, so keep the ZIP or the exact source snapshot you deployed as well.

Copy the successful backup to private, durable storage outside the repository. The database and configuration contain business data and credentials. `pg_restore --list` confirms that PostgreSQL can read the archive. For a recovery test, restore it into a separate database, sign in, open a ledger and check its inventory.

On a native installation, take a PostgreSQL backup and save the runtime environment and merchant directory separately. The upgrade script makes its own copies of the API and web files. You supply the database backup.

## 4. Build a release archive for a native service

On the build machine, run the [browser build, API regression tests and FIFO inventory checks](../README.en.md#run-the-tests) for the checkout you intend to release. Then run the dashboard tests against the generated JavaScript and build the server archive.

```bash
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html &&
  node web/test_v1_0_2_dashboard.js &&
  python3 build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

The path above is the packager’s default. To keep a previous archive, choose a new filename for the next build. The packager stops if its output file already exists.

Inside the archive, `restaurant-cloud-v1.0.2/` contains these files.

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

The packager writes a `.sha256` file beside the archive. The archive contains the runtime files listed above and the three scripts at its root. It leaves out databases, private `.env` files, merchant keys, test modules and dependency caches. The SHA-256 manifest detects changes to contents. Verifying the publisher’s identity would require a separate signature.

Copy the archive and its `.sha256` file to the target host. In the directory containing both files, verify the checksum, extract into a fresh directory and check the web build marker.

```bash
sha256sum -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256 &&
mkdir restaurant-finance-release-check &&
tar -xzf restaurant-cloud-v1.0.2-deploy.tar.gz -C restaurant-finance-release-check &&
grep -Fq 'data-build-revision="20261112-daily-pl"' \
  restaurant-finance-release-check/restaurant-cloud-v1.0.2/web_frontend/index.html || exit 1
```

On macOS, use `shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256` for the checksum. Give the Ubuntu upgrade script the extracted `restaurant-cloud-v1.0.2/` directory.

## 5. Upgrade an existing native Ubuntu installation

Use `deploy_from_home_ubuntu.sh` on a host with the following existing services and directories. Compose installations have a different layout.

| Component | Location |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| Private runtime environment | `/opt/restaurant-cloud/.env.runtime` |
| Browser files | `/var/www/restaurant-web` |
| Nginx upload/cache snippet | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| Running systemd service | `restaurant-cloud.service` |
| Program backup and default evidence directory | `/opt/restaurant-cloud/backups/v1.0.2-UTCSTAMP-UNIQUE/` |

The script switches versions by renaming directories. The API and web roots must be physical directories, and both must share a filesystem with the backup and staging directories. Compare the installed `requirements.txt` and Nginx snippet with the release. The script stops if either differs, so handle dependency or Nginx changes before running it.

The upgrade reuses the installed Python environment (`python-dotenv`, SQLAlchemy and the PostgreSQL driver), systemd, Nginx, `flock`, curl and the other utilities it checks at startup. Python dependency installation and Nginx configuration are separate steps.

**Before the maintenance window:** verify the database backup and save the runtime configuration. Pause writes from staff, background jobs and other database clients. The upgrade compares protected records before and after the switch, so even a valid sale entered in between would change the result.

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2 \
  --base-url http://127.0.0.1
```

Use the upload path on your host in place of `/home/ubuntu/...`. The script uses both verifiers from the release by default. To supply your own paths, pass `--release-verifier` and `--db-verifier`. Results go in `evidence/` under this upgrade’s backup. To put them elsewhere, pass a new absolute path to `--evidence-dir`.

**What happens during the upgrade**

1. Check dependencies, the Nginx configuration and the service, acquire the deployment lock, then validate the release and filesystem layout.
2. Copy and verify the installed programs. Stage the API by overlaying the release on a copy of the existing API. Stage the web directory from the release and check that the staged Python sources compile.
3. Stop the API, confirm it has stopped, record the database baseline, then switch the API and web directories.
4. Start the service. Compare the reported version, installed files, HTTP assets, OpenAPI routes and protected database records with their expected values.
5. Once all checks pass, write `DEPLOYED_VERSION` in the evidence directory. The program backups and check results remain available.

If the switch fails, the script attempts to put the old API and web directories back and checks service health. If that rollback also fails, it reports the failure and keeps the directories for recovery. The rollback covers program files. Restoring PostgreSQL requires your database backup.

The script retains old backups. When you clean them up, keep the files needed for your recovery plan and the evidence for the current deployment.

## 6. Run verification separately

The upgrade runs both checks below. Run them separately when investigating an existing instance or when you need another record of the result. The examples use the native Ubuntu paths from section 5.

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

Set `--evidence-dir` to a fresh, private directory for each check. Read `release-check.json` there for the installed API and web file hashes, requirements, Nginx snippet, browser asset URLs and cache versions, health response and ingredient-name correction routes.

Set `--base-url` to the website. Set `--api-base-url` to the address where the API itself serves `/openapi.json`. The Ubuntu wrapper uses `http://127.0.0.1:8000` for the latter. Compose Nginx forwards `/api/` only, so its website address cannot serve the OpenAPI document.

### Same-version build revisions

The footer and health endpoint both say `v1.0.2` across several builds. Check that the served HTML declares `data-build-revision="20261112-daily-pl"` and that local asset URLs use `?v=v1.0.2-20261112-daily-pl`. The preflight and file verifier check this pairing as well as the files themselves. For older releases that declare no build revision, they expect the version alone.

Keep host details, credentials, backups and results for each actual deployment in private storage.

### PostgreSQL evidence before and after an upgrade

Run `before` with business writes paused. After the upgrade, run `after` in the same evidence directory before reopening writes.

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

The verifier opens a PostgreSQL `REPEATABLE READ`, `READ ONLY` transaction. It loads the database configuration directly, leaving application startup out of the check. It hashes JSONB using PostgreSQL’s own text representation so a Python float conversion cannot change the digest. The output contains counts, table hashes, the runtime environment file’s hash and pass/fail results. Ledger contents, account password hashes and configuration values stay out of the report.

`before` requires a new baseline. `after` needs that baseline to compare business records, timing fields, ingredient-name correction receipts, accounts, ledgers, memberships and temporary permissions. For audit cleanup it checks a narrower condition: the count may drop by at most the number of records already over 366 days old in the baseline. That count cannot identify which individual audit rows were deleted.

The target database must already have the tables and columns used by these queries. Handle schema migration separately. Startup may add compatibility fields or remove expired audit entries. If a protected table differs, inspect the results for that table before resuming writes.

## 7. Check the running application

After the server checks pass, reload an existing tab, then open the dashboard in a fresh tab. Use a dedicated test ledger or separate instance for checks that save or import records.

| What to check | What you should see |
| --- | --- |
| Dashboard in both languages | Five cards. Card 4 shows **Estimated daily profit/loss this month** with **(Estimated month-end profit/loss ÷ days in the month)** on the next line, an amount in CNY/day and a monthly comparison. Card 5 shows actual net profit and the net margin. In the [January/February 2024 example](ENGINEERING_REFERENCE.md#month-end-profitloss), card 4 rises from CNY 10.00/day to CNY 20.00/day, up 100.0%. |
| Daily trend and weekday charts | Both open on revenue. Switch only the weekday chart to ingredient cost. The daily trend should still show revenue. |
| Forecast details | For the same ledger and month, open **ⓘ** on the dashboard card and in the full monthly report. Both show the two months’ fixed costs, daily ingredient costs and daily other costs, and which amounts were used. The last three lines give projected daily total cost, total cost and revenue. A completed month shows actuals, with profit equal to actual revenue less actual total cost. |
| Mobile cost breakdown | Choose a day with several expenses. The ring colors match the legend. The amount and unit sit together in the center. |
| Save a purchase | In a test ledger with last month’s costs and revenue recorded before today in the current month, add a purchase dated today large enough to raise this month’s daily ingredient cost above last month’s. Both forecast panels should now use this month’s ingredient cost. Add revenue dated today. Projected revenue should still use income through yesterday. |
| Everyday operations | Sign in, switch ledgers, check phone, tablet and desktop layouts, filter labour expenses by month, inspect an inventory batch and its FIFO cost, and try Excel import/export. Compare what each assigned role can view or change. |
