# 餐饮财务与库存管理系统

### **README、更新日志、部署指南和工程技术参考 (Engineering reference) 均以英文撰写，并译为中文。中英文表述如有出入，以英文版为准。**<br>**The README, CHANGELOG, Deployment Guide, and Engineering Reference are written in English and translated into Chinese. If the wording differs, the English edition takes precedence.**

### [English](README.en.md) · [更新日志](<CHANGELOG (中文).md>) · [部署指南](docs/DEPLOYMENT.zh-CN.md) · [工程技术参考 (Engineering reference)](docs/ENGINEERING_REFERENCE.zh-CN.md)

本系统用于餐饮门店的日常记账、经营核算和库存管理。同一本账可以按门店和渠道记录营业收入，汇总食材采购与领用情况，并按月登记房租、工资等费用。经营者可以查看本月截至目前的实际净利润，查阅各项费用的明细，也可以根据已有收支估算月底盈亏。

网页版支持电脑、平板和手机浏览器。在不同设备上打开同一网址，登录后即可使用分配给该账号的账本。网页界面可切换中英文，店名、菜品名和备注始终保留录入时的原文。macOS 桌面版使用中文，也支持在本地使用 Excel 账本，并与服务器同步。

## 手机版与平板版网页

本页截图均使用网页版英文界面，图中账本和交易均为示例。

**手机。** 账本选择器位于页面顶部，点「菜单」即可展开导航。记账表单按屏幕宽度纵向排列。在仪表盘上，轻点图表的数据点可以查看日期和数值，点预计月底盈亏旁的 **ⓘ** 可以查阅计算依据。

<img src="docs/images/web-phone-en.png" alt="手机浏览器中的英文经营仪表盘，顶部可切换账本" width="340">

**平板。** 竖屏时使用折叠菜单，较宽的屏幕可容纳更多表单字段和报表内容。在「更多统计」中选定月份，即可查看经营、费用或客流统计，轻点图表便能读取数据。在宽屏电脑上打开这些页面，左侧导航栏会常驻显示。

<img src="docs/images/web-tablet-en.png" alt="平板竖屏浏览器中的英文统计页面，支持触控操作" width="680">

## 记账与库存管理

**门店与账本。** 两个档口共用厨房时，可以使用同一本账。在「店铺设置」中分别填写档口名称，就能分开登记各自的现金、微信支付、支付宝和外卖收入。共用的采购支出、房租和工资在这本账中记一次即可。如果两个档口需要独立管理库存、核算费用和编制报表，可以分别建立账本。

**日常记账。** 选定营业日期后，可分别登记各档口的现金、线上收款和外卖收入。记账表会汇总各渠道收入，手续费单独列示。同一天的客人数、备注、食材和佐料采购也记在这张表里。采购明细可填写数量、单位和单价，事后可以按笔核对总额。工资、房租等月度固定成本按所属月份保存。

![电脑浏览器中的英文记账页，可查看营业日期、收入合计和各收款渠道](docs/images/web-ledger-en.png)

**现金对账。** 现金余额表面向管理员和具有长期修改权限的账号。已登记的营业收入和经营支出会反映在余额中，股东借款单独记录。如果盘点金额与账面余额有差异，在「新增现金项目 → 余额强制修改」中填入指定日期的实盘金额即可。这笔调整会列入现金流水，不计入经营利润。切换到英文界面后，部分自动生成的摘要（如「当日收入」）仍显示中文。

![英文现金余额表，展示可用余额和按日期排列的流水](docs/images/web-cash-en.png)

**库存与领用成本。** 假设大米期初库存为零。在日账的食材采购中登记大米 10 公斤、总价 80 元，系统会记入这笔采购支出，并自动生成入库记录。厨房领用 2 公斤后，库存结余 8 公斤，本次领用成本为 16 元。各批次进价不同时，系统按先进先出（FIFO）计价，从最早入库且仍有余量的批次开始扣减。库存记录还列出损耗、盘点调整和进价未知的数量。核算月度利润时扣除采购支出，厨房领用和菜品耗用成本可单独查看，同一笔采购不会重复扣减。

