# 部署指南

**[← 返回 README](../README.md)** · [English](DEPLOYMENT.md)

本指南适用于 v1.0.2，网页构建号为 `20261112-daily-pl`。第一次搭建系统，从 Docker Compose 开始。它会一起启动网页、API 和数据库。

| 你要做什么？ | 从这里开始 |
| --- | --- |
| 在新主机上安装整套系统 | [用 Compose 启动](#1-从源码启动一套新实例) |
| 为开发调试启动 Python API | [准备 Python 和 PostgreSQL](#2-直接运行原生-python-api) |
| 备份 Compose 实例 | [保存数据库、配置和文件](#3-备份-compose-实例) |
| 升级已用 systemd 运行 API 的 Ubuntu 服务器 | 先[制作发布包](#4-从仓库制作原生服务发布包)，再[升级服务](#5-升级已有-ubuntu-原生安装) |
| 检查服务器实际运行的版本 | 先[核对文件和数据库](#6-独立执行核验)，再[检查实际操作](#7-上线后的实际检查) |

要了解账目保存在哪里、成本如何计算，请看[工程技术参考](ENGINEERING_REFERENCE.zh-CN.md)。

## 1. 从源码启动一套新实例

在主机上安装 Git、Docker Engine、Compose v2、Python 3 和 curl。以下命令在兼容 POSIX 的 shell 中运行。第一次构建需要下载容器镜像和 Python 依赖。

仓库的 `web/` 已包含可直接运行的网页，使用 Compose 部署时无需安装 Node.js。如果改过 `build/web-exact-source/` 下的业务逻辑，请先[重新生成网页脚本](../README.md#运行测试)。`web/money.js`、HTML 和 CSS 直接在 `web/` 中修改。启动前核对下面的构建号，同为 v1.0.2 的旧构建也会显示相同的版本号。

```bash
cd /path/to/restaurant-finance-and-inventory-management-system
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html || exit 1
```

**创建 Compose 配置。** 在仓库根目录运行下面的命令，从 `.env.example` 生成只有当前用户能读取的 `.env`，并为三个配置项各生成一个独立的随机值。`backend/` 里的模板用于直接启动 API。

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

在本机打开 `.env` 查看初始管理员密码。要使用其他管理员用户名，在第一次启动前设置 `ADMIN_USERNAME`。上面的命令不会把密码打到终端；发现已有 `.env` 就会停止。生成的十六进制密码可以直接用于数据库连接地址。

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

API 就绪后，健康检查会返回 `status: ok` 和 `version: v1.0.2`。如果第一次请求失败，先用 `docker compose logs --tail=100 backend` 看启动日志，等服务启动完成再试。

**首次登录。** 在主机上打开 <http://127.0.0.1:8080>，用 `.env` 中的账号登录，为门店建一个账本。添加员工账号时，给每个人选好可以打开的账本。启动程序只在用户名不存在时创建管理员；已有账号需要改密码时，请在用户管理中操作。

### 服务与持久化

| 服务/数据 | 配置 | 作用 |
| --- | --- | --- |
| `database` | PostgreSQL 16 | 保存账号、账本、业务记录、审计和权限 |
| `backend` | Python 3.12、Uvicorn | 在容器网络内提供端口 8000 的 API |
| `web` | Nginx | 在同一个源下提供静态网页和 API 代理 |
| `postgres-data` 卷 | PostgreSQL 数据目录 | 重建容器后保留数据库 |
| `payment-secrets` 卷 | API 的 `/data/payment-secrets` | 保存由应用接收的商户文件 |
| `recovery-files` 卷 | API 的 `/opt/restaurant-cloud/backups` | 保存应用生成的恢复材料 |

默认只有网页端口对主机开放，地址为 `127.0.0.1:8080`。PostgreSQL 和 API 通过 Compose 内部网络访问。要让其他人通过域名使用系统，在主机上配置 HTTPS 反向代理，把请求转发到 `127.0.0.1:8080`。要调整监听地址或端口，在 `.env` 中设置 `WEB_BIND` 和 `WEB_PORT`。

`TEST_LOGIN_ENABLED=false` 默认关闭演示账号的快捷登录，员工可使用各自的账号。当前服务启动时不会开启旧版微信账单定时任务，即使已经配置商户文件也是如此。

用 `docker compose stop` 暂停服务，用 `docker compose up -d` 恢复。`docker compose down` 会保留命名卷；若加上 `-v`，包括数据库在内的这些卷都会被删除。

### 为什么需要同源代理

浏览器把 API 请求发往当前网站的 `/api/v1`，Nginx 再将请求转给后端。`deploy/nginx.conf` 使用下面这段配置。

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`proxy_pass` 的末尾不要加斜杠，这样转发后的地址才会保留 `/api/v1/auth/login` 等完整路径。其他页面文件由 Nginx 从挂载的 `web/` 目录读取。如果网页能打开却无法登录，请检查 `/api/` 的请求是否到达后端。

Compose 的 Nginx 配置还将上传上限设为 26 MB，并要求浏览器重新验证缓存。直接安装在主机上时，`deploy/restaurant-cloud-upload.conf` 只提供上传和缓存设置，主机还需配置 Nginx 的 `server` 块。

## 2. 直接运行原生 Python API

调试 API，或自行配置进程管理和 Nginx 时，可按这一节直接启动后端。安装 Python 3.12，并在可访问的 PostgreSQL 实例上为应用准备角色和数据库。业务记录使用 PostgreSQL 的 `JSONB` 类型；SQLite 只用于测试。

如果 Ubuntu 上刚装好 PostgreSQL，可用下面两条命令创建角色和归它所有的数据库。密码在交互提示中输入。

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

在仓库根目录创建 Python 环境并安装依赖。首次配置时，在 `backend/` 下从模板生成 `.env`。

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
(umask 077; set -C; cat .env.example > .env)
```

在 `backend/.env` 中填写 PostgreSQL 连接地址、随机生成的 `SECRET_KEY` 和初始管理员密码。保留 `TEST_LOGIN_ENABLED=false`。如果数据库密码里有 URL 保留字符，要先做百分号编码。把 `PAYMENT_SECRET_ROOT` 指向公开源码树之外、API 有权写入的目录，用来保存商户文件。

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

`uvicorn[standard]` 自带的 `python-dotenv` 会读取 `.env`。保持进程运行，另开一个终端检查这两个接口。

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

要让网页使用这个 API，把主机 Nginx 的静态根目录指向 `web/`，在 `location /api/` 下设置 `proxy_pass http://127.0.0.1:8000;`。长期运行还需要服务账号、可写目录和进程管理。第 5 节的 Ubuntu 升级脚本要求这些配置已经就绪。

启动时，SQLAlchemy 的 `create_all` 会建好缺失的表。应用还会补齐旧版 JSONB 时间记录所需的兼容字段、准备初始管理员和旧账号的账本授权，并清理超过 366 天的审计记录。要改已有列的结构，需要为该改动安排数据库迁移。

## 3. 备份 Compose 实例

Excel 导出可以用来恢复账本内容。要恢复整套系统，还要保存数据库、私有 `.env`、商户文件、应用生成的恢复文件，以及部署时使用的源码提交或发布包。员工账号、权限和审计记录都在数据库里。

先暂停记账和其他写入，让数据库和关联文件对应同一个备份时点。在仓库根目录运行以下命令，每次备份都会使用单独的目录。

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

最后一行会显示备份所在目录。其中包含 `VERSION`；如果有完整发行包清单或 Git 提交号，也会一并保存。下载的源码 ZIP 没有 Git 历史，请另存所用的 ZIP 或部署时的完整源码。

备份成功后，将文件复制到仓库以外、限制访问的持久存储中。数据库和配置含有账务数据和凭据。`pg_restore --list` 用于确认 PostgreSQL 能读取归档；要检验能否恢复，应还原到独立数据库，实际登录、打开账本并核对库存。

直接安装在主机上时，请自行备份 PostgreSQL，并另存运行环境配置和商户目录。升级脚本负责复制 API 和网页程序，数据库备份由你另行准备。

## 4. 从仓库制作原生服务发布包

在构建机上，针对准备发布的这份源码，先完成 [README 中的网页构建、API 回归测试和库存先进先出（FIFO）检查](../README.md#运行测试)。然后运行下面的命令，针对生成的网页脚本测试仪表盘，再制作服务器发布包。

```bash
grep -Fq 'data-build-revision="20261112-daily-pl"' web/index.html &&
  node web/test_v1_0_2_dashboard.js &&
  python3 build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

上面给出的是默认输出路径。如果要保留上次的包，下次打包时换一个输出文件名；指定路径已有文件时，打包器会停止。

解压后，`restaurant-cloud-v1.0.2/` 目录里有以下文件。

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

打包器在压缩包旁生成一个 `.sha256` 校验文件。包内是上面列出的运行文件和放在根目录的三个脚本；数据库、私有 `.env`、商户密钥、测试模块和依赖缓存均不在其中。SHA-256 清单用于核对文件内容；要验证发布者身份，还需单独的数字签名。

将压缩包和 `.sha256` 文件传到目标主机。在这两个文件所在目录运行以下命令，先验算校验值，再解压到新目录并核对网页构建号。

```bash
sha256sum -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256 &&
mkdir restaurant-finance-release-check &&
tar -xzf restaurant-cloud-v1.0.2-deploy.tar.gz -C restaurant-finance-release-check &&
grep -Fq 'data-build-revision="20261112-daily-pl"' \
  restaurant-finance-release-check/restaurant-cloud-v1.0.2/web_frontend/index.html || exit 1
```

在 macOS 上，校验命令是 `shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256`。Ubuntu 升级脚本的输入是解压后的 `restaurant-cloud-v1.0.2/` 目录。

## 5. 升级已有 Ubuntu 原生安装

已有 Ubuntu 实例的目录和服务符合下表时，才适用 `deploy_from_home_ubuntu.sh`。Compose 实例使用另一套目录结构。

| 项目 | 位置 |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| 私有运行环境 | `/opt/restaurant-cloud/.env.runtime` |
| 网页 | `/var/www/restaurant-web` |
| Nginx 上传/缓存片段 | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| 已运行的 systemd 服务 | `restaurant-cloud.service` |
| 本次程序备份与默认证据 | `/opt/restaurant-cloud/backups/v1.0.2-UTCSTAMP-UNIQUE/` |

脚本通过重命名目录来切换版本。API 和网页根目录必须是实际目录，并与备份及暂存目录位于同一文件系统。先对比已安装的 `requirements.txt` 和 Nginx 配置片段与包内文件。只要其中一个有差异，脚本就会停止，需要先处理依赖或 Nginx 配置变更。

升级时会复用现有 Python 环境（`python-dotenv`、SQLAlchemy、PostgreSQL 驱动）、systemd、Nginx、`flock`、curl 等脚本启动时会检查的工具。安装 Python 依赖和调整 Nginx 配置需要单独处理。

**升级前**先检查数据库备份能否恢复，并保存运行配置。暂停员工录入、后台任务以及其他数据库客户端的写入。脚本会比对切换前后的业务记录，即使中间只多录了一笔正常营业收入，核验结果也会出现差异。

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-v1.0.2 \
  --base-url http://127.0.0.1
```

把 `/home/ubuntu/...` 换成主机上的实际上传路径。脚本默认使用发布包中的两个核验程序；需要指定其他路径时，使用 `--release-verifier` 和 `--db-verifier`。结果默认写入本次备份的 `evidence/` 目录。若要另存，通过 `--evidence-dir` 指定一个尚不存在的绝对路径。

**脚本执行过程**

1. 检查依赖、Nginx 配置和服务状态，获取部署锁，然后核对发布包及目录所在的文件系统。
2. 复制并核对当前程序。在旧 API 的副本上覆盖新发布文件作为暂存 API；从发布包生成新的网页目录，并检查暂存的 Python 源码能否编译。
3. 停止 API，确认已停止，记录此时的数据库摘要，再切换 API 和网页目录。
4. 启动服务，核对版本号、安装文件、通过 HTTP 提供的资源、OpenAPI 路由，以及升级前后受保护的数据库记录。
5. 全部通过后，在核验目录写入 `DEPLOYED_VERSION`，保留程序备份和检查结果。

切换失败时，脚本会尝试恢复旧 API 和网页目录，再检查服务状态。如果回退也失败，脚本会报错并保留原目录，以便手动恢复。这一步恢复的是程序文件；恢复 PostgreSQL 需要另外使用数据库备份。

脚本会保留旧备份。之后清理时，请按恢复方案保留所需文件，并保存本次部署的核验记录。

## 6. 独立执行核验

升级脚本会自动执行下面两项检查。排查已有实例，或需要另存一份核验记录时，可以单独运行。示例沿用第 5 节的 Ubuntu 原生安装路径。

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

每次检查都用 `--evidence-dir` 指定一个新的私有目录。该目录的 `release-check.json` 记录已安装 API 和网页的文件哈希、依赖清单、Nginx 配置片段、网页资源地址和缓存版本、健康接口响应，以及食材品名更正接口的核验结果。

`--base-url` 填网页入口；`--api-base-url` 填能直接访问 `/openapi.json` 的 API 地址。Ubuntu 升级脚本默认用 `http://127.0.0.1:8000` 作为 API 地址。Compose 的 Nginx 只向后端转发 `/api/`，因此网页入口不能用来获取 OpenAPI 文档。

### 同版本构建修订

几个构建的页脚和健康接口都显示 `v1.0.2`。要分辨构建，请检查实际返回的 HTML 是否含有 `data-build-revision="20261112-daily-pl"`，本地资源地址是否带有 `?v=v1.0.2-20261112-daily-pl`。部署预检和文件核验程序会同时检查这个对应关系和文件本身。对于没有声明构建号的旧版本，它们按单独的版本号核验。

实际主机信息、凭据、备份和每次部署的核验结果请存放在私有位置。

### PostgreSQL 升级前后证据

暂停业务写入后运行 `before`。升级完成后，在恢复写入之前用同一个核验目录运行 `after`。

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

核验程序使用 PostgreSQL 的 `REPEATABLE READ`、`READ ONLY` 事务，直接读取数据库配置，检查期间不会触发应用启动。计算业务 JSONB 摘要时使用 PostgreSQL 自身的文本表示，避免经 Python 浮点转换改变结果。输出包含记录数、表摘要、运行环境文件的摘要及检查结果；账本内容、账号密码哈希和配置值均不会写入报告。

`before` 要求使用新基线；`after` 读取这份基线，比对业务记录、时间字段、食材品名更正回执、账号、账本、账本授权和临时权限。审计清理只检查数量：减少数不能超过升级前超过 366 天的记录数。这项检查无法识别具体删除了哪几条审计记录。

目标库须已有查询所需的表和列。需要迁移表结构时请单独处理。启动时应用可能会补兼容字段或清理过期审计记录；若受保护的表出现差异，请先查看该表的核验结果，再恢复写入。

## 7. 上线后的实际检查

服务器核验通过后，普通刷新已打开的标签页，再用新标签页打开仪表盘。涉及保存或导入数据的操作，请在专用测试账本或独立实例中进行。

| 检查什么 | 应该看到什么 |
| --- | --- |
| 中英文仪表盘 | 都有五张卡。第四张第一行为 **预计 本月每日盈亏**，第二行为 **(预计月底盈亏 ➗ 本月天数)**，下方是以元/天显示的金额和环比。第五张显示实际净利润和净利率。在[工程参考的一、二月算例](ENGINEERING_REFERENCE.zh-CN.md#预计月底盈亏)中，2024 年一月为 10.00 元/天，二月为 20.00 元/天，环比增加 100.0%。 |
| 本月趋势和各星期平均 | 两张图打开时都显示收入。只把星期图切到食材成本，本月趋势应继续显示收入。 |
| 预测说明 | 在同一账本、同一月份，分别打开主页卡片和完整月报里的 **ⓘ**。两处都列出两个月的固定成本、日均食材成本、日均其他成本及各项取值。最后三行是预计日均总成本、预计总成本和预计收入。已结束月份显示实际金额，盈亏等于实际收入减实际总成本。 |
| 手机上的开销构成 | 选择有多项开销的日期。圆环颜色应与图例一致，金额和单位在环心居中显示。 |
| 保存采购记录 | 在测试账本中准备好上月成本和本月昨天及以前的收入。录入一笔日期为今天的采购，金额要足以让本月日均食材成本超过上月。两处预测说明都应改用本月的食材成本。再记一笔今天的收入，预计收入仍应只计算到昨天。 |
| 日常操作 | 登录，切换账本，检查手机、平板和电脑排版。按月筛选人工支出，查看库存批次及先进先出成本，试用 Excel 导入导出，并分别核对不同角色能查看和修改哪些内容。 |
