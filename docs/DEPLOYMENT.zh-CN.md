# restaurant-finance-and-inventory-management-system 部署指南

[返回 README](../README%20%28%E4%B8%AD%E6%96%87%29.md) · [English](DEPLOYMENT.md) | 简体中文

本指南对应 `Oct30LingChen`。新实例推荐使用仓库根目录的 Docker Compose；已有 Ubuntu 原生服务使用单独的发布包升级流程。两者的目录、运行环境和操作命令不同。

文中的主机路径是安装约定，不是生产凭据。以下步骤说明如何安装和核验，不表示任何生产服务器已经完成部署或验收。

## 1. 从源码启动一套新实例

主机需要安装 Git、Docker Engine、Docker Compose v2、Python 3 和 curl，并在 POSIX shell 中执行以下命令。首次启动会从镜像仓库和 Python 包源下载依赖。仓库已包含生成后的网页文件，因此直接部署无需先安装 Node.js；修改网页业务源码后，应按 README 中的构建步骤重新生成 `web/`。

业务脚本源码位于 `build/web-exact-source/`。共用十进制运行时 `web/money.js` 和 HTML/CSS 静态资源直接在 `web/` 中维护，编译器不会生成或复制它们。

```bash
git clone https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system.git
cd restaurant-finance-and-inventory-management-system
```

根目录的 `.env.example` 用于 Compose，`backend/.env.example` 用于直接运行 Python API。两份文件用途不同。可以用下面的命令从根目录模板创建私有配置，分别生成数据库密码、JWT 密钥和初始管理员密码：

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

该命令不打印生成的值，也不会覆盖已有 `.env`。用本机编辑器查看管理员密码，并按需修改 `ADMIN_USERNAME`。数据库密码直接插入 `DATABASE_URL`，使用生成的十六进制字符可避免 URL 保留字符的转义问题。

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

首次构建和 API 启动可能需要一段时间；若健康检查暂时失败，先看 `docker compose logs --tail=100 backend`，确认服务启动后再检查。成功响应中的 `status` 应为 `ok`，`version` 应为 `Oct30LingChen`。

打开 <http://127.0.0.1:8080>，使用 `.env` 中的管理员登录。创建独立账本后，再创建其他账号并分配账本。初始管理员只在同名账号不存在时创建；修改 `.env` 里的 `ADMIN_PASSWORD` 不会重设数据库中已有账号的密码。

### 服务与持久化

| 服务/数据 | 配置 | 作用 |
| --- | --- | --- |
| `database` | PostgreSQL 16 | 保存账号、账本、业务记录、审计和权限 |
| `backend` | Python 3.12、Uvicorn | 在容器网络内提供端口 8000 的 API |
| `web` | Nginx | 在同一个源下提供静态网页和 API 代理 |
| `postgres-data` 卷 | PostgreSQL 数据目录 | 重建容器后保留数据库 |
| `payment-secrets` 卷 | API 的 `/data/payment-secrets` | 保存由应用接收的商户文件 |
| `recovery-files` 卷 | API 的 `/opt/restaurant-cloud/backups` | 保存应用生成的恢复材料 |

Compose 不把数据库或 API 端口直接发布到主机。网页默认绑定 `127.0.0.1:8080`，适合本机验证或作为主机 HTTPS 反向代理的上游。对外提供服务时，应在域名的 HTTPS 入口代理到这个地址。修改 `WEB_BIND` 会改变访问范围；本文件不包含域名、证书或 DNS 的个人配置。

`TEST_LOGIN_ENABLED=false` 默认关闭 Test 快捷登录。保留这项设置并使用自己创建的账号。当前启动路径不启用旧微信账单调度线程；配置了商户文件也不代表定时导入已经运行。

`docker compose stop` 停止容器，`docker compose up -d` 再启动。普通 `docker compose down` 保留命名卷；带删除卷的选项会删除上述持久化数据，不是日常更新步骤。

### 为什么需要同源代理

网页固定请求 `/api/v1`。`deploy/nginx.conf` 的关键配置是：

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

这里的 `proxy_pass` 末尾没有 `/`，因此请求 `/api/v1/auth/login` 会按原路径交给 API。静态文件来自挂载的 `web/`。只运行静态 HTTP 服务器可以看到页面，但不能完成真实登录和数据操作。

Compose 的完整 Nginx 配置还设置 26 MB 上传上限，并要求浏览器重新验证缓存。`deploy/restaurant-cloud-upload.conf` 是原生部署使用的上传/缓存片段，不是 Compose 的完整 `server` 配置。

## 2. 直接运行原生 Python API

这一方式适合调试，或交给自有的进程管理和 Nginx 配置。需要 Python 3.12、可访问的 PostgreSQL，以及已创建的数据库和角色。正常运行依赖 PostgreSQL `JSONB`；测试中的 SQLite 适配不属于生产部署方案。