在库存结存页面，可以查询某种食材的现存数量，并追溯对应的入库和出库记录。实盘数量与账面数量有差异时，通过盘点登记差额。每种物料可以单独设置低库存预警值。价格未知的库存另行标示，便于与已按零成本入账的库存区分。

![英文库存管理页面，展示各物料的结存数量和库存操作入口](docs/images/web-inventory-en.png)

**账号权限与临时授权。** 管理员为员工账号分配账本。只读账号可查阅获准访问的账本，录入账号可填报日常收支并在规定时间内更正，有修改权限的账号可修改已有记录。超过更正时限后，管理员可按账本和营业日期临时授权。例如，可以允许店员在今天下午三点前修改指定账本中昨天的记录，到时授权自动失效。

**经营报表与来源明细。** 经营统计列出已记账的营业日中有多少天盈利，费用统计显示主要支出类别。核对固定费用时，可以比较月度汇总与逐笔付款，两种金额分别列示，便于查找差额。客流统计列出客人数最多的营业日。明细表支持筛选和排序，合计金额和 CSV 导出均包含所有符合条件的记录，涵盖全部分页。

**Excel 账本。** 员工可按年份下载有权访问的业务账本。管理员可将导入的工作簿与所选账本合并，也可用它替换该账本的数据。内部工作簿则保留程序使用的结构化记录。备份整台服务所需的数据库和运行配置，见[部署指南](docs/DEPLOYMENT.zh-CN.md)。

## 经营仪表盘

主页五项指标依次为日均收入、日均毛利润（毛利率）、预计月底盈亏、预计本月每日盈亏、实际净利润（净利率）。查看本月时，前两项按截至昨天的数据计算。实际净利润包含今天已录入的收支和已保存的整月固定成本。

![十一月示例账本的五项经营指标](docs/images/dashboard-kpis-en.png)

图中示例账本的十一月预计月底盈利为 **62,475.33 元**，按全月 30 个自然日计算，预计每日盈利 **2,082.51 元**，比十月实际日均盈利低 9.1%。毛利润为营业收入减去食材、佐料和手续费后的金额。计算净利润时，还需扣除日常水电等其他支出和当月固定成本。

<details>
<summary>预计月底盈亏的计算方法</summary>

本月预计收入等于截至昨天的日均收入乘以本月自然天数。预计收入扣除三项预计成本后，即为预计月底盈亏。固定成本取本月与上月已记录的整月金额中的较高值。食材成本（含佐料）和其他成本分别比较两个月的日均金额，各取较高值，再乘以本月天数。今天新增一笔采购就可能影响预测。次月 1 日起，仪表盘显示已结束月份的实际净利润。

点开预测值旁的 **ⓘ**，可以查看两个月各项成本的金额和计算时采用的数值。下图中，固定成本取自十月，日均食材成本和日均其他成本取自十一月。末尾三行依次列出十一月预计日均总成本、预计总成本和预计收入。

<img src="docs/images/forecast-inputs-en.png" alt="十月与十一月的成本，以及十一月预测采用的数值" width="400">

</details>

<details>
<summary>每日趋势、各星期平均与开销构成</summary>

**每日趋势与各星期平均。** 「本月趋势」逐日展示数据。「各星期平均」把所选月份有记录的日期按星期几分组，再算出各组平均值。两张图默认显示收入，也可以分别切换为毛利润、净利润或食材成本（含佐料）。

![十月每日营业收入，图中选中了一天](docs/images/daily-revenue-en.png)

![各星期平均营业收入，图中选中了周六](docs/images/weekday-revenue-en.png)

**每日开销构成。** 选择日期后，圆环中心显示当天的总成本，图例列出各类费用的金额和占比。

<img src="docs/images/cost-ring-en.png" alt="手机端每日开销构成，环心显示当天总成本" width="390">

</details>

## 本地安装

首次从源码运行时，使用 Docker Compose v2 一起启动 PostgreSQL、API 和网页服务器。在仓库根目录复制配置模板。

