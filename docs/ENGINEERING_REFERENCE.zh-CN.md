# 工程技术参考 · v1.0.2

**[← 返回中文 README](../README.md)** · [English](ENGINEERING_REFERENCE.md) · [更新日志](<../CHANGELOG (中文).md>) · [部署指南](DEPLOYMENT.zh-CN.md)

修改功能或追查界面上某个金额时，可以按下表找到相关代码和计算规则。安装步骤请看上方的部署指南。

| 想做什么 | 从哪里开始 |
| --- | --- |
| 找到某个页面的代码，或追踪一次保存 | [源码索引](#source-map) · [数据库记录](#database) · [保存流程与权限](#saving) |
| 核对金额或修改图表 | [利润与库存](#calculations) · [预计月底盈亏](#预计月底盈亏) · [图表与导出](#charts) |
| 翻译表单或错误提示 | [界面语言](#languages) |
| 运行测试、构建发布包或恢复服务 | [配置](#settings) · [测试与构建](#tests) · [打包与恢复](#recovery) |
| 排查故障或查找接口 | [故障排查](#troubleshooting) · [HTTP 接口](#api-routes) · [隐私检查](#privacy) |

## 系统由哪些部分组成

一个**账本**保存一套经营记录。同一账本可以分别记录 A 店和 B 店各渠道的收入。界面上的门店名称用来辨认收入来源。服务器根据账本 ID 查找记录，并检查当前账号是否有权修改。

浏览器加载静态 HTML、JavaScript 和 CSS。FastAPI 服务负责验证账号，并将账本保存到 PostgreSQL。macOS 客户端使用 PySide6，既能读写本地 Excel 工作簿，也能与服务器同步。仓库提供这三部分的源码和测试，服务器部署包与 macOS 应用分别构建。

| 想确认什么 | 查哪里 |
| --- | --- |
| 软件版本 | `VERSION` 文件和 API 健康检查都会返回 `v1.0.2`。同一版本可以先后有多次构建。 |
| 这次构建用了哪份代码 | Git 提交标识已纳入版本管理的源码。HTML 里的构建号可区分同一版本下的不同前端构建。 |
| 服务器实际提供了哪些文件 | 用服务器部署包中 `MANIFEST.json` 记录的 SHA-256 值，核对已安装的文件和通过 HTTP 取得的文件。 |
| 完整 ZIP 里有什么 | 外层 `.sha256` 校验整个 ZIP。`PACKAGE_MANIFEST.json` 记录包内文件、权限和符号链接。 |
| 升级后账本是否完整 | 对比升级前后的数据库核查结果。要验证备份能否恢复，在隔离环境中用该备份及配套配置实际恢复一次。 |

经营报表采用下文列出的门店核算口径。补录或更正可以改变已结束月份的数字。核实收款要查支付记录，编制法定报表应以适用的会计记录为准。

<a id="source-map"></a>

## 按功能查找源码

从 `web/index.html` 查看脚本加载顺序。各面板共用 `state`，后加载的模块有时会扩展或替换先前定义的函数。排查仪表盘问题时，沿着工作台、图表、仪表盘和统计模块往下找，确认浏览器最终调用了哪个函数。精确金额运算库要先于业务脚本加载。

| 源码位置 | 负责的功能 |
| --- | --- |
| `web/index.html` | 基础 DOM、脚本依赖的 ID、资源载入顺序、修订号与缓存查询参数。改 ID 前查全部调用。 |
| `web/money.js` | BigInt 精确十进制运行库，直接维护，无另一份编译输入。 |
| `build/web-exact-source/app.js` | 共享状态、权限、记录规范化、API 操作、编辑基线、报表、日期逻辑与切语言。 |
| `build/web-exact-source/pro.js` | 加强版流水/采购/菜品编辑器、明细解析、报告及早期统计入口。 |
| `web/i18n-en.js`、`i18n-inventory-en.js`、`i18n-backend-en.js`、`i18n-extra-en.js` | 四组英文显示字典，先于 v8 载入；UI、库存、API 错误/审计及旧模板分别覆盖。必须保护用户原文。 |
| `web/i18n-controls.js` | 英文月份输入显示适配：ISO `YYYY-MM` 覆盖层，保留原生输入、值、验证、事件和日历选择；四字典之后、v8 之前载入。 |
| `build/web-exact-source/v8.js`、`v28.js` | 选择器、后续工作流及设置；切账本时的请求上下文保护不能移除。 |
| `build/web-exact-source/sep04.js` | 现金余额视图、缓存同步、加项操作和旧格式兼容。 |
| `build/web-exact-source/sep05.js`、`sep07.js` | 报表、编辑器、权限和客人数等后续集成；保留实际生效封装。 |
| `build/web-exact-source/inventory-fifo.js` | FIFO 重放、批次分摊及金额守恒。 |
| `build/web-exact-source/oct29.js` | 扩展流水/库存/工作流以及对应回归。 |
| `build/web-exact-source/inventory-workspace.js` | 库存工作区、单据、来源明细和品名更正界面。 |
| `web/workbench.js`、`web/workbench.css` | 应用外壳、导航、页面标题和响应式布局，直接维护。 |
| `build/web-exact-source/charts-oct30.js` | 共用 SVG 几何、坐标、悬停/触摸/焦点/键盘查看及缩放生命周期。 |
| `build/web-exact-source/dashboard-oct30.js` | 主页五项指标、比较文案和图表入口。 |
| `build/web-exact-source/analytics-oct30.js`、`web/analytics-oct30.css` | 统计筛选、经营/费用/客流视图、费用计算、来源明细表及页面布局。 |
| `desktop/restaurant_cost_manager.py` | 原生控件、本地与云端数据、财务和同步；大型单文件，应按符号/类定位，不依赖旧行号。 |
| `backend/app/main.py` | API 路由、记录策略、权限、现金汇总、启动兼容和审计维护。 |
| `backend/app/models.py`、`database.py`、`security.py` | 表结构、精确 JSON 保存、会话、JWT 和密码。 |
| `backend/app/money.py`、`money_routes.py`、`excel_io.py` | 金额输入/序列化、HTTP 原始 JSON 精确解析和工作簿边界。 |
| `backend/app/inventory_balance.py`、`inventory_validation.py` | 数量重放、事务时库存/单据金额检查；不是第三套 FIFO 成本引擎。 |
| `backend/app/name_corrections.py`、`ingredient_corrections.py` | 更名预览、关联改写、盘点调整、过期状态校验及持久幂等回执。 |
| `backend/app/store_settings.py`、`wechat_pay.py`、`wechat_sync.py` | 店铺配置和保留的微信账单代码；当前启动不会开启旧自动同步。 |

网页业务源码位于 `build/web-exact-source/`。`node build/compile_exact_web.cjs` 用 Acorn 解析后生成对应 `web/*.js`，不能只改生成文件。HTML、CSS、`money.js`、`workbench.js`、本地化资源及许可证直接维护。新增文件先看编译器清单，确认是否应编译。浏览器运行不需要 Node、Acorn、打包器或 CDN。

<a id="database"></a>

## 一个账本怎样存入数据库

生产环境使用 PostgreSQL，字段不固定的业务记录保存在 JSONB 列中。启动时会调用 SQLAlchemy 的 `create_all`，并执行代码中列明的几项兼容性更新。修改数据库结构时，要另行安排迁移。测试也会用到 SQLite 适配器。

| 数据表 | 保存什么 | 修改时要注意什么 |
| --- | --- | --- |
| `app_users` | UUID、唯一用户名、显示名、bcrypt 密码哈希、角色、启用状态。 | 更改启动环境密码不会重设已存在管理员密码。 |
| `datasets` | 稳定账本 ID、名称、schema_version。 | 重命名仅改显示名；ID 决定记录和权限范围。 |
| `user_dataset_memberships` | 用户/账本唯一组合与默认账本标志。 | 非管理员须有成员关系，选中 UI 不等于授权。 |
| `devices` | 所属账本、设备 ID、名称/平台、上次活动。 | 注册和缓存使用请求开始时捕获的账本。 |
| `sync_records` | 唯一 `(dataset_id, record_type, record_key)`，payload、校验和、版本、序号、删除状态。 | 保留 expected-version 和删除墓碑；商品同名不是单据身份。 |
| `entry_timings` | 服务端首次保存时间、字段/明细时钟和旧兼容时钟。 | 改 payload 不能延长更正或新增窗口。 |
| `audit_logs` | 前后内容、操作者、来源/事件/设备、版本变化、序号和时间。 | 有保留期和管理员删除，不能代替不可变备份。 |
| `temporary_permissions` | 用户/账本、角色、业务日期范围、生效时间段。 | 同时校验业务日期与真实生效时间。 |
| `sync_conflicts` | 本地/云端版本与内容、状态、解决方式和说明。 | 解决冲突不能绕过普通写入的金额和权限规则。 |
| `inventory_name_corrections` | 账本/request ID 唯一、请求哈希、请求与响应内容、原因。 | 回执独立于审计清理；相同 ID 携带不同请求无效。 |

日记录可能包含 `daily`、`dishes`、`fixed_expenses`；月记录包含 `monthly_fixed`；global 记录按既有 key 保存设置、字典、现金及库存相关资料。历史 payload 可能一次包含多天，修改一天须按日期合并各数组，并保留不能明确归属的无日期旧行。某天没有菜品时，不能回退显示另一日最后一行。

ID、日期、版本、记录键、名字、备注和扩展元数据不是金额。导入与编辑保留未知字段。名称相同但单位、价格或备注不同的采购仍是不同明细；移动/删除选中行必须按行身份，不按名称整批选取。

内部数据 Excel 有 `__day_records`、`__month_records`、`__global_records`、`__meta`、`__audit_records` 等记录表，含结构化 `payload_json`。它是交换格式，不包含完整服务器的账户、成员关系、时钟、商户密钥、环境和服务配置。用户工作簿面向业务；合并与替换必须明确分开。

<a id="saving"></a>

## 从编辑器保存到数据库

浏览器向提供网页的同一站点发送 `/api/v1` 请求。Nginx 转发请求时保留 `/api/` 前缀。登录成功后，客户端获得 JWT 并以 Bearer 方式随请求发送。服务器会重新读取账号，检查它是否仍然启用。角色分为 `viewer`（只读）、`entry`（录入）、`editor`（编辑）和 `admin`（管理员）。管理员可以跨账本操作，其他用户需要先被分配到相应账本。

1. 编辑器记下当前登录状态、账本和本次界面的标识，保留编辑前的记录以及此次没改动的字段。
2. 客户端为该账本注册或复用设备，按规定格式整理金额字段、计算校验和，并把编辑前的记录版本号随请求一起发出。
3. 在同一事务中，服务器检查权限、修改时限、记录版本，以及这次操作涉及的库存规则。保存时一并写入新版本号、同步序号和审计记录。
4. 响应返回时，客户端会检查用户是否仍在原来的编辑环境中。从 A 账本切到 B 再切回 A，第一次打开 A 时发出的请求已经过期。新的本地保存也会推进版本，较早发出的刷新不能覆盖它。

**现金余额。** 调整现金余额可能不会改变日账。每次收到现金接口的响应，都要核对账本和现金数据的版本。即使日账快照没有变化，也要处理新的现金余额。所有现金视图共用同一份缓存。

**录入权限。** 服务器按字段或明细行记录首次保存时间。主要的更正时限为 30 分钟，追加明细的时限为 12 小时，还要检查业务日期和收入录入的截止时间。临时授权可在生效期间为指定业务日期的日记录提高操作权限。修改规则前先看 `_effective_record_role` 和 `_entry_timing_updates`。修改备注或用等值金额重新保存时，计时起点保持不变。

**库存变动。** 服务器先锁定账本，按顺序重算库存流水，检查本次修改是否造成新的库存不足，同时拒绝过期版本的单据。更正品名时先预览受影响的记录，再复核并在同一事务中更新。成功后保存的请求回执用于识别重复提交。

**审计记录。** 服务器保留 366 天的记录，并提供管理员维护接口。启动时可以清理过期记录，对比升级前后的数据库时应考虑这项变化。

<a id="calculations"></a>

## 利润和库存怎样计算

金额格式和测试用例见[客户端金额规范](../build/MONEY_CONTRACT.txt)、[先进先出规则](../build/FIFO_CONTRACT.md)及 [API 金额规范](../backend/MONEY_BACKEND.txt)。API 用十进制字符串传递新增或修改的金额。Python 使用 `Decimal`，浏览器使用 `Exact`。金额保留两位小数，单价保留六位，按 `ROUND_HALF_UP` 舍入。单笔金额的绝对值上限为 999999999999.99，单价的绝对值上限为 999999999999.999999。多笔合法输入产生的合计值另有规则。无效文本、布尔值、NaN 和无穷大均应拒绝。明确录入的零单价属于已知价格。

旧 numeric JSON 读取保留原十进制词法；需要时从 OOXML 原始数值读取。只规范已知财务路径，不能递归把任意 metadata 都转金额。绘图坐标可以在最终边界转 float，不能用于财务持久化。Exact 的格式化不能在中间运算中暗中调用 Number。

主页五项依次为日均收入、日均毛利润（毛利率）、预计月底盈亏、预计 本月每日盈亏、净利润（净利率）。前两项算到昨天，分母是截至昨天已过的自然天数。第四张卡显示每天的盈亏金额，下方百分比是与上月每日盈亏的环比。第五张卡包含今天已录的收支和整月已保存的固定支出。其净利率用实际月净利润除以含今天的本月实际收入，收入缺失或为零时不可用。完整月报里的实际日均净利润用实际净利润除以已过自然天数。

“本月趋势”和“各星期平均”打开时都显示收入，各自有独立的指标选择。收入、毛利润、净利润沿用日账指标；食材成本是食材与佐料采购支出之和。趋势图保留未录日期的空缺。星期均值按所选月、星期几分组，分母是各星期实际有记录的日期数。有经营记录的日期即使该指标为零也参与平均；没有业务内容的空行不参与，整组没有记录时留空。这个分母和预测用的自然天数各有用途。

主页“开销构成”展示所选日各项支出。类别颜色固定，其他类别是否出现都不会使颜色错位。图例以同色标记列出类别、金额和占比。圆心金额为该日图中各项支出之和。实际日图只绘制正数支出，日固定费用按现有分摊口径取值。原生端月度支出图按既有类别绘制整月固定费用，手续费不在该月图内。核对圆心时，应当将同一张图的扇区相加。月底预测从账本重新计算整月金额。

日环图以 `dayMetrics` 中的成本类别键为依据。配色表 `costDonutColors` 和绘制函数 `renderCostDonut` 在 `build/web-exact-source/app.js` 内，环形色块和图例从同一张表取色。修改后用 `build/compile_exact_web.cjs` 重新生成网页文件。窄屏布局及圆心内名称、金额和单位的居中样式在 `web/reporting-oct30.css`，原生程序对应 `DashboardTab._draw_cost_ring`。

### 预计月底盈亏

主页与完整月报使用同一结果。中文标题第一行是 `预计月底盈亏`，第二行是 `(根据 本月预计成本 和 本月预计收入 计算)`。英文两行分别是 **Estimated month-end profit/loss** 和 **(based on this month’s projected costs and revenue)**。悬停或点击旁边的 **i**，可查看计算方式、取数截至哪一天，以及跨月后怎样显示。网页版说明跟随界面语言，“更多统计”的高级视图也复用这份说明。同步替换按钮时，已经打开的说明会关联到新按钮并刷新金额。原生客户端以中文说明同一规则。

以下各项均取自同一账本。用 **D** 表示本月自然天数。上月日均值的分母是上月全部自然天数，1 月的上月是上一年的 12 月。本月日均收入的分子只含截至昨天的收入。日均食材、日均其他成本的分子计入截至今天已保存的费用，未来日期的记录尚不参与。本月三项日均均除以截至昨天已过的自然天数，没有录入的自然日也计入分母。

| 项目 | 计算方式 |
| --- | --- |
| 本月预计收入 | 本月截至昨天的日均收入 × D。 |
| 预计固定成本 | 比较上月和本月已保存的整月固定支出，取较高金额。固定支出中的水电煤气按实付金额计算。 |
| 预计食材成本 | 各期间分别将食材和佐料采购成本相加，比较两个月的日均值，取较高值 × D。 |
| 预计其他成本 | 各期间分别用总成本减去食材成本（含佐料）和整月固定支出，剩余为日结水电、手续费及其他费用。比较两个月的日均其他成本，取较高值 × D。 |
| 预计月底盈亏 | 本月预计收入 − 预计固定成本 − 预计食材成本 − 预计其他成本。 |
| 预计 本月每日盈亏 | (预计月底盈亏 ➗ 本月天数)。用尚未舍入的月底盈亏除以 D。已结月用实际净利润除以该月自然天数。月度盈亏缺失时显示破折号。 |

**算例：11 月 11 日记了一笔采购。** 本月已过 10 天，10 月有 31 天，11 月有 30 天。假设账本里有以下金额，单位为元。

| 项目 | 10 月 | 11 月已记 | 11 月预计 |
| --- | ---: | ---: | ---: |
| 固定成本 | 6,000 | 6,500 | 6,500 |
| 食材及佐料 | 9,300（日均 300） | 2,600（日均 260） | 9,000 |
| 其他成本 | 1,550（日均 50） | 750（日均 75） | 2,250 |
| 截至昨天的收入 | — | 8,000（日均 800） | 24,000 |

说明中显示预计日均总成本 **591.67 元**、预计总成本 **17,750.00 元**、预计收入 **24,000.00 元**。预计月底盈利 **6,250 元**。现在保存一笔日期为 11 月 11 日、金额 600 元的买菜支出，11 月日均食材成本变为 3,200 ÷ 10 = 320 元，高于 10 月的 300 元。预计食材成本随之升至 9,600 元，预计盈利降至 **5,650 元**。如果 11 月 11 日记的是营业收入，则到 11 月 12 日才会计入预计收入。

具体计算时，两个月的日均值先通分。用 **e** 表示本月截至昨天已过的天数，**p** 表示上月天数，公分母就是 `e × p`。食材和其他成本各自比较两个分子 `本月累计成本 × p` 和 `上月累计成本 × e`，取较高者。本月截至昨天的累计收入乘 p，扣除这两项选中的分子，再乘 D，减去 `预计固定支出 × e × p`。将所得分子统一除以 `e × p`，最后将预计盈亏显示到分。这样即使某项日均值是循环小数，恰好半分的净额仍能正确舍入。预测中的“其他成本”包含手续费、日结水电和记账分类中的“其他费用”。本月尚未保存固定支出时，直接用上月固定支出。本月明确保存为零时，零会参与比较。上月明确记为零，或仅有已保存的月固定支出记录，都能作为比较依据。每月 1 日、本月截至昨天还没有经营记录、上月完全没有成本依据，以及所选月份在未来时，无法计算预测。

说明里的日均总成本含固定支出。设核算盈亏时尚未舍入的预计总成本分子为 N。月总成本为 `N ÷ (e × p)`，日均总成本为 `N ÷ (e × p × D)`。两项分别格式化到分。月结后，三行改为实际日均总成本、实际总成本和实际收入，日均用全月实际总成本除以该月自然天数。缺少计算依据的金额显示破折号。

第四张卡沿用第三张卡的盈亏分子，一次除以 `e × p × D`，显示时才舍入到分。上文十一月的采购保存前为 6,250 ÷ 30 = **208.33 元/天**，保存后为 5,650 ÷ 30 = **188.33 元/天**。若某次十一月预计月底盈亏恰为 0.145 元，第三张卡显示 0.15 元，第四张卡按 0.145 ÷ 30 计算，显示 **0.00 元/天**。

要复现跨月环比，可在空测试账本中为 2024 年 1 月 1 日录入收入 310 元，为 2 月 1 日录入收入 580 元，各项成本均为零。月结后查看 2 月，第三张卡显示 580.00 元。第四张卡将 2 月的 580 ÷ 29 = **20.00 元/天** 与 1 月的 310 ÷ 31 = **10.00 元/天** 比较，环比增加 **100.0%**。第五张卡显示实际净利润 580.00 元，净利率 100.0%。改用平年 2023 年、2 月收入 560 元，2 月分母为 28 天。

环比对两个月尚未舍入的每日盈亏通分后再比较。例如十一月净额为 0.03 元、十月净额为 2.00 元，两个月的每日盈亏分别按 0.03 ÷ 30 和 2.00 ÷ 31 计，降幅恰为 98.45%，显示为 **98.5%**。

**修改计算逻辑时从哪里入手。** 在 `build/web-exact-source/app.js` 中，`monthOverviewMetricsV102` 汇总账目，`monthForecastV102` 每次刷新时据此计算预测，返回 `net`、`dailyNet`、`netNumerator` 和 `dailyNetDenominator`。`dashboard-oct30.js` 的 `summary` 将两个月各自的分子与除数交给 `monthChangeV102` 计算环比。主页和月报使用同一份预测。说明区按未舍入的值比较，列出两个月的候选金额，并标明取自哪一月或两月持平。固定成本按整月金额比较，食材和其他成本按日均金额比较。

桌面端对应 `desktop/restaurant_cost_manager.py` 中的 `calc_dashboard_month_kpis`，返回的 `projected_daily_net` 由 `DashboardTab._refresh_month_headlines` 显示。运行 `node web/test_v1_0_2_dashboard.js` 核对二月算例和舍入边界，运行 `python build/test_v1_0_2_desktop.py` 核对桌面计算，用 `QT_QPA_PLATFORM=offscreen python build/test_v1_0_2_desktop_qt.py` 检查实际界面的卡片顺序、金额和利润率。测试账本可以让食材成本取上月、其他成本取本月，以确认两项分别比较。加入一笔当天的采购和一笔佐料，能一并检查日期截止及重复计入问题。

客户端本地日历决定月份是否结束，与选中的日无关。网页和原生日期监测约每五秒检查，即使数据未变也重算；网页恢复可见时也检查，原生等弹窗关闭后刷新并在读取失败后重试。下个月 1 日起，上月预测卡显示实际净利，包含十二月跨年情况。这个切换不改变选中期间、不写入或冻结月结；合法历史更正会重新计算。

| 客户端日期 | 所选月份 | 预测卡金额 |
| --- | --- | --- |
| 10 月 31 日 | 10 月 | 当月预测。 |
| 11 月 1 日 | 10 月 | 10 月实际净利，不再需要上月成本。 |
| 11 月 1 日 | 11 月 | 已过一天前不可预测，实际净利可单独存在。 |
| 1 月 1 日 | 上年 12 月 | 12 月实际净利。 |
| 11 月 10 日 | 12 月 | 未来期间，不可用。 |

| 项目 | 必须保持的含义 |
| --- | --- |
| 收入 | 规范渠道记录和 `收益` / `总金额` 等历史总额字段；有效渠道值优先于过期派生总额，不能两者相加。 |
| 毛利润 | 收入 − 食材 − 佐料 − 手续费。 |
| 毛利率 | 日均毛利 ÷ 同口径日均收入；分母缺失或为零时不可用。 |
| 变动成本 | 食材 + 佐料 + 日结水电 + 其他 + 手续费。 |
| 月固定支出 | 已保存人工 + 房租/物业 + 实付水/电/煤气 + 其他固定。 |
| 月总成本 | 日变动成本合计 + 整月已保存固定支出。 |
| 月净利润 | 收入 − 月总成本。 |
| 环比 | `(本期 − 上期) / abs(上期) × 100`；上期零或缺失须说明。 |
| 余额强制修改 | 某日实际余额设定，不是营业收入/支出。 |
| 固定费用比较 | 月保存汇总与逐笔日期支出为两种核对口径，不能相加。 |

库存身份由类别/名称/单位组成，不暗中换算单位。FIFO 保存批次原数量、原金额、原单价和剩余量。每次出库成本为累计分摊差：`round(原批次金额 × 累计耗用量 / 原数量, 2) − 此前已分摊金额`。批次完全耗尽时吃掉全部余分。剩余价值=原入账价值−已分摊，不是剩余数量×显示单价。未知价格数量必须明确显示。

采购支出和 FIFO 耗用成本回答不同问题。月度经营利润采用采购/费用口径，包装、耗材和话费保持其记录中的费用分类。因此毛利减固定支出仍可能要再扣日结水电/其他才能等于净利。日明细卡有菜品成本时可以使用该成本；月度和日均毛利仍汇总日记账毛利。预计水电金额可以出现在费用详情，实际月固定支出和净利使用实付金额。

现金余额表通过“加一项 → 余额强制修改”设置某日实际余额；不产生营业收入/费用，不替换此前交易。普通条目保留删除规则，历史 `system_locked` 条目继续受保护。没有另一个独立“余额校正”表单。

<a id="languages"></a>

## 翻译界面时怎样保留用户原文

网页版提供中英文界面，macOS 客户端使用中文。网页中由系统提供的文字都需要翻译，包括对话框按钮、校验提示、角色名称和图例。账本名、店名、商品、菜品、自定义收入项目、备注、人名、供应商和计量单位按用户输入的原文显示。两种语言使用相同的存储键和枚举值。

给一个字段增加翻译时，可以按以下步骤检查。

1. 在界面代码或词典中补上固定标签，保留原来的存储键和值。
2. 对于“店名＋支付渠道”，先将店名转义后插入 HTML，再翻译渠道后缀。错误提示也按这个思路处理，翻译固定句式，填入用户原值。
3. 在有未保存内容时切换语言。当前面板和随后打开的对话框都应使用选中的语言。核对账本、日期、金额、草稿，以及保存请求中的数据。
4. 用一个名称恰好与词条相同的商品做测试。检查不同角色能看到的页面、输入提示、标题、无障碍标签和屏幕上显示的文字。

英文界面用 `CNY` 显示同一笔人民币金额。对于 `input[type=month]`，`web/i18n-controls.js` 在原生控件上显示 `YYYY-MM`，使不同操作系统下的月份字段格式一致。控件的值、校验、事件和日期选择仍由原生控件处理。弹出的日历由浏览器和操作系统提供。

### 翻译在哪些环节生效

`web/index.html` 在 `app.js` 和 `pro.js` 之后加载下面四份词典，随后才由 `v8.js` 建立查找表。

| 文件 | 范围 |
| --- | --- |
| `web/i18n-en.js` | 共用标签、系统消息模板、`systemMessage` 及 alert/confirm/prompt 显示。 |
| `web/i18n-inventory-en.js` | 库存工作区、入/出库、盘点、批次和品名更正弹窗。 |
| `web/i18n-backend-en.js` | 已知 API 错误/验证/状态模板、规范字段显示名及结构化审计摘要。 |
| `web/i18n-extra-en.js` | 其余历史流水/报表/现金、选择器、账号、临时权限和 Excel 文案。 |

这些词典扩充 `SYSTEM_EN` 和 `SYSTEM_EN_PATTERNS`。四份词典加载完毕后，再加载月份控件适配脚本，最后加载 `v8.js`。词典直接在源码中维护，随服务器文件清单一起发布，使用与其他脚本相同的缓存版本号。Exact 编译器另行处理业务脚本。

`v8.js` 翻译固定的文本节点和 `placeholder`、`title`、`aria-*`、`data-label` 等显示属性。它成对保存原文和译文。异步渲染改变文字后，观察器会翻译新的原文，合并同批更新，并且只写入发生变化的值。`v28.js` 用相同的机制保留原店名，同时翻译固定的支付渠道名称。

把人名、备注和其他用户输入的文字标记为 `data-user-content`。可编辑输入框和指定的账本、账号选择器也会跳过翻译。`sep07.js` 会给输入值的只读副本加上同样的标记，只有原值改变时才更新它。重建节点时要保留这个标记，否则翻译观察器和只读视图可能反复覆盖彼此的内容。

HTML 选项如果没有 `value`，提交时会使用屏幕上显示的文字。翻译标签前，先将原值明确写入 `value`。这样切换语言后，现金类型、固定费用类别等字段仍会提交相同的值。用户自建选项的标识和名称都保留原样。

`translateBackendMessage` 按预先定义的完整句式匹配服务端提示。已知字段名、错误位置和嵌套错误可翻译，用户名、备注、单位和路径保留原文。新增 API 错误句式时，要补上对应词条。整个过程保留原始响应数据和存储键。

`translateAuditSummary(summary, item)` 读取结构化的 `before_payload`、`after_payload` 和修改原因，翻译已知字段名，保留用户填入的值，并用 Added、Removed、Changed、Cleared 标明新增、移除、修改或清空。摘要最多列出 20 项变化，递归遍历也有深度限制。完整对比可查看原始数据。旧响应可能缺少这些字段，此时只翻译能识别的固定表述，含义无法确定的文字（如带分号的备注）保留原文。

相关回归入口为 `build/qa_english_ui.cjs`、`build/qa_inventory_english.cjs`、`build/test_i18n_backend.cjs`、`build/qa_enhanced_analytics.cjs` 及既有业务/金额测试。验收包括中英文往返、动态弹窗、错误路径、option 值不变、用户名字恰好等于字典词、只读镜像以及观察器不循环。

<a id="charts"></a>

## 看懂图表，核对导出明细

**更多统计**提供经营、费用和客流三个视图。先看图表上方选中的期间、指标和对比月份，再用明细表追溯合计值。费用视图可以核对按月填写的固定支出和逐笔登记的付款。同一笔费用可能在两处都有记录，核对时要分别看。

| 界面内容 | 怎样核对 |
| --- | --- |
| 摘要卡片 | 三个视图都显示有记录的天数。经营视图另列金额最大的费用类别和盈利天数，费用视图另列最大费用类别和固定支出的核对差额，客流视图另列客流最多的一天，以及已录入日期中客数大于零的天数。 |
| 趋势 | 折线图和柱状图使用同一批数据。统计栏给出数量、均值、最小值和最大值。未录入的日期留空，亏损画在零线以下。 |
| 明细表和 CSV | 导出沿用当前的排序和筛选。合计包含所有符合条件的行，即使明细已分页。CSV 表头随界面语言变化，用户录入的值保留原文。 |
| 横坐标 | SVG 绘图代码测量可用宽度，按所选期间缩写日期，为首尾刻度预留空间，并允许类别名称换行。窗口大小变化时重新排列标签，每个数据点仍可查看。 |
| 精确数值 | 悬停、点按或用键盘聚焦，可读到完整日期或类别及对应金额。方向键和 Home/End 键可在数据点间移动。图和表使用同一套计算结果。 |

桌面端“更多统计”会显示所选范围和来源记录数。窗口变窄时，筛选项自动换行，图表可从两列切换到一列。采购、耗用和计算方法区域可以折叠。所选指标混合金额、人数或比率时，界面会提示单位的差别。隐藏表格后依然能导出当前筛选结果，没有符合条件的记录时导出按钮不可用。

<a id="settings"></a>

## 配置项与服务启动

| 设置 | 含义和边界 |
| --- | --- |
| `DATABASE_URL` | 必需的 PostgreSQL SQLAlchemy DSN，值属于私密配置。 |
| `SECRET_KEY` | 必需 JWT 签名密钥，更改影响已有登录。 |
| `ADMIN_USERNAME`、`ADMIN_PASSWORD` | 首次管理员创建，不会自动重置已有账户。 |
| `CORS_ORIGINS` | 逗号分隔来源策略；同源网页无需单独浏览器 API 主机。 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 主 token 期限，代码默认 1440。 |
| `TEST_LOGIN_ENABLED` | 私有实例明确设 false。运行代码缺省值为 true，但公开模板/Compose 设置 false；不能认为不写就关闭。 |
| `TEST_USERNAME`、`TEST_DATASET_ID`、`TEST_ACCESS_TOKEN_EXPIRE_MINUTES` | 可选演示账户、账本和期限，演示行为有单独限制。 |
| `MAX_WORKBOOK_UPLOAD_BYTES` | 后端工作簿上限默认 25 MiB；Nginx 上限须匹配流程。 |
| `PAYMENT_SECRET_ROOT` | 受保护的账本/店铺商户文件根目录，独立于网页和数据库行。 |
| `BUSINESS_TIMEZONE`、`WECHAT_TIMEZONE` | 业务时钟/回退时区，不要与客户端本地月份显示边界混淆。 |
| `WECHAT_*` | 保留账单集成参数；当前启动明确不运行旧同步线程。 |
| 原生本机连接配置 | 监测器读取 `~/.restaurant_finance_sync/config.json`；通过 `RESTAURANT_MAIN_STATUS_PORT` / `RESTAURANT_ASSISTANT_STATUS_PORT` 配置端口，默认 47650/47651。不能把用户实际配置打成公开默认。 |

使用 Compose 时，配置项见 `.env.example`。直接运行 API 时，查看 `backend/.env.example`。真实凭据保存在该实例的私有配置中。Compose 指定 PostgreSQL 16 和 Nginx 1.28，网页端口默认绑定本机回环地址。数据库、支付密钥和恢复文件各自使用独立的卷，普通升级要保留这些卷。`docker compose down -v` 的 `-v` 会删除它们。

API 启动时会创建缺失的表，补齐已支持的录入计时字段，清理过期审计记录，创建初始管理员，并处理旧账号和测试账号的账本关联。其他数据库结构变更和历史金额修正需要单独处理。旧版微信定时同步线程默认不启动。支付下单、退款、清算、银行流水接入、高可用和集中监控需要另外配置相应服务。

<a id="tests"></a>

## 验证修改并构建发布包

下文命令均从仓库根目录运行，Python 使用 3.12。按仓库中的依赖清单和 Acorn 锁文件安装依赖。macOS 应用内置了自己的 Python/Qt 运行环境，因此源码测试通过后，还要测试打包好的应用。生成的报告、截图、导出文件和测试应用放在已忽略的 `work/`、`dist/` 或外部 CI 存储中。

### 源码环境与回归测试

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r build/test-requirements.txt -r desktop/requirements.txt
npm ci --prefix build/js-transform
node build/compile_exact_web.cjs

(cd backend && PYTHONPATH=.:tests python -m pytest -q tests)
for test in web/test_*.js; do node "$test" || exit 1; done
node build/test_exact_web.cjs
node build/test_i18n_backend.cjs
python build/test_fifo_contract.py
python build/test_deployment_cache_revision.py
python build/test_distribution_privacy.py
for test in build/test_v1_0_1_desktop.py build/test_v1_0_1_desktop_qt.py \
  build/test_v1_0_2_desktop.py build/test_v1_0_2_desktop_qt.py \
  build/test_v1_0_2_analytics_qt.py; do
  QT_QPA_PLATFORM=offscreen python "$test" || exit 1
done
```

FIFO 测试会导入桌面模块，要求 Node 在 `PATH`，也可把 `NODE_BINARY` 设为 Node 可执行文件的绝对路径。原生源码导入 `fcntl`，不宣称支持 Windows。Qt 测试使用 offscreen 平台；日常原生界面需要图形会话。测试使用隔离夹具，不能加载生产环境文件或真实账本。历史测试文件名表示仍需保护的回归行为，不应仅因版本变化而重命名。

### 浏览器 QA

在独立工具目录安装 Playwright 及 Chromium；也可用 `CHROME_EXECUTABLE` 指定已有且受支持的 Chrome/Chromium：

```bash
npm install --prefix work/browser-qa-tools --save-exact playwright
work/browser-qa-tools/node_modules/.bin/playwright install chromium

for test in qa_web_browser qa_dashboard_charts qa_cost_ring qa_english_ui qa_inventory_english \
  qa_enhanced_analytics qa_analytics_english_advanced; do
  PLAYWRIGHT_MODULE="$PWD/work/browser-qa-tools/node_modules/playwright" \
  QA_OUTPUT_DIR="$PWD/work/qa/$test" node "build/$test.cjs" || exit 1
done
```

`QA_OUTPUT_DIR` 必须为可写绝对目录。保留验收记录时，每次运行使用新目录；脚本会在其中写报告和截图。`PLAYWRIGHT_MODULE` 指定已安装 Node 模块，`CHROME_EXECUTABLE` 可选指定浏览器，`RELEASE_SOURCE_ROOT` 可选切换待测源码树；默认以本地文件方式加载本仓库 `web/index.html`。外部 HTTP 被阻断，合成记录替代真实账号。验收保持默认断言模式，`QA_DIAGNOSTIC=1` 只用于诊断，不能算通过验收。

`build/qa_web_browser.cjs` 用合成账本操作食材编辑器，检查同一账本同步后首页、月报和说明里的金额。`build/qa_dashboard_charts.cjs` 将显示的五张卡片和两个指标选择器的数值与合成账目对照，并生成中英文的主页指标、趋势图和预测说明截图。`build/qa_cost_ring.cjs` 在手机和桌面宽度检查圆心与金额的实际位置、图例和类别颜色，并生成环图截图。桌面工作簿成功保存后会通知当前打开的仪表盘和报表，重新读取预测和成本明细。

浏览器检查覆盖手机/电脑宽度、所选期间与跨月切换、图表标签/交互、固定英文、用户值保持和规范保存枚举。修改业务源后，应测试实际编译资源。仅有截图不能证明财务或权限行为正确。

### 服务器归档

在已经跟踪所需运行文件的 Git 工作副本中构建。构建前审查未提交修改；构建器检查路径是否被跟踪，但不能代替工作区状态审查。

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
(cd dist && shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256)
```

输出路径必须不存在。归档根目录为 `restaurant-cloud-v1.0.2/`，包含 API/静态网页、部署工具、配置示例、`VERSION` 及 SHA-256 `MANIFEST.json`，不包含数据库和运行凭据。将归档文件哈希与选定源码逐一核对，再按 [部署指南](DEPLOYMENT.zh-CN.md) 执行部署及已安装/HTTP 文件验证。健康接口只返回软件版本，不足以证明构建修订或网页资源正确。

### macOS App 与打包运行库 QA

原生重建工具要求 macOS、Python 3.12，以及可信的现有双架构 Python/Qt App 作为 `--runtime-app`。该运行库是另行提供的发布输入，不放进 Git。工具保留其他运行条目，仅替换主脚本字节码，更新两个架构，设置最低 macOS 15，并生成 ad-hoc 签名；不执行 Apple 公证。输出必须使用新路径。

```bash
python build/rebuild_macos_app.py \
  --runtime-app /absolute/path/to/Runtime.app \
  --source desktop/restaurant_cost_manager.py \
  --output dist/Finance.app --version v1.0.2 \
  --report work/qa/app-build.json

python build/verify_macos_app.py \
  --app dist/Finance.app --source desktop/restaurant_cost_manager.py \
  --runtime-app /absolute/path/to/Runtime.app --version v1.0.2 \
  --report work/qa/app-verification.json
codesign --verify --deep --strict dist/Finance.app
```

`build/qa_packaged_desktop.py` 是独立离线 QA App 的主入口，不能替换生产候选 App 的业务入口。另建一个 QA App，让它读取待测候选 App 的主字节码：

```bash
python build/rebuild_macos_app.py \
  --runtime-app /absolute/path/to/Runtime.app \
  --source build/qa_packaged_desktop.py \
  --output dist/Finance-QA.app --version v1.0.2 \
  --report work/qa/qa-app-build.json

V101_SOURCE_ROOT="$PWD" \
V101_PRODUCTION_APP="$PWD/dist/Finance.app" \
V101_QA_DIR="$PWD/work/qa/packaged-arm64" \
/usr/bin/arch -arm64 "$PWD/dist/Finance-QA.app/Contents/MacOS/Finance-QA"
```

在兼容主机上另用 `/usr/bin/arch -x86_64` 运行相同 QA 可执行文件，并设置另一个 `V101_QA_DIR`；Apple Silicon 上执行 x86_64 需要 Rosetta。若复用运行库没有 `unittest.mock`，可仅为 QA 设置 `V101_QA_STDLIB`，指向 Python 3.12 标准库目录。这些环境变量沿用历史 `V101` 名字，实际测试的是 `V101_PRODUCTION_APP` 指定的候选 App。测试禁网，所有可写用户路径重定向到 QA 目录。

记录实际测试的源码提交、修订、环境和结果，区分重跑检查与沿用证据。SQLite 夹具不证明生产 PostgreSQL 并发负载，Rosetta 执行不代表已经在实体 Intel 硬件测试，数据库 dump 可读也不等于完整恢复演练通过。

<a id="recovery"></a>

## 组装 ZIP 或恢复已有实例

需要一起交付源码、文档、已校验的服务器部署包和可选的 macOS 应用时，先把这些内容放入 Git 工作区之外的暂存目录。在暂存根目录放入 `VERSION` 和生成的 `RELEASE_INFO.json`。其中必须提供 `build_revision`，并建议记录源码提交和各产物的哈希，便于接手人核对。服务器 tar 包有独立的构建工具。完整 ZIP 按下列命令生成。

```bash
python -B build/make_complete_package.py \
  --root /absolute/path/to/staging/Release \
  --output "$PWD/dist/complete-release.zip"
python -B build/verify_package.py --root /absolute/path/to/extracted/Release
```

ZIP 输出必须在暂存树之外且尚不存在。组装工具更新 `PACKAGE_MANIFEST.json`，保留 UTF-8 文件名、Unix 权限和内部符号链接，并生成外层 `.sha256`。暂存树不能带 `.git`、依赖/虚拟环境目录和缓存。重新解压到新位置，验证清单、内嵌服务器归档和 App 签名。公开软件产物不应包含真实服务器身份、个人本机路径、业务数据、运行环境值或凭据；运维备份应放在独立受保护存储中。

可恢复的运维备份需要数据库 dump、匹配的程序/配置版本、运行密钥、相关外部文件、服务/Nginx 布局及数据库/角色假设。商户文件可能保存在 PostgreSQL 之外的 `PAYMENT_SECRET_ROOT`。SSH 私钥、数据库密码、JWT 签名密钥和商户密钥用途各不相同。先在隔离环境演练恢复，验证表结构、数据和关键流程；Excel 交换工作簿不能替代完整系统备份。

程序回退和数据库恢复是不同操作，不能自动用升级前快照覆盖较新的数据库。部署核验期间保留当前备份，之后清理也须明确审查目标目录。随附部署脚本保留备份、不恢复数据库。数据库前后验证完成之前应暂停业务写入；摘要变化时，先调查并发写入与允许的审计保留清理，再判断是否数据损坏。

<a id="troubleshooting"></a>

## 排查运行中的问题

| 现象 | 先检查 | 避免 |
| --- | --- | --- |
| 都显示 v1.0.2，但页面旧 | HTML 修订、资源 query、HTTP 文件 hash、实际服务/web root。 | 不核对部署文件而反复清缓存。 |
| 英文中仍有中文 | 区分固定 UI 和用户原文，查延迟渲染/弹窗、字典和当前语言。 | 翻译所有中文或改 payload key。 |
| 毛利减固定不等于净利 | 日结水电、其他费用；月保存固定与逐笔固定口径。 | 为凑等式更改毛利。 |
| 月初日均无值 | 已过自然天数为 0，实际净利可以独立存在。 | 强制除以 1、虚构平均。 |
| 历史预测等于实际净利 | 下个月 1 日后的要求，核对本地当前日期。 | 改回旧预测。 |
| 切账本后现金跳变 | 上下文/revision、共用缓存、请求返回先后。 | 再造独立缓存或无条件应用晚响应。 |
| 导入金额不同 | 原始 XML/JSON 小数、规范化路径、逐行舍入与总额舍入。 | float 解析之后再转字符串。 |
| FIFO 差几分钱 | 累计分摊、最后余分、已知零/未知价。 | 用数量乘已舍入平均价。 |
| 横坐标挤压 | 实际字体/宽度、最后刻度预留、换行空间、ResizeObserver。 | 删除观察数据来适应标签。 |
| 原生窗口太宽 | minimum size、控件分行、scroll area、Matplotlib 排版。 | 强制要求 1600px 屏幕或把全部控件加大。 |
| 上传未到 API 已失败 | Nginx/后端上限、内容类型、结构和授权。 | 绕过校验或导入错账本。 |
| 部署数据库摘要变化 | 对照前后证据调查授权并发写入及审计保留。 | 未调查就删备份或恢复旧库。 |
| 新 App 行为仍旧 | 实际候选主字节码与最终源码、启动文件、签名/架构。 | 只改版本文本或旁边 `.py`。 |

<a id="api-routes"></a>

## 按操作查找 HTTP 接口

要查看某个接口的请求模型、响应格式和权限检查，可以按最后一栏的函数名查找。也可以通过运行中实例的 `/openapi.json` 查看该实例的接口说明。`record_key:path` 可以包含路径字符，请求时要正确进行 URL 编码。现金接口的两种拼写都是受支持的别名。

| 方法 | 路径 | 源码函数 |
| --- | --- | --- |
| GET | `/api/v1/health` | `main.py:health` |
| POST | `/api/v1/auth/login` | `main.py:login` |
| POST | `/api/v1/auth/test-login` | `main.py:test_login` |
| GET | `/api/v1/auth/me` | `main.py:me` |
| GET | `/api/v1/users` | `main.py:list_users` |
| POST | `/api/v1/users` | `main.py:create_user` |
| PATCH | `/api/v1/users/{user_id}` | `main.py:update_user` |
| DELETE | `/api/v1/users/{user_id}` | `main.py:delete_user` |
| GET | `/api/v1/temporary-permissions` | `main.py:list_temporary_permissions` |
| POST | `/api/v1/temporary-permissions` | `main.py:create_temporary_permission` |
| DELETE | `/api/v1/temporary-permissions/{permission_id}` | `main.py:delete_temporary_permission` |
| GET | `/api/v1/datasets` | `main.py:list_datasets` |
| POST | `/api/v1/datasets` | `main.py:create_dataset` |
| PATCH | `/api/v1/datasets/{dataset_id}` | `main.py:rename_dataset` |
| DELETE | `/api/v1/datasets/{dataset_id}` | `main.py:delete_dataset` |
| GET | `/api/v1/datasets/{dataset_id}/workbooks/internal` | `main.py:download_internal_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/internal` | `main.py:upload_internal_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/internal-overwrite` | `main.py:upload_internal_workbook_with_backup` |
| GET | `/api/v1/datasets/{dataset_id}/workbooks/user` | `main.py:download_user_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/user` | `main.py:upload_user_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/user-merge` | `main.py:merge_user_workbook` |
| POST | `/api/v1/devices/register` | `main.py:register_device` |
| GET | `/api/v1/datasets/{dataset_id}/store-settings` | `main.py:get_store_settings` |
| PUT | `/api/v1/datasets/{dataset_id}/store-settings` | `main.py:update_store_settings` |
| GET | `/api/v1/datasets/{dataset_id}/cash-position` | `main.py:get_cash_position` |
| GET | `/api/v1/datasets/{dataset_id}/cash_position` | `main.py:get_cash_position` |
| PUT | `/api/v1/datasets/{dataset_id}/cash-position` | `main.py:update_cash_position` |
| PUT | `/api/v1/datasets/{dataset_id}/cash_position` | `main.py:update_cash_position` |
| GET | `/api/v1/datasets/{dataset_id}/entry-windows` | `main.py:list_entry_windows` |
| POST | `/api/v1/datasets/{dataset_id}/records/bulk-delete` | `main.py:bulk_delete_records` |
| POST | `/api/v1/datasets/{dataset_id}/records/delete-month` | `main.py:delete_month_records` |
| POST | `/api/v1/datasets/{source_dataset_id}/copy-to-ledger` | `main.py:copy_entire_ledger` |
| GET | `/api/v1/datasets/{dataset_id}/records` | `main.py:list_records` |
| GET | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}` | `main.py:read_record` |
| PUT | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}` | `main.py:write_record` |
| POST | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}/delete` | `main.py:delete_record` |
| GET | `/api/v1/datasets/{dataset_id}/changes` | `main.py:changes` |
| GET | `/api/v1/audit` | `main.py:audit_logs` |
| DELETE | `/api/v1/audit/{audit_id}` | `main.py:delete_audit_log` |
| DELETE | `/api/v1/audit` | `main.py:delete_audit_logs` |
| POST | `/api/v1/audit/delete` | `main.py:delete_audit_logs_body` |
| GET | `/api/v1/conflicts` | `main.py:list_conflicts` |
| POST | `/api/v1/conflicts/{conflict_id}/resolve` | `main.py:resolve_conflict` |
| POST | `/api/v1/datasets/{dataset_id}/inventory/name-corrections/preview` | `name_corrections.py:preview_correction` |
| POST | `/api/v1/datasets/{dataset_id}/inventory/name-corrections/apply` | `name_corrections.py:apply_correction` |

<a id="privacy"></a>

## 分享前检查发布包

用 `build/audit_distribution_privacy.py` 扫描解压目录、ZIP、tar 或 macOS 应用。把要核对的标识写在单独的文件中，可用 JSON 字符串数组，也可用 UTF-8 文本每行一项。该文件放在仓库和分发目录之外。工具只读取待检文件，检查 UTF-8 和 UTF-16 数据、完整私钥块、归档路径和链接，并解包检查两种 Mach-O 架构里的 PyInstaller CArchive/PYZ 内容。输出中会隐去密钥片段。可运行 `build/test_distribution_privacy.py` 用合成测试数据核对扫描结果。

在仓库根目录运行以下命令，检查已构建的服务器包，把报告写入已忽略的测试目录。

```bash
python -B build/audit_distribution_privacy.py \
  dist/restaurant-cloud-v1.0.2-deploy.tar.gz \
  --forbid-file /absolute/private/identifiers.txt \
  --report work/qa/privacy-report.json
```

完整 ZIP 或其解压目录也按相同步骤扫描。发布前人工核对扫描列出的工作簿、数据库和配置，并查看截图及日志。扫描器只统计图片数量，不做文字识别。它能匹配已知标识和私钥特征。凭据、实际经营数据和恢复备份另存于私有位置。验收结果随相应版本或 CI 运行记录保存，方便追溯当时的源码和构建号。
