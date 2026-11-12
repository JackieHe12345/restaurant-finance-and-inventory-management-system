# 部署指南

**[← 返回 README](../README.md)** · [English](DEPLOYMENT.md)

本指南适用于 v1.0.2，网页构建号为 `20261112-daily-pl`。新建实例时，使用 Docker Compose 一并启动网页服务器、API 和 PostgreSQL 数据库。已有 Ubuntu 实例若由 systemd 管理，请按第 4、5 节制作发布包并升级服务。

| 部署任务 | 对应步骤 |
| --- | --- |
| 在新主机上安装整套系统 | [启动 Compose 服务](#1-从源码启动一套新实例) |
| 为开发调试启动 Python API | [准备 Python 和 PostgreSQL](#2-直接运行原生-python-api) |
| 备份 Compose 实例 | [保存数据库、配置和文件](#3-备份-compose-实例) |
| 升级由 systemd 管理 API 的现有 Ubuntu 实例 | 先[制作发布包](#4-从仓库制作原生服务发布包)，再[升级服务](#5-升级已有-ubuntu-原生安装) |
| 核验运行中的实例 | 先[核对文件和数据库](#6-独立执行核验)，再[检查业务功能](#7-上线后的实际检查) |

账目如何存储、成本如何计算，见[工程技术参考](ENGINEERING_REFERENCE.zh-CN.md)。

## 1. 从源码启动一套新实例

在主机上安装 Git、带 Compose v2 的 Docker Engine、Python 3 和 curl。以下命令适用于兼容 POSIX 的 shell。首次构建会下载容器镜像和 Python 依赖。

仓库的 `web/` 目录已包含构建好的网页文件，使用 Compose 部署时无需安装 Node.js。若修改了 `build/web-exact-source/` 中的业务逻辑，请先[重新生成网页脚本](../README.md#运行测试)。`web/money.js`、HTML 和 CSS 直接在 `web/` 中维护。启动 Compose 前，请核对下列构建号，以区分 v1.0.2 的不同构建。

```bash
cd /path/to/restaurant-finance-and-inventory-management-system
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html || exit 1
```

在仓库根目录运行以下脚本，创建仅文件所有者可读写的 `.env`。脚本分别为数据库密码、令牌签名密钥和初始管理员密码生成随机值。Compose 使用根目录的 `.env.example` 模板；`backend/` 下的模板供单独启动 API 时使用。

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

在本机的 `.env` 文件中查看初始管理员密码。如需更改管理员用户名，请在首次启动前设置 `ADMIN_USERNAME`。脚本遇到已有的 `.env` 会退出，生成的值也不会出现在终端中。数据库密码采用十六进制字符，可直接写入连接地址，无需转义。

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

API 正常时，健康检查返回 `status: ok` 和 `version: v1.0.2`。若首次请求失败，请运行 `docker compose logs --tail=100 backend` 查看启动日志，待服务就绪后重试。

**首次登录。** 在主机上打开 <http://127.0.0.1:8080>，使用 `.env` 中的管理员账号登录。先为门店创建账本，再为各员工账号分配可访问的账本。只有配置的用户名尚不存在时，服务才会在启动时创建管理员账号。已有账号的密码可在「用户管理」中修改。

### 服务与持久化

| 服务或数据卷 | 配置 | 作用 |
| --- | --- | --- |
| `database` | PostgreSQL 16 | 保存账号、账本、业务记录、审计和权限 |
| `backend` | Python 3.12、Uvicorn | 在容器网络内通过 8000 端口提供 API 服务 |
| `web` | Nginx | 提供静态网页，并通过同源地址转发 API 请求 |
| `postgres-data` 卷 | PostgreSQL 数据目录 | 重建容器后保留数据库 |
| `payment-secrets` 卷 | API 的 `/data/payment-secrets` | 保存由应用接收的商户文件 |
| `recovery-files` 卷 | API 的 `/opt/restaurant-cloud/backups` | 保存应用生成的恢复文件 |

默认情况下，主机只开放网页服务的本地监听端口 `127.0.0.1:8080`，API 和 PostgreSQL 仅在 Compose 内部网络中提供服务。如需通过域名访问，请配置主机的 HTTPS 反向代理，将请求转发至 `127.0.0.1:8080`。要调整监听地址或端口，在 `.env` 中设置对应的 `WEB_BIND` 或 `WEB_PORT`。

`TEST_LOGIN_ENABLED=false` 默认关闭演示账号的快捷登录入口，员工使用各自的账号登录。即使已配置商户文件，服务启动时也不会启用旧版微信账单定时任务。

使用 `docker compose stop` 停止服务，使用 `docker compose up -d` 重新启动。`docker compose down` 会移除容器并保留命名卷。加上 `-v` 会一并删除这些卷，其中包括数据库。

### 为什么需要同源代理

浏览器向当前网站的 `/api/v1` 发送请求，由 Nginx 转发至后端。对应配置位于 `deploy/nginx.conf`。

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

保持示例中的 `proxy_pass` 写法，末尾不加斜杠，以保留 `/api/v1/auth/login` 等完整请求路径。Nginx 从挂载的 `web/` 目录读取静态文件。如果页面加载正常却无法登录，请检查 `/api/` 下的请求能否到达后端。

Compose 的 Nginx 配置还将上传上限设为 26 MB，并要求浏览器重新验证缓存。直接安装在主机上时，`deploy/restaurant-cloud-upload.conf` 只提供上传和缓存设置，主机还需配置 Nginx 的 `server` 块。

## 2. 直接运行原生 Python API

调试 API，或自行配置进程管理器和 Nginx 时，可以单独启动后端。主机需要 Python 3.12，还需在应用可访问的 PostgreSQL 服务器上创建角色和数据库。业务记录使用 PostgreSQL 的 `JSONB` 类型，SQLite 适配器仅用于测试。

在新装的 Ubuntu PostgreSQL 实例上，使用以下命令创建应用角色，并将新数据库的所有权授予该角色。按提示输入密码。

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

在仓库根目录创建 Python 虚拟环境并安装依赖。首次安装时，再使用模板创建 `backend/.env`。

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
(umask 077; set -C; cat .env.example > .env)
```

在 `backend/.env` 中填写 PostgreSQL 连接地址、随机生成的 `SECRET_KEY` 和初始管理员密码，并保留 `TEST_LOGIN_ENABLED=false`。数据库密码中如含有 URL 保留字符，须进行百分号编码。将 `PAYMENT_SECRET_ROOT` 设为公开源码目录之外、API 有权写入的目录，用于保存商户文件。

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

`uvicorn[standard]` 自带的 `python-dotenv` 会读取 `.env`。保持进程运行，另开一个终端检查这两个接口。

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

要让网页连接此 API，请将 Nginx 静态根目录设为 `web/`，并在 `location /api/` 中设置 `proxy_pass http://127.0.0.1:8000;`。长期运行的实例还需配置服务账号、可写目录和进程管理器。第 5 节的 Ubuntu 升级步骤以这些配置已就绪为前提。

启动时，SQLAlchemy 的 `create_all` 会创建缺失的表。应用会为旧版录入时间记录补充兼容字段，创建初始管理员，为只有一个业务账本的旧实例补齐员工账号缺少的账本授权，并清理超过 366 天的审计记录。修改已有列的定义需单独执行数据库迁移。

## 3. 备份 Compose 实例

Excel 导出可用于恢复账本内容。若要恢复整个实例，还需保留 PostgreSQL 数据库、私有 `.env` 文件、商户文件、应用生成的恢复文件，以及部署时使用的源码提交或发布包。员工账号、权限和审计记录也存储在 PostgreSQL 中。

备份期间请暂停所有写入，确保数据库和关联文件反映同一时点的状态。在仓库根目录运行以下命令，为本次备份创建独立目录。

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

备份成功后，脚本会输出备份目录的路径。目录中包含 `VERSION`，若有完整发行包清单或 Git 提交号，也会一并保存。若使用源码 ZIP 部署，请另存原压缩包或当时的完整源码。ZIP 不含 Git 历史。

请将备份转存到仓库之外、限制访问的长期存储中。数据库和配置文件含有账务数据及访问凭据。`pg_restore --list` 用于检查 PostgreSQL 能否读取归档。要验证能否恢复，请还原到独立数据库，然后实际登录、打开账本并核对库存。

直接在主机上安装时，备份范围应包括 PostgreSQL、运行环境配置文件和商户目录。升级脚本另行备份已安装的 API 和网页文件。

## 4. 从仓库制作原生服务发布包

在构建机上，先按 [README](../README.md#运行测试) 构建网页脚本、运行 API 回归测试，并核对库存先进先出（FIFO）成本。随后在同一份源码中运行以下仪表盘测试并生成服务器发布包。

```bash
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html &&
  node web/test_v1_0_2_dashboard.js &&
  python3 build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

上面是默认输出路径。打包器只创建新文件，如果同名归档已存在就会停止。如需保留此前的归档，请使用其他输出文件名。

归档内的文件位于 `restaurant-cloud-v1.0.2/`，目录结构如下。

```text
api/app/                            Python API 源码
api/requirements.txt                API 依赖
web_frontend/                       生成后的网页运行文件
nginx/restaurant-cloud-upload.conf  原生 Nginx 上传/缓存片段
VERSION                             发布版本
MANIFEST.json                       所包含文件的 SHA-256
deploy_from_home_ubuntu.sh         原生升级脚本
verify_deployment.py               PostgreSQL 前后证据
verify_release_files.py            文件与 HTTP 核验
```

打包器在归档旁生成 `.sha256` 校验文件。包内含上述运行文件和三个脚本，不含数据库、私有 `.env`、商户密钥、测试模块或依赖缓存。文件清单记录各文件的哈希值，用于检查内容是否完整。验证发布者身份还需单独的数字签名。

将归档和 `.sha256` 文件传至目标主机，进入文件所在目录，依次校验归档、解压至新目录，并核对网页构建号。

```bash
sha256sum -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256 &&
mkdir restaurant-finance-release-check &&
tar -xzf restaurant-cloud-v1.0.2-deploy.tar.gz -C restaurant-finance-release-check &&
grep -Fq 'data-build-revision="20261112-daily-pl"' \
  restaurant-finance-release-check/restaurant-cloud-v1.0.2/web_frontend/index.html || exit 1
```

macOS 上可使用 `shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256` 校验归档。运行 Ubuntu 升级脚本时，传入解压后的 `restaurant-cloud-v1.0.2/` 目录。

## 5. 升级已有 Ubuntu 原生安装

已有 Ubuntu 实例的目录和服务符合下表时，才适用 `deploy_from_home_ubuntu.sh`。Compose 实例使用另一套目录结构。

| 项目 | 位置 |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| 私有运行配置 | `/opt/restaurant-cloud/.env.runtime` |
| 网页 | `/var/www/restaurant-web` |
| Nginx 上传与缓存配置片段 | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| 已运行的 systemd 服务 | `restaurant-cloud.service` |
| 程序备份和核验报告的默认目录 | `/opt/restaurant-cloud/backups/v1.0.2-UTCSTAMP-UNIQUE/` |

脚本通过重命名目录切换版本。API 和网页根目录都必须直接指向实际目录，不支持符号链接，且与备份、暂存目录位于同一文件系统。已安装的 `requirements.txt` 或 Nginx 配置片段只要与包内对应文件不同，脚本就会停止。请在升级前处理差异。

升级使用现有 Python 环境，包括 `python-dotenv`、SQLAlchemy 和 PostgreSQL 驱动。脚本还会检查 systemd、Nginx、`flock`、curl 等所需工具。如需安装 Python 依赖或更新 Nginx 配置，请单独处理。

**升级前**请验证数据库备份并保存运行配置。暂停员工录入、后台任务及其他数据库客户端的写入。脚本会比较切换前后的业务记录；维护期间即使是正常录入的一笔收入，也会被列为数据差异。

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2 \
  --base-url http://127.0.0.1
```

将 `/home/ubuntu/...` 替换为目标主机上的实际上传路径。脚本默认运行包内的两个核验程序；如需使用其他路径，可通过 `--release-verifier` 和 `--db-verifier` 指定。结果默认保存在本次备份目录的 `evidence/` 中。要另存到其他位置，可为 `--evidence-dir` 指定一个尚不存在的绝对路径。

**升级流程**

1. 检查依赖、Nginx 配置和服务状态，取得部署锁后，核对发布包及相关目录所在的文件系统。
2. 复制并核对当前程序。在当前 API 的副本中覆盖新版文件，准备待切换的 API 目录。再从发布包生成网页目录，并检查暂存的 Python 源码能否编译。
3. 停止 API。确认服务已停止后，记录数据库基线，再切换 API 和网页目录。
4. 启动服务，核对版本号、安装文件、通过 HTTP 提供的资源、OpenAPI 路由，以及升级前后受保护的数据库记录。
5. 全部通过后，在核验目录写入 `DEPLOYED_VERSION`，保留程序备份和检查结果。

若版本切换失败，脚本会尝试恢复原 API 和网页目录，并检查服务状态。若回退也失败，脚本会报错并保留原目录，以便手动恢复。数据库恢复需使用 PostgreSQL 备份。

脚本会保留旧备份。之后清理时，请按恢复方案保留所需文件，并保存本次部署的核验记录。

## 6. 独立执行核验

升级脚本会自动运行两个核验程序。排查已有实例或需要独立的核验报告时，也可分别执行。以下示例沿用第 5 节的 Ubuntu 安装路径。

### 发布文件与 HTTP

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

每次核验都用 `--evidence-dir` 指定一个新的私有目录。程序将结果写入其中的 `release-check.json`，检查范围包括已安装的 API 和网页文件、Python 依赖清单、Nginx 配置、网页资源地址及缓存版本、健康检查响应，以及食材品名更正接口。

`--base-url` 使用网页入口地址，`--api-base-url` 使用能够直接访问 `/openapi.json` 的 API 地址。Ubuntu 升级脚本默认使用 `http://127.0.0.1:8000` 访问 API。Compose 的 Nginx 只转发 `/api/` 下的请求，获取 OpenAPI 文档时需直接访问 API。

### 同版本构建修订

页脚和健康接口报告的发布版本均为 `v1.0.2`，同一版本可包含多个网页构建。要确认是否为本次构建，请检查服务器返回的 HTML 中是否含有 `data-build-revision="20261112-daily-pl"`，以及本地资源地址是否带有 `?v=v1.0.2-20261112-daily-pl`。部署预检和文件核验程序会检查构建号、资源版本及文件内容。未声明构建号的旧版本只在资源地址中标记版本号。

主机信息、凭据、备份和部署报告应存放在限制访问的存储位置。

### PostgreSQL 升级前后证据

暂停业务写入，运行 `before` 记录基线。升级完成后，在同一核验目录中运行 `after`，再恢复写入。

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/verify_deployment.py before \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001

# 完成程序更新后再执行：
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/verify_deployment.py after \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001
```

核验程序在 `REPEATABLE READ` 隔离级别下以只读事务查询 PostgreSQL，直接读取数据库配置，无需启动应用。计算 JSONB 记录的哈希值时，程序使用 PostgreSQL 自身的文本表示，以保留数值精度。报告包含记录数、表摘要、运行配置文件的摘要及检查结果，不含账本内容、账号密码哈希或具体配置值。

`before` 写入新的基线，`after` 据此比较业务记录、时间字段、食材品名更正回执、账号、账本、授权关系和临时权限。审计记录按数量核验，允许减少的上限为基线中已超过 366 天的记录数。仅凭数量无法确定具体删除了哪些记录。

目标数据库须已包含核验查询涉及的表和列。如需迁移表结构，应单独执行。服务启动时可能会补充兼容字段或清理过期审计记录。受保护的表若有差异，请查明原因后再恢复写入。

## 7. 上线后的实际检查

服务器核验通过后，刷新已打开的浏览器标签页，并在新标签页中打开仪表盘。涉及写入或导入数据的检查，请使用专用测试账本或独立实例。

| 检查项目 | 操作与预期结果 |
| --- | --- |
| 中英文仪表盘 | 两种语言下均显示五张指标卡。第四张的首行为 **预计 本月每日盈亏**，第二行为 **(预计月底盈亏 ➗ 本月天数)**，标题下方显示金额（元/天）及环比变动。第五张显示实际净利润和净利率。按[工程技术参考](ENGINEERING_REFERENCE.zh-CN.md#预计月底盈亏)中 2024 年 1 月和 2 月的算例，第四张卡由 10.00 元/天升至 20.00 元/天，环比增长 100.0%。 |
| 本月趋势和各星期平均 | 两张图默认均显示收入。将「各星期平均」切换为食材成本，「本月趋势」应继续显示收入。 |
| 预测说明 | 在同一账本中选择同一月份，分别打开主页卡片和完整月报中的 **ⓘ**。两处均列出上月和本月的固定成本、日均食材成本和日均其他成本，并标明预测采用的数值。最后三行是预计日均总成本、预计总成本和预计收入。已结束月份显示实际金额，盈亏等于实际收入减实际总成本。 |
| 手机端开销构成 | 选择有多笔支出的日期。圆环各色块应与图例对应，金额与单位应在圆心居中显示。 |
| 保存采购记录 | 在测试账本中先录入上个月的成本和本月截至昨天的收入。录入一笔日期为今天的采购，金额要足以让本月日均食材成本超过上月。两处预测说明均应显示采用本月食材成本。再记一笔今天的收入，预计收入仍应只计算到昨天。 |
| 日常操作 | 登录并切换账本，检查手机、平板和电脑的页面布局。按月筛选人工支出，查看库存批次及先进先出成本，验证 Excel 导入与导出，并核对各角色的查看和修改权限。 |