例如，在新的 Ubuntu PostgreSQL 实例上，可通过交互提示创建数据库角色，密码不写入 shell 命令：

```bash
sudo -u postgres createuser --login --pwprompt restaurant
sudo -u postgres createdb --owner=restaurant restaurant
```

在仓库根目录创建 Python 环境，再进入后端目录：

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
cp .env.example .env
chmod 600 .env
```

仅对新配置执行上面的复制。编辑 `backend/.env`，填写实际 PostgreSQL 连接串、随机 `SECRET_KEY` 和初始管理员密码，并保留 `TEST_LOGIN_ENABLED=false`。数据库密码包含 URL 保留字符时，需要在连接串中进行百分号编码。为商户文件配置进程可写的 `PAYMENT_SECRET_ROOT`，不要将它放进公开源码目录。

```bash
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

`uvicorn[standard]` 包含读取环境文件所需的 `python-dotenv`。在另一个终端检查：

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/openapi.json
```

配套的主机 Nginx 应将静态根目录指向本仓库的 `web/`，并用 `proxy_pass http://127.0.0.1:8000;` 保留 `/api/` 原路径。生产运行还需要自己建立服务账号、可写目录和进程管理服务。下节的升级脚本只接受已经具备指定路径和 systemd 服务的安装，不负责创建这一环境。

应用启动使用 SQLAlchemy `create_all` 创建缺失表，并补充特定旧版本的时限 JSONB 字段；这不是通用数据库迁移框架。已有列结构变化需要单独设计迁移。启动还会处理初始账号、旧账号绑定和超过 366 天的审计保留策略，不能把程序重启描述成“数据库绝对不会变化”。

## 3. 备份 Compose 实例

Excel 导出不包含完整账号、权限、审计和运行配置。完整恢复至少需要数据库、私有 `.env`、商户文件及应用恢复材料；另保存所用源码提交或发布包。

下面从仓库根目录创建一份单独的本地备份。业务写入应暂停到备份结束，以便数据库与关联文件对应同一操作时段。

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

逐条确认命令成功后，将备份转存到受限的持久存储。备份包含凭据和业务数据，不应进入 Git。`pg_restore --list` 只能检查归档能否被读取；还需在独立数据库中试恢复，并核对登录、账本和库存，才能确认恢复流程可用。

原生安装应使用自己的 PostgreSQL 备份方式，同时保存运行环境和商户目录。下节的升级脚本备份的是 API 与网页程序，不会自动生成数据库 dump。

## 4. 从仓库制作原生服务发布包

先完成 README 列出的网页构建、API 回归和 FIFO 契约检查，再从仓库根目录执行：

```bash
python3 build/make_release.py --output dist/restaurant-cloud-Oct30LingChen-deploy.tar.gz
```

默认输出路径也是上述路径。打包器以排他方式创建压缩包，拒绝覆盖已有文件；需要重新打包时使用新的输出文件名。

包内根目录是 `restaurant-cloud-Oct30LingChen/`，包含：

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

三个脚本均在发布根目录。包外还有同名 `.sha256` 校验文件。打包器从指定源码路径选取运行文件，不打包数据库、`.env`、商户密钥、测试模块或依赖缓存。文件清单用于核对包内容，不表示发布包自带数字签名。

将压缩包和 `.sha256` 文件传到目标主机后，在它们所在目录核对并解压：

```bash
sha256sum -c restaurant-cloud-Oct30LingChen-deploy.tar.gz.sha256
mkdir restaurant-finance-release-check
tar -xzf restaurant-cloud-Oct30LingChen-deploy.tar.gz -C restaurant-finance-release-check
```

macOS 对应的校验命令是 `shasum -a 256 -c ...`。使用新建空目录解压；升级脚本接收的是解压后的发布根目录，不是 Git 仓库目录，也不是 `.tar.gz` 文件。

## 5. 升级已有 Ubuntu 原生安装

`deploy_from_home_ubuntu.sh` 针对以下固定安装约定：

| 项目 | 位置 |
| --- | --- |
| API | `/opt/restaurant-cloud/api` |
| Python | `/opt/restaurant-cloud/.venv/bin/python` |
| 私有运行环境 | `/opt/restaurant-cloud/.env.runtime` |
| 网页 | `/var/www/restaurant-web` |
| Nginx 上传/缓存片段 | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| 已运行的 systemd 服务 | `restaurant-cloud.service` |
| 本次程序备份与默认证据 | `/opt/restaurant-cloud/backups/Oct30LingChen-UTCSTAMP-UNIQUE/` |

该脚本不能用来更新 Compose 容器。API、网页、备份和暂存目录必须位于同一文件系统，以便通过目录重命名切换。现有 API/网页必须是实际目录。现有 requirements 和 Nginx 片段必须与发布包逐字节一致；若不同，脚本会停止，需先单独评审依赖或 Nginx 变更。

