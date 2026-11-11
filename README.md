# Restaurant Finance and Inventory Management System

[简体中文](<README (中文).md>) · [Changelog](CHANGELOG.md) · [Deployment](docs/DEPLOYMENT.md) · [Engineering reference](docs/ENGINEERING_REFERENCE.md)

A restaurant bookkeeping system with a responsive browser interface, a FastAPI/PostgreSQL backend and a Python desktop client. It connects income, expenses, purchasing, inventory, dish consumption and operating reports.

Current version: **v1.0.2**. Browser build revision: **`20261111-live-forecast-r2`**. Historical source is retained on `old/v1.0.0` and `old/V1.0.1`; the original V1.0.0 program uses the internal name `Oct30LingChen`.

## Features

- Independent ledgers, store income channels, user roles and time-limited editing permissions.
- Income, customer counts, purchases, fixed expenses, cash transactions and Excel exchange.
- Ingredient receipts, issues, losses, stocktakes and FIFO lot costs, with explicit unknown-price quantities.
- Five dashboard metrics and a full monthly report. Both use revenue through yesterday and costs saved through today to estimate month-end profit. Open **i** to compare last month’s and this month’s figures and see which was used for each cost. Completed months show actual net profit.
- The daily trend and weekday averages open on revenue. Each chart can independently show revenue, gross profit, net profit or ingredient costs including seasonings.
- Operating, expense and customer statistics with links to the underlying records.
- Responsive desktop/mobile charts, filtering, sorting and CSV export.
- Chinese and English browser interfaces that preserve user names and notes. The native desktop interface is Chinese.

Money uses Python `Decimal` and a browser decimal runtime backed by `BigInt`. Purchasing expense and FIFO consumption cost are separate accounting bases. The [engineering reference](docs/ENGINEERING_REFERENCE.md) documents formulas, modules, APIs, tables and development contracts.

## Dashboard preview

These screenshots use a synthetic ledger. The daily trend and weekday averages both open on revenue. Each chart has its own selector for revenue, gross profit, net profit, or ingredient and seasoning costs.

![October daily revenue with a selected day and its amount in CNY](docs/images/daily-revenue-en.png)

![Average revenue by weekday with Saturday selected and its mean in CNY](docs/images/weekday-revenue-en.png)

<details>
<summary>View the cost inputs behind the November forecast</summary>

The forecast help compares October and November for each cost. In this example, October supplies the fixed cost and November supplies both daily variable-cost rates.

<img src="docs/images/forecast-inputs-en.png" alt="October and November cost inputs and the selected source month for each cost" width="400">

</details>

## Run a new instance

The Compose setup provides PostgreSQL, the API and Nginx. It serves the web application and `/api/v1` from the same origin and binds the demonstration port to loopback by default.

```bash
cp .env.example .env
chmod 600 .env
# Edit .env: set independent POSTGRES_PASSWORD, SECRET_KEY and ADMIN_PASSWORD.
# Generate random values locally, for example: openssl rand -hex 32

docker compose config --quiet
docker compose up --build -d
curl --fail http://127.0.0.1:8080/api/v1/health
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) and sign in with the configured administrator account. Startup creates missing tables and the initial administrator; it does not reset an existing account's password. Create an independent book and assign user memberships through the application. The public configuration leaves the optional Test shortcut disabled.

The complete first-install procedure, native API setup, Nginx routing and existing-service upgrade procedure are in the [English deployment guide](docs/DEPLOYMENT.md), also available in [Chinese](docs/DEPLOYMENT.zh-CN.md). They are separate deployment paths: the existing Ubuntu upgrade script is not a Compose installer.

## Repository layout

```text
backend/                  FastAPI application, requirements and API tests
  app/                    models, routes, money, inventory and workbook logic
  tests/                  isolated regression fixtures and test modules