```bash
cp .env.example .env
chmod 600 .env
```

打开 `.env`，分别为 `POSTGRES_PASSWORD`、`SECRET_KEY` 和 `ADMIN_PASSWORD` 设置不同的值。可为每一项单独运行一次 `openssl rand -hex 32`，也可用[部署指南](docs/DEPLOYMENT.zh-CN.md)中的脚本生成配置。然后启动服务并检查 API。

```bash
docker compose config --quiet
docker compose up --build -d
curl --fail --retry 12 --retry-connrefused --retry-delay 2 http://127.0.0.1:8080/api/v1/health
```

打开 <http://127.0.0.1:8080>，使用 `.env` 中配置的管理员账号登录，默认用户名为 `admin`。在「Excel 账本」中新建账本，再到「用户管理」中为员工分配账本。默认配置只允许本机访问。配置中的初始密码在首次创建管理员账号时生效。

服务器安装、数据库备份及已有 Ubuntu 服务的升级步骤见[部署指南](docs/DEPLOYMENT.zh-CN.md)。

## 源码与开发

| 模块 | 源码位置与构建方法 |
| --- | --- |
| 网页界面 | 页面、样式表和语言文件位于 `web/`。业务计算源码位于 `build/web-exact-source/`。修改后运行 `node build/compile_exact_web.cjs`，重新生成浏览器加载的脚本。 |
| API 与数据库 | `backend/app/` 包含 FastAPI 路由、SQLAlchemy 数据模型、权限校验、金额计算及 Excel 导入导出代码。测试位于 `backend/tests/`。生产数据存储在 PostgreSQL 中，修改已有字段需要执行数据库迁移。 |
| macOS 桌面版 | PySide6 程序入口是 `desktop/restaurant_cost_manager.py`。安装 `desktop/requirements.txt` 所列依赖后，在图形界面环境中运行 `python desktop/restaurant_cost_manager.py`。 |
| 安装与升级 | `compose.yaml` 用于启动新实例。`deploy/` 下的脚本用于升级和核验已有的原生 Ubuntu 服务。`build/make_release.py` 用于生成服务器部署包。 |

网页使用基于 `BigInt` 的十进制运算处理金额，Python 端使用 `Decimal`。财务公式、库存计价规则、数据库表、API 路由及测试方法见[工程技术参考](docs/ENGINEERING_REFERENCE.zh-CN.md)。

### 运行测试

测试需要 Python 3.12、Node.js 和 npm。在仓库根目录运行以下命令，创建测试环境，按锁文件安装编译依赖，并运行网页和 API 测试。API 测试会创建独立的测试数据库，并使用测试配置。

```bash
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

在受支持的 macOS 或 Unix 环境中，可以运行 FIFO 测试，核对桌面版与网页的计算结果。测试使用 Qt 离屏模式，并通过 `PATH` 或 `NODE_BINARY` 指定的路径查找 `node`。桌面版源码使用 Unix 模块 `fcntl`。

```bash
python -m pip install -r desktop/requirements.txt
python build/test_fifo_contract.py
```

### 服务器部署包

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
```

部署包的根目录为 `restaurant-cloud-v1.0.2/`，内含 API、网页文件、Nginx 配置和部署工具。每次构建请使用新的输出文件名。生产凭据和数据库备份应单独保存。升级后，`deploy/verify_release_files.py` 用于核对已安装的文件和 HTTP 接口，`deploy/verify_deployment.py` 用于比较升级前后的数据库记录。具体步骤见[部署指南](docs/DEPLOYMENT.zh-CN.md)。

## 版本与许可证

**v1.0.2** · 网页构建号 `20261112-daily-pl`。早期源码见 [V1.0.1](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/tree/old/V1.0.1) 和 [V1.0.0](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/tree/old/v1.0.0)。V1.0.0 源码中的初始构建标识为 `Oct30LingChen`。各版本改动见[更新日志](<CHANGELOG (中文).md>)。

本项目采用 [MIT 许可证](LICENSE)。