脚本依赖现有 Python 环境，包括 `python-dotenv`、SQLAlchemy 和 PostgreSQL 驱动，并要求 systemd、Nginx、`flock`、`curl` 等主机工具已经可用。它不会安装 Python 依赖，也不会修改 Nginx 配置。

确认数据库备份可用，并暂停其他客户端、后台任务和外部数据库写入。后验检查要求受保护的业务记录与前验一致；部署期间的正常业务写入也会使这项检查失败。

```bash
sudo bash /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/deploy_from_home_ubuntu.sh \
  --release-dir /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen \
  --base-url http://127.0.0.1
```

按实际上传位置替换 `/home/ubuntu/...`。默认使用发布包内的两个核验脚本；需要显式指定时使用 `--release-verifier` 和 `--db-verifier`。可通过 `--evidence-dir` 指定新的绝对目录，目录必须尚不存在。默认在本次备份目录下创建 `evidence/`。

升级过程依次执行：

1. 校验版本、HTML 资源引用、依赖、Nginx 和目录条件，获取部署锁。
2. 复制并核对旧程序，构建暂存目录，校验 Python 源码可编译。API 暂存目录在旧 API 副本上覆盖发布文件，网页从发布包重新建立。
3. 停止 API，确认停止成功，生成数据库前验摘要，再切换 API 和网页目录。
4. 启动服务，核对健康版本、磁盘文件、HTTP 静态资源、OpenAPI 路由及数据库后验摘要。
5. 全部通过后，在证据目录写入 `DEPLOYED_VERSION`。程序备份和证据继续保留。

失败时脚本尝试恢复原 API/网页目录并重新检查服务健康。自动回退不恢复数据库；若回退失败，会明确输出错误并保留原始目录供处理。程序回退和数据库恢复是两个不同操作。

脚本不删除旧备份。清理旧版本应在核验和恢复准备完成后单独进行；本次证据目录与数据库恢复材料不能混作普通临时文件删除。

## 6. 独立执行核验

升级脚本已经调用这些检查。排查已有安装或保留额外证据时，也可以单独运行。下面命令针对上一节的原生路径。

### 发布文件与 HTTP

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

`--evidence-dir` 必填。为每次独立检查选择新的私有目录；结果写入 `release-check.json`。检查内容包括发布包对应的 Python/网页文件哈希、requirements、Nginx 片段、网页引用的资源、缓存版本、健康接口和品名更正 API 路由。

`--base-url` 是网页入口，`--api-base-url` 是可直接访问 `/openapi.json` 的 API 地址。Compose Nginx 没有转发 `/openapi.json`，不能把网页地址直接当作这个参数使用。现有升级包装脚本使用 API 默认地址 `127.0.0.1:8000`。

### PostgreSQL 升级前后证据

在升级前停止业务写入并执行 `before`，升级后保持写入暂停并执行 `after`。两次使用同一证据目录：

```bash
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/verify_deployment.py before \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001

# 完成程序更新后再执行：
sudo /opt/restaurant-cloud/.venv/bin/python /home/ubuntu/restaurant-finance-release-check/restaurant-cloud-Oct30LingChen/verify_deployment.py after \
  --env-file /opt/restaurant-cloud/.env.runtime \
  --app-dir /opt/restaurant-cloud/api \
  --evidence-dir /opt/restaurant-cloud/backups/manual-db-check-001
```

该工具要求 PostgreSQL，并在 `REPEATABLE READ`、`READ ONLY` 事务中读取当前数据。它只导入配置和数据库模块，不执行应用启动。业务 JSONB 使用 PostgreSQL 原始文本生成摘要，避免通过 Python 浮点值重新序列化。输出保留记录数量、表摘要、环境文件摘要和检查结果，不打印账本 payload、密码哈希或环境值。

`before` 拒绝覆盖已有基线；`after` 缺少基线时失败。它比较业务记录、时限、品名更正回执、账号、账本、绑定关系和临时权限等指定数据，另外检查审计减少数量是否落在旧基线中超过 366 天的记录数量范围内。这不是全数据库逐字节比较，也不能证明每条被清理的审计记录的身份。

工具假定目标已具备当前验证查询需要的表结构，不负责迁移旧数据库。应用启动可能补充结构或清理过期审计；若受保护表发生变化，应查看具体证据并判断原因，不应为通过检查而忽略差异。

## 7. 上线后的实际检查

文件核验和数据库摘要通过之后，还需要用具备相应权限的账号检查实际流程：登录与账本切换、手机/平板/电脑布局、所选月份的人工支出筛选、库存批次与 FIFO 成本、Excel 导入导出和权限限制。写入测试应使用专门测试账本或独立实例。

健康接口证明 API 能响应，文件哈希证明部署内容与发布目录一致，数据库摘要检查指定业务数据是否保留；它们均不能替代完整的交互验收或数据库恢复演练。