web/                      served static application and generated business scripts
build/
  web-exact-source/       editable business JavaScript source
  js-transform/          Acorn dependency and npm lockfile
  compile_exact_web.cjs   source-to-web transformation
  test_exact_web.cjs      browser money/business checks
  test_fifo_contract.py   browser/desktop cost and API quantity checks
  make_release.py        server archive builder
desktop/                  native Python source and its dependencies
deploy/                   Nginx configuration and deployment/verification tools
docs/                     bilingual deployment and engineering documentation
compose.yaml              independent local PostgreSQL/API/Nginx instance
README.md                 English documentation
README (中文).md          Chinese documentation
VERSION                   v1.0.2
```

## Development and tests

Use Python 3.12, Node.js and npm. The browser build only needs the Acorn dependency under `build/js-transform`; the Python API tests do not need a running production database.

```bash
cd /path/to/restaurant-finance-and-inventory-management-system

python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r build/test-requirements.txt

npm ci --prefix build/js-transform
node build/compile_exact_web.cjs
for test in web/test_*.js; do node "$test" || exit 1; done
node build/test_exact_web.cjs
node build/test_i18n_backend.cjs
python build/test_deployment_cache_revision.py
python build/test_distribution_privacy.py

(cd backend && PYTHONPATH=.:tests python -m pytest -q tests)
```

The test suite supplies its own isolated database fixtures and test environment defaults. Do not load a production environment file when running it. `build/test-requirements.txt` includes the API dependencies plus pytest, HTTPX and the subtest support used by the suite.

The FIFO contract imports the desktop module as well as the browser engine. On a supported macOS/Unix environment, install the additional desktop dependencies and run it after compiling the web scripts:

```bash
python -m pip install -r desktop/requirements.txt
python build/test_fifo_contract.py
```

`node` must be on `PATH`; alternatively set `NODE_BINARY` to its absolute path. The test uses Qt's offscreen platform. The source test environment uses Python 3.12 on macOS. Native dependency wheels have their own system requirements; check the complete runtime when rebuilding an application bundle. The desktop source imports `fcntl`, so Windows support is not claimed. Launch the native interface with `python desktop/restaurant_cost_manager.py` on a machine with a graphical session.

## Release packaging and verification

After the checks pass, generate the server archive from the checked-in source:

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

The archive has a `restaurant-cloud-v1.0.2/` root and contains `api/`, `web_frontend/`, `VERSION`, Nginx material and deployment/verification scripts. It does not include a database or runtime secrets. The builder refuses to overwrite an existing output; choose a new path for a subsequent build.

`deploy/verify_release_files.py` compares installed API/static files with a supplied release and checks the API health, version and required routes. `deploy/verify_deployment.py` captures PostgreSQL records in a read-only transaction and compares before/after evidence without printing payloads. The latter checks deployment preservation, not whether every user workflow is correct. Both need an explicitly chosen private evidence directory in the documented commands.

Write generated logs, QA screenshots, CSV exports, build manifests and deployment evidence into ignored directories such as `work/` or `dist/`. Application bundles, ZIPs, business data and runtime credentials stay outside the source repository. Test scripts, synthetic fixtures, reusable build tools and third-party license notices remain version controlled.

Browser acceptance, desktop tests, macOS universal rebuilding and complete-distribution packaging are documented in the [engineering reference](docs/ENGINEERING_REFERENCE.md).

## Current boundaries

The project has one PostgreSQL-backed API, static browser assets and a desktop source client. It does not include a payment gateway, bank reconciliation service, high-availability database setup, centralized monitoring or CI deployment pipeline. Schema initialization uses SQLAlchemy `create_all` plus specific compatibility additions in startup; there is no general migration framework. Changes to existing columns require an explicit migration plan.

The desktop source and browser use matching financial contracts where tested, but their interfaces are different. Rebuilding a signed/notarized macOS application, restoring a full server and validating a live deployment are separate tasks from cloning this repository.

## License

MIT. See [LICENSE](LICENSE).
