# 工程技术参考 · v1.0.2

**[← 返回中文 README](../README.md)** · [English](ENGINEERING_REFERENCE.md) · [更新日志](<../CHANGELOG (中文).md>) · [部署指南](DEPLOYMENT.zh-CN.md)

修改报表时，可以先查计算公式和对应的测试。排查保存或同步问题时，沿着编辑器、API 和 PostgreSQL 追踪同一条记录。安装步骤见[部署指南](DEPLOYMENT.zh-CN.md)。

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
| `web/index.html` | 页面结构、DOM ID、样式表和脚本加载顺序、构建号，以及用于刷新缓存的查询参数。修改元素 ID 前先查找引用。 |
| `web/money.js` | 基于 BigInt 的精确十进制运算。直接修改此文件。 |
| `build/web-exact-source/app.js` | 共享状态、权限检查、API 调用及记录格式整理。还负责保留编辑前的原始记录，并处理报表、统计期间和界面语言切换。 |
| `build/web-exact-source/pro.js` | 记账、采购和菜品编辑器，以及明细行解析、报表和早期的统计页面。 |
| `web/i18n-en.js`、`i18n-inventory-en.js`、`i18n-backend-en.js`、`i18n-extra-en.js` | 分别维护主界面、库存、API 错误与审计记录，以及旧版页面的英文词条。四份词典均在 `v8.js` 之前加载。 |
| `web/i18n-controls.js` | 英文界面的月份字段显示为 `YYYY-MM`，同时保留原生选择器、字段值、事件和校验。在词典之后、`v8.js` 之前加载。 |
| `build/web-exact-source/v8.js`、`v28.js` | 选择对话框、门店设置，以及防止旧账本的请求更新当前账本的检查。 |
| `build/web-exact-source/sep04.js` | 现金余额页面、现金条目、缓存更新及旧记录兼容处理。 |
| `build/web-exact-source/sep05.js`、`sep07.js` | 扩展报表、编辑、权限及客流统计的处理函数。调试时要查明最后生效的封装函数。 |
| `build/web-exact-source/inventory-fifo.js` | 按先进先出顺序重算库存流水，将每一批的成本准确分摊到各次出库。 |
| `build/web-exact-source/oct29.js` | 记账页面使用的其他账务和库存操作。 |
| `build/web-exact-source/inventory-workspace.js` | 库存单据、每笔库存变动的原始记录，以及更正品名的界面。 |
| `web/workbench.js`、`web/workbench.css` | 导航、页面标题及响应式布局。这两个文件都直接维护。 |
| `build/web-exact-source/charts-oct30.js` | 绘制 SVG 图表和坐标轴，处理鼠标、触屏及键盘操作，在容器尺寸变化时重新绘图。 |
| `build/web-exact-source/dashboard-oct30.js` | 仪表盘的五张指标卡、各卡的环比说明，以及主页图表。 |
| `build/web-exact-source/analytics-oct30.js`、`web/analytics-oct30.css` | 经营、费用和客流三个统计视图及其筛选功能，也包含费用计算、明细表和页面布局。 |
| `desktop/restaurant_cost_manager.py` | PySide6 控件、财务计算、工作簿读写和云端同步集中在同一模块中。可按类名或函数名定位。 |
| `backend/app/main.py` | API 路由、记录权限、现金汇总、启动时的数据库兼容更新，以及审计日志维护。 |
| `backend/app/models.py`、`database.py`、`security.py` | SQLAlchemy 数据模型、数据库会话、精确保存 JSON 数值、密码哈希和 JWT 处理。 |
| `backend/app/money.py`、`money_routes.py`、`excel_io.py` | HTTP 请求中的金额解析、JSON 序列化，以及 Excel 导入导出。 |
| `backend/app/inventory_balance.py`、`inventory_validation.py` | 重算库存数量，并在写入事务中校验库存余额和单据金额。FIFO 成本分摊的实现位于网页和桌面客户端。 |
| `backend/app/name_corrections.py`、`ingredient_corrections.py` | 预览关联记录，同时更新名称和盘点调整，检查请求是否已过期，保存回执以便安全重试。 |
| `backend/app/store_settings.py`、`wechat_pay.py`、`wechat_sync.py` | 门店设置和微信商户账单接入。服务启动时不会运行旧版定时同步任务。 |

修改网页业务逻辑时，先编辑 `build/web-exact-source/` 下的脚本，再运行 `node build/compile_exact_web.cjs`。该脚本用 Acorn 解析源码并重新生成对应的 `web/*.js`，两份文件一起提交。HTML、CSS、`money.js`、`workbench.js`、翻译词典和许可证都直接维护。哪些文件由编译生成，可以查看编译脚本中的清单。部署后浏览器只加载静态文件，运行时无需 Node、Acorn、打包工具或 CDN。

<a id="database"></a>

## 一个账本怎样存入数据库

生产环境使用 PostgreSQL，字段不固定的业务记录保存在 JSONB 列中。启动时会调用 SQLAlchemy 的 `create_all`，并执行代码中列明的几项兼容性更新。修改数据库结构时，要另行安排迁移。测试也会用到 SQLite 适配器。

| 数据表 | 保存什么 | 修改时要注意什么 |
| --- | --- | --- |
| `app_users` | UUID、唯一用户名、显示名、密码哈希（bcrypt）、角色和启用状态。 | 修改初始化密码的环境变量后，已有管理员仍使用原密码。 |
| `datasets` | 固定的账本 ID、显示名及数据结构版本。 | 更名后沿用原 ID 查找记录和权限。 |
| `user_dataset_memberships` | 每个用户与账本的关联各占一行，并标明是否为默认账本。 | 非管理员即使在界面上能看到某个账本，服务端也要检查其成员资格。 |
| `devices` | 设备 ID、账本 ID、平台、设备名称和上次活动时间。 | 注册设备或请求缓存时，记下当时选中的账本。 |
| `sync_records` | 唯一键 `(dataset_id, record_type, record_key)`、记录内容、校验和、版本号、同步序号和删除状态。 | 写入时检查预期版本，保留删除标记以便其他客户端同步。识别明细行时不能只看品名。 |
| `entry_timings` | 首次保存时间、各字段和明细行的时间戳，以及旧记录的计时数据。 | 改动记录内容后，更正及补录的原有截止时间仍有效。 |
| `audit_logs` | 修改前后的内容、操作者、来源、事件、设备、版本变化、序号和时间戳。 | 审计记录会过期，管理员也可以删除，因此备份需单独保存。 |
| `temporary_permissions` | 用户、账本、授权角色、可操作的业务日期及授权生效时间段。 | 同时检查记录所属的业务日期，以及用户实际执行修改的时间。 |
| `sync_conflicts` | 本地和服务端版本、两端的记录内容、冲突状态、处理结果和备注。 | 解决冲突时执行与普通写入相同的金额校验和权限检查。 |
| `inventory_name_corrections` | 账本与请求 ID 的唯一组合、请求哈希、请求和响应内容，以及更正原因。 | 审计清理后仍保留回执。使用原 ID 重试时，请求内容也必须与原请求一致。 |

日记录可包含 `daily`、`dishes` 和 `fixed_expenses` 数组，月记录保存 `monthly_fixed`。全局记录保存设置、字典、现金条目和库存数据。旧格式的同一条记录可能含有多个业务日期。编辑某一天时，只合并各数组中该日的明细，保留其他日期和无法确定日期的行。如果当天没有菜品记录，则显示空列表。

导入或编辑时，ID、日期、版本、记录键、名称、备注和自定义元数据都保留原类型，暂不识别的字段也应原样保留。同名的两笔采购可能有不同的单位、价格或备注。移动或删除时，要依据选中行本身的标识。

内部工作簿按记录类型分表，例如 `__day_records`、`__month_records`、`__global_records`、`__meta` 和 `__audit_records`。记录表将结构化内容保存在 `payload_json` 中。用户工作簿按业务整理成方便手工填写的表格。导入时，合并记录和整表替换使用不同接口。要恢复整个服务器，还要另行备份账号、账本成员关系、录入时间戳、商户密钥、运行设置和服务配置。

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

读取旧版 JSON 时，先保留原始十进制文本，再做数值转换。如果直接读取 Excel 会损失精度，就从底层 OOXML 单元格取值。金额规范化仅针对已知金额字段，包括明细行里的金额，其他元数据保持原样。计算和格式化都使用 `Exact`，只在最后绘图时才把图表坐标转成浮点数。

主页五项依次为日均收入、日均毛利润（毛利率）、预计月底盈亏、预计 本月每日盈亏、净利润（净利率）。前两项算到昨天，分母是截至昨天已过的自然天数。第四张卡显示每天的盈亏金额，下方百分比是与上月每日盈亏的环比。第五张卡包含今天已录的收支和整月已保存的固定支出。其净利率用实际月净利润除以含今天的本月实际收入，收入缺失或为零时不可用。完整月报里的实际日均净利润用实际净利润除以已过自然天数。

每日趋势和各星期平均默认都显示收入。两张图可分别选择收入、毛利润、净利润或食材成本。前三项取自日账，食材成本包含佐料采购。每日趋势中未录入的日期留空。计算某个星期几的平均值时，先汇总所选月份中该星期几的数值，再除以有记录的天数。有业务记录但金额为零的日期计入天数，空行跳过。某个星期几一次也未录入，就没有平均值。月底预测另按已过的自然天数计算。

主页“开销构成”展示所选日各项支出。类别颜色固定，其他类别是否出现都不会使颜色错位。图例以同色标记列出类别、金额和占比。圆心金额为该日图中各项支出之和。实际日图只绘制正数支出，日固定费用按现有分摊口径取值。原生端月度支出图按既有类别绘制整月固定费用，手续费不在该月图内。核对圆心时，应当将同一张图的扇区相加。月底预测从账本重新计算整月金额。

日环图以 `dayMetrics` 中的成本类别键为依据。配色表 `costDonutColors` 和绘制函数 `renderCostDonut` 在 `build/web-exact-source/app.js` 内，环形色块和图例从同一张表取色。修改后用 `build/compile_exact_web.cjs` 重新生成网页文件。窄屏布局及圆心内名称、金额和单位的居中样式在 `web/reporting-oct30.css`，原生程序对应 `DashboardTab._draw_cost_ring`。

### 预计月底盈亏

主页与完整月报使用同一结果。中文标题第一行是 `预计月底盈亏`，第二行是 `(根据 本月预计成本 和 本月预计收入 计算)`。英文两行分别是 **Estimated month-end profit/loss** 和 **(based on this month’s projected costs and revenue)**。悬停或点击旁边的 **i**，可查看计算方式、取数截至哪一天，以及跨月后怎样显示。网页版说明跟随界面语言，“更多统计”的高级视图也复用这份说明。同步替换按钮时，已经打开的说明会关联到新按钮并刷新金额。原生客户端以中文说明同一规则。

以下各项都取同一账本的数据，**D** 是本月自然天数。上月按其全部自然天数计算日均值，跨年也一样。本月计算日均收入、日均食材成本和日均其他成本时，分母统一为截至昨天已过的自然天数。收入只取到昨天，当天的成本在保存后就计入，未来日期的记录排除。没有记账的日子也计入天数。

| 项目 | 计算方式 |
| --- | --- |
| 本月预计收入 | 本月截至昨天的日均收入 × D。 |
| 预计固定成本 | 比较上月和本月已保存的整月固定支出，取较高金额。固定支出中的水电煤气按实付金额计算。 |
| 预计食材成本 | 各期间分别将食材和佐料采购成本相加，比较两个月的日均值，取较高值 × D。 |
| 预计其他成本 | 各期间分别用总成本减去食材成本（含佐料）和整月固定支出，剩余为日结水电、手续费及其他费用。比较两个月的日均其他成本，取较高值 × D。 |
| 预计月底盈亏 | 本月预计收入 − 预计固定成本 − 预计食材成本 − 预计其他成本。 |
| 预计 本月每日盈亏 | (预计月底盈亏 ➗ 本月天数)。用尚未舍入的月底盈亏除以 D。已结月用实际净利润除以该月自然天数。月度盈亏缺失时显示破折号。 |

**11 月 11 日记了一笔买菜支出。** 本月已经过了 10 天。10 月有 31 天，11 月有 30 天。下表金额单位为元。

| 项目 | 10 月 | 11 月已记 | 11 月预计 |
| --- | ---: | ---: | ---: |
| 固定成本 | 6,000 | 6,500 | 6,500 |
| 食材及佐料 | 9,300（日均 300） | 2,600（日均 260） | 9,000 |
| 其他成本 | 1,550（日均 50） | 750（日均 75） | 2,250 |
| 截至昨天的收入 | — | 8,000（日均 800） | 24,000 |

说明中显示预计日均总成本 **591.67 元**、预计总成本 **17,750.00 元**、预计收入 **24,000.00 元**。预计月底盈利 **6,250 元**。现在保存一笔日期为 11 月 11 日、金额 600 元的买菜支出，11 月日均食材成本变为 3,200 ÷ 10 = 320 元，高于 10 月的 300 元。预计食材成本随之升至 9,600 元，预计盈利降至 **5,650 元**。如果 11 月 11 日记的是营业收入，则到 11 月 12 日才会计入预计收入。

**怎样舍入。** 设 **e** 为本月截至昨天已过的自然天数，**p** 为上月天数。两项变动成本分别比较 `本月合计 × p` 和 `上月合计 × e`，二者的公分母都是 `e × p`。用 `本月收入 × p` 减去两项成本各自较大的分子，再乘以 **D**，减去 `预计固定成本 × e × p`。最后只除一次 `e × p`。即使中间的日均值是循环小数，恰好半分的结果也能正确舍入。

**缺少记录时怎么办。** 如果本月还没保存固定成本，就采用上月固定成本；明确存为零则按零参与比较。上月只要有记录即可，包括保存的零值或单独一条固定成本记录。本月须在截至昨天的日期里至少有一条经营记录。本月第一天、选择未来月份或任一期缺少所需数据时，预测暂不可用。两个月的“其他成本”都包含手续费、日结水电等费用，以及归在“其他”类别的支出。

说明里的日均总成本含固定支出。设核算盈亏时尚未舍入的预计总成本分子为 N。月总成本为 `N ÷ (e × p)`，日均总成本为 `N ÷ (e × p × D)`。两项分别格式化到分。月结后，三行改为实际日均总成本、实际总成本和实际收入，日均用全月实际总成本除以该月自然天数。缺少计算依据的金额显示破折号。

第四张卡沿用第三张卡的盈亏分子，一次除以 `e × p × D`，显示时才舍入到分。上文十一月的采购保存前为 6,250 ÷ 30 = **208.33 元/天**，保存后为 5,650 ÷ 30 = **188.33 元/天**。若某次十一月预计月底盈亏恰为 0.145 元，第三张卡显示 0.15 元，第四张卡按 0.145 ÷ 30 计算，显示 **0.00 元/天**。

要复现跨月环比，可在空测试账本中为 2024 年 1 月 1 日录入收入 310 元，为 2 月 1 日录入收入 580 元，各项成本均为零。月结后查看 2 月，第三张卡显示 580.00 元。第四张卡将 2 月的 580 ÷ 29 = **20.00 元/天** 与 1 月的 310 ÷ 31 = **10.00 元/天** 比较，环比增加 **100.0%**。第五张卡显示实际净利润 580.00 元，净利率 100.0%。改用平年 2023 年、2 月收入 560 元，2 月分母为 28 天。

环比对两个月尚未舍入的每日盈亏通分后再比较。例如十一月净额为 0.03 元、十月净额为 2.00 元，两个月的每日盈亏分别按 0.03 ÷ 30 和 2.00 ÷ 31 计，降幅恰为 98.45%，显示为 **98.5%**。

**修改计算逻辑时从哪里入手。** 在 `build/web-exact-source/app.js` 中，`monthOverviewMetricsV102` 汇总账目，`monthForecastV102` 每次刷新时据此计算预测，返回 `net`、`dailyNet`、`netNumerator` 和 `dailyNetDenominator`。`dashboard-oct30.js` 的 `summary` 将两个月各自的分子与除数交给 `monthChangeV102` 计算环比。主页和月报使用同一份预测。说明区按未舍入的值比较，列出两个月的候选金额，并标明取自哪一月或两月持平。固定成本按整月金额比较，食材和其他成本按日均金额比较。

桌面端对应 `desktop/restaurant_cost_manager.py` 中的 `calc_dashboard_month_kpis`，返回的 `projected_daily_net` 由 `DashboardTab._refresh_month_headlines` 显示。运行 `node web/test_v1_0_2_dashboard.js` 核对二月算例和舍入边界，运行 `python build/test_v1_0_2_desktop.py` 核对桌面计算，用 `QT_QPA_PLATFORM=offscreen python build/test_v1_0_2_desktop_qt.py` 检查实际界面的卡片顺序、金额和利润率。测试账本可以让食材成本取上月、其他成本取本月，以确认两项分别比较。加入一笔当天的采购和一笔佐料，能一并检查日期截止及重复计入问题。

是否跨月取决于客户端的本地日期。即使账本没有新增记录，网页和桌面端也会约每五秒检查一次日期。浏览器标签页恢复可见时会再检查一次。macOS 客户端如遇弹窗，会在弹窗关闭后刷新，读取失败则重试。从次月 1 日起，回看上月时，预测卡显示该月实际净利润，选中的期间保持不变。该数值实时取自账本，补录或更正历史账目后也会随之更新。

| 客户端日期 | 所选月份 | 预测卡金额 |
| --- | --- | --- |
| 10 月 31 日 | 10 月 | 当月预测。 |
| 11 月 1 日 | 10 月 | 10 月实际净利，不再需要上月成本。 |
| 11 月 1 日 | 11 月 | 已过一天前不可预测，实际净利可单独存在。 |
| 1 月 1 日 | 上年 12 月 | 12 月实际净利。 |
| 11 月 10 日 | 12 月 | 未来期间，不可用。 |

| 指标 | 计算方法或记账口径 |
| --- | --- |
| 收入 | 有有效渠道明细时按渠道汇总。旧记录只有总额时，读取 `收益` 或 `总金额`。这类已存总额可能已包含各渠道，不能再重复加总。 |
| 毛利润 | 收入 − 食材 − 佐料 − 手续费。 |
| 毛利率 | 日均毛利润 ÷ 同一截止日期的日均收入。收入缺失或为零时不显示毛利率。 |
| 变动成本 | 食材 + 佐料 + 日结水电 + 其他 + 手续费。 |
| 月固定支出 | 按月保存的人工、房租物业、已付水电燃气费和其他固定支出。 |
| 月总成本 | 日变动成本合计 + 整月已保存固定支出。 |
| 月净利润 | 收入 − 月总成本。 |
| 环比 | `（本期 − 上期）/ 上期绝对值 × 100`。上期值缺失或为零时，注明无法比较的原因。 |
| 余额强制修改 | 设置指定日期的实际现金余额。该调整不会产生营业收入或经营成本。 |
| 固定费用比较 | 按月填写的固定支出和逐笔登记的付款用于互相核对，两者相加会重复计算。 |

库存按类别、品名和单位识别物品。单位不同，库存项就不同。每个先进先出批次都保存原始数量、入账金额、单价和剩余数量。单次出库成本为 `round(批次原金额 × 累计出库量 / 批次原数量, 2) − 此前已分摊金额`。最后一次出库分摊余下的尾数。用入账金额减去累计分摊成本，即得该批次的剩余价值。单价未知的库存数量应始终能单独识别。

月度经营利润按账本中登记的采购和支出计算，FIFO 衡量已耗用库存的成本。包装、耗材、话费沿用录入时的费用分类。用毛利润核对净利润时，除固定支出外，还要扣除日结水电等费用及归在“其他”的支出。当天的明细卡片在有菜品成本时可用该成本计算，月度和日均毛利润则取日账中的毛利润。费用明细可以列出预计水电费，月固定支出与净利润以实付金额为准。

设置某天的实际现金余额时，打开**加一项 → 余额强制修改**，输入日期和余额。该操作记录一次余额调整，保留此前的现金流水，也不产生收入或费用。普通流水沿用原有删除规则，标有 `system_locked` 的历史条目仍受保护。

<a id="languages"></a>

## 翻译界面时怎样保留用户原文

网页版支持英文和中文，macOS 应用使用中文。对话框按钮、校验提示、角色名称、图例等系统文字都要翻译。账本名、店名、商品名、菜品名、自定义收入来源，以及备注、人名、供应商和单位均保留用户原文。切换语言时，底层存储键和枚举值保持一致。

给字段增加翻译时，逐项检查以下行为。

1. 在界面代码或词典中补上固定标签，保留原来的存储键和值。
2. 对于“店名＋支付渠道”，先将店名转义后插入 HTML，再翻译渠道后缀。错误提示也按这个思路处理，翻译固定句式，填入用户原值。
3. 在有未保存内容时切换语言。当前面板和随后打开的对话框都应使用选中的语言。核对账本、日期、金额、草稿，以及保存请求中的数据。
4. 用一个名称恰好与词条相同的商品做测试。检查不同角色能看到的页面、输入提示、标题、无障碍标签和屏幕上显示的文字。

英文界面用 `CNY` 显示同一笔人民币金额。对于 `input[type=month]`，`web/i18n-controls.js` 在原生控件上显示 `YYYY-MM`，使不同操作系统下的月份字段格式一致。控件的值、校验、事件和日期选择仍由原生控件处理。弹出的日历由浏览器和操作系统提供。

### 翻译在哪些环节生效

`web/index.html` 在 `app.js` 和 `pro.js` 之后加载下面四份词典，随后才由 `v8.js` 建立查找表。

| 文件 | 范围 |
| --- | --- |
| `web/i18n-en.js` | 通用标签、系统消息模板、`systemMessage`，以及提示、确认和输入对话框的文字。 |
| `web/i18n-inventory-en.js` | 库存页面、入库、出库、盘点，以及批次和品名更正对话框。 |
| `web/i18n-backend-en.js` | API 错误、校验与状态提示、字段标签和结构化审计摘要。 |
| `web/i18n-extra-en.js` | 旧版记账、报表及现金页面的标签与提示，以及选择器、账号、临时授权和 Excel 操作的相关文字。 |

这些词典扩充 `SYSTEM_EN` 和 `SYSTEM_EN_PATTERNS`。四份词典加载完毕后，再加载月份控件适配脚本，最后加载 `v8.js`。词典直接在源码中维护，随服务器文件清单一起发布，使用与其他脚本相同的缓存版本号。Exact 编译器另行处理业务脚本。

`v8.js` 翻译固定的文本节点和 `placeholder`、`title`、`aria-*`、`data-label` 等显示属性。它成对保存原文和译文。异步渲染改变文字后，观察器会翻译新的原文，合并同批更新，并且只写入发生变化的值。`v28.js` 用相同的机制保留原店名，同时翻译固定的支付渠道名称。

把人名、备注和其他用户输入的文字标记为 `data-user-content`。可编辑输入框和指定的账本、账号选择器也会跳过翻译。`sep07.js` 会给输入值的只读副本加上同样的标记，只有原值改变时才更新它。重建节点时要保留这个标记，否则翻译观察器和只读视图可能反复覆盖彼此的内容。

HTML 选项如果没有 `value`，提交时会使用屏幕上显示的文字。翻译标签前，先将原值明确写入 `value`。这样切换语言后，现金类型、固定费用类别等字段仍会提交相同的值。用户自建选项的标识和名称都保留原样。

`translateBackendMessage` 按预先定义的完整句式匹配服务端提示。已知字段名、错误位置和嵌套错误可翻译，用户名、备注、单位和路径保留原文。新增 API 错误句式时，要补上对应词条。整个过程保留原始响应数据和存储键。

`translateAuditSummary(summary, item)` 读取结构化的 `before_payload`、`after_payload` 和修改原因，翻译已知字段名，保留用户填入的值，并用 Added、Removed、Changed、Cleared 标明新增、移除、修改或清空。摘要最多列出 20 项变化，递归遍历也有深度限制。完整对比可查看原始数据。旧响应可能缺少这些字段，此时只翻译能识别的固定表述，含义无法确定的文字（如带分号的备注）保留原文。

除记账和金额测试外，还要运行 `build/qa_english_ui.cjs`、`build/qa_inventory_english.cjs`、`build/test_i18n_backend.cjs` 和 `build/qa_enhanced_analytics.cjs`。打开对话框，切到英文再切回中文，检查 API 错误提示、选项保存值和输入内容的只读副本。用户名称即使恰好命中词典，也应在来回切换后保持原文。界面文字稳定后，翻译不应反复触发更新。

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

| 配置项 | 用途和默认值 |
| --- | --- |
| `DATABASE_URL` | 必填的 PostgreSQL 连接串，供 SQLAlchemy 使用。连接串可能包含凭据。 |
| `SECRET_KEY` | JWT 签名密钥。更换后，旧密钥签发的令牌失效。 |
| `ADMIN_USERNAME`、`ADMIN_PASSWORD` | 创建初始管理员时使用的账号和密码。之后更改配置并重启，不会重置已有账号。 |
| `CORS_ORIGINS` | 允许的来源列表，以英文逗号分隔。同源部署时，浏览器通过页面所在的站点访问 API。 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 普通访问令牌的有效期，单位为分钟。默认 1,440 分钟（24 小时）。 |
| `TEST_LOGIN_ENABLED` | 私有部署请明确设为 `false`。API 未读到此设置时默认为 `true`。仓库提供的配置模板和 Compose 已设为 `false`。 |
| `TEST_USERNAME`、`TEST_DATASET_ID`、`TEST_ACCESS_TOKEN_EXPIRE_MINUTES` | 演示用户名、账本 ID 和令牌有效期。演示账号有单独的访问限制。 |
| `MAX_WORKBOOK_UPLOAD_BYTES` | 工作簿上传大小上限，后端默认 25 MiB。还要核对 Nginx 的请求大小限制。 |
| `PAYMENT_SECRET_ROOT` | 商户文件目录，按账本和门店区分。这些文件保存在数据库及网页目录之外，应单独保护和备份。 |
| `BUSINESS_TIMEZONE`、`WECHAT_TIMEZONE` | 服务端判断业务时间使用的时区及其回退设置。仪表盘判断是否跨月时，按客户端的本地日期计算。 |
| `WECHAT_*` | 微信商户对账单的接入配置。当前 API 启动流程不会运行旧版定时任务。 |
| 原生本机连接配置 | 桌面端监测器读取 `~/.restaurant_finance_sync/config.json`。`RESTAURANT_MAIN_STATUS_PORT` 默认 47650，`RESTAURANT_ASSISTANT_STATUS_PORT` 默认 47651。公开分发包不要包含用户本机的实际配置。 |

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

FIFO 测试会导入桌面模块并运行 Node。可把 Node 加入 `PATH`，也可用 `NODE_BINARY` 指定其绝对路径。桌面源码使用 `fcntl`，运行环境须支持该模块。Qt 测试可在无窗口模式运行，实际操作桌面应用则需要图形会话。测试统一使用隔离的样例数据。部分旧版本号保留在文件名中，用于标识仍需测试的历史问题。

### 浏览器 QA

在独立的工具目录中安装 Playwright 和配套 Chromium。也可以用 `CHROME_EXECUTABLE` 指定本机受支持的 Chrome 或 Chromium 可执行文件。

```bash
npm install --prefix work/browser-qa-tools --save-exact playwright
work/browser-qa-tools/node_modules/.bin/playwright install chromium

for test in qa_web_browser qa_dashboard_charts qa_cost_ring qa_english_ui qa_inventory_english \
  qa_enhanced_analytics qa_analytics_english_advanced; do
  PLAYWRIGHT_MODULE="$PWD/work/browser-qa-tools/node_modules/playwright" \
  QA_OUTPUT_DIR="$PWD/work/qa/$test" node "build/$test.cjs" || exit 1
done
```

将 `QA_OUTPUT_DIR` 设为可写的绝对路径。需要保留报告和截图时，每次运行使用新目录。`PLAYWRIGHT_MODULE` 指向已安装的 Node 模块。可通过 `CHROME_EXECUTABLE` 指定浏览器，通过 `RELEASE_SOURCE_ROOT` 指定另一份待测源码。默认情况下，测试从本地打开仓库中的 `web/index.html`，阻止 HTTP 请求，使用合成数据。记录通过或失败时应启用断言，`QA_DIAGNOSTIC=1` 仅用于排查故障。

`build/qa_web_browser.cjs` 检查采购编辑器、同账本同步和两处预测。`build/qa_dashboard_charts.cjs` 检查五张指标卡和两个图表选择器的金额，并生成中英文的仪表盘、趋势图和预测说明截图。`build/qa_cost_ring.cjs` 分别按手机和电脑宽度检查圆心内容、图例及类别配色。macOS 客户端成功保存工作簿后，会刷新已打开的仪表盘和报表。

修改网页业务脚本后，要用重新生成的文件运行浏览器测试。测试覆盖手机和电脑布局、期间切换与跨月、图表交互、界面翻译，以及用户原文和存储枚举值的保留情况。计算和权限测试也需要一并运行。

### 服务器归档

从 Git 工作区构建。构建器会检查运行文件是否已纳入版本管理，但实际打包的是文件当前的内容，也可能包含尚未提交的改动。打包前先核对 `git status` 和差异。

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
(cd dist && shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256)
```

输出文件需使用新路径。解压后的根目录为 `restaurant-cloud-v1.0.2/`，其中包含 API、静态网页、部署工具、配置示例、`VERSION` 和记录 SHA-256 的 `MANIFEST.json`。数据库和运行凭据留在实际安装环境中。构建后将包内文件与选定的源码版本核对。部署后检查 HTML 构建号和服务器实际返回的文件哈希，健康接口只报告软件版本。操作步骤见[部署指南](DEPLOYMENT.zh-CN.md)。

### macOS App 与打包运行库 QA

在 macOS 上使用 Python 3.12，并通过 `--runtime-app` 指定可信的现有双架构 Python/Qt 应用。运行库需单独取得。构建器替换两个架构的主脚本字节码，保留其他运行库内容，将最低系统版本设为 macOS 15，并执行临时签名（ad hoc）。Apple 公证需另行办理。输出使用新路径。

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

以 `build/qa_packaged_desktop.py` 为入口另建一个离线测试应用。它从待发布应用中加载主脚本字节码，直接测试要分发的那份程序。

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

在兼容的主机上，用 `/usr/bin/arch -x86_64` 再运行一次测试程序，并换一个 `V101_QA_DIR`。在 Apple Silicon 上执行 Intel 架构测试需要 Rosetta。若运行库缺少 `unittest.mock`，可为这次测试设置 `V101_QA_STDLIB`，指向 Python 3.12 标准库目录。`V101` 变量名为兼容历史工具而保留，实际测试的应用由 `V101_PRODUCTION_APP` 指定。测试程序会禁用网络访问，并将用户目录的写入重定向到测试目录。

记录测试结果时写明源码提交、构建号、测试环境和实际结果，并注明哪些检查沿用了之前的结果。评估生产并发需要在接近真实负载的 PostgreSQL 上测试。报告 Intel 架构测试时注明是否使用 Rosetta。验证备份恢复则应在隔离环境中实际恢复。

<a id="recovery"></a>

## 组装 ZIP 或恢复已有实例

需要一起交付源码、文档、已校验的服务器部署包和可选的 macOS 应用时，先把这些内容放入 Git 工作区之外的暂存目录。在暂存根目录放入 `VERSION` 和生成的 `RELEASE_INFO.json`。其中必须提供 `build_revision`，并建议记录源码提交和各产物的哈希，便于接手人核对。服务器 tar 包有独立的构建工具。完整 ZIP 按下列命令生成。

```bash
python -B build/make_complete_package.py \
  --root /absolute/path/to/staging/Release \
  --output "$PWD/dist/complete-release.zip"
python -B build/verify_package.py --root /absolute/path/to/extracted/Release
```

为 ZIP 选择暂存目录之外的新路径。工具会更新 `PACKAGE_MANIFEST.json`，保留 UTF-8 文件名、Unix 权限及内部符号链接，并为 ZIP 生成 `.sha256`。暂存目录应排除 Git 元数据、依赖、虚拟环境和缓存。另选位置解压 ZIP，核对清单、内嵌的服务器包及应用签名。公开包需排除服务器标识、用户本机路径、真实经营记录、运行配置值和凭据。运维备份另存于受保护的位置。

恢复服务所需的资料包括数据库备份、配套的程序版本、运行配置和密钥、外部文件、系统服务与 Nginx 配置，以及数据库角色要求。若实例使用商户功能，还需备份 `PAYMENT_SECRET_ROOT` 下的商户文件。SSH 私钥、数据库密码、JWT 签名密钥和商户密钥用途各异，应分别清点。在隔离环境中演练恢复，再核对表结构、业务记录和关键流程。Excel 交换文件只覆盖业务记录。

部署脚本会保留升级备份，回退应用时保留现有数据库。升级前后两次数据库核验完成之前，应暂停业务写入。如果摘要发生变化，先检查是否有同时写入或清理过期审计记录的情况。恢复较早的数据库备份可能会丢失此后的录入。核验完成前保留备份，之后清理旧副本时先核对具体路径。

<a id="troubleshooting"></a>

## 排查运行中的问题

| 现象 | 怎样排查 |
| --- | --- |
| 页脚显示 v1.0.2，页面仍像旧版 | 读取服务器实际返回的 HTML 构建号，按其中的资源地址下载文件，对照清单核对哈希，并确认正在提供服务的进程及网页根目录。 |
| 英文界面仍出现中文 | 先确认是固定文案还是用户原文。固定文案应检查当前语言、翻译词典，以及初次渲染后才打开的对话框。 |
| 毛利润减固定成本与净利润不符 | 核对日结水电等费用及归在“其他”的支出。分别查看按月保存的固定支出和逐笔付款，避免重复计算。 |
| 月初第一天没有日均值 | 截至昨天已过的自然天数为零。此时可以已有实际净利润，日均值则要等经过一个自然日后才能计算。 |
| 以前月份的预测卡显示实际净利润 | 检查客户端的本地日期。从次月 1 日起，该卡改用已结束月份的实际净利润。 |
| 切换账本后余额跳变 | 追踪每个请求发出时的账本和现金数据版本，再核对共享缓存及各响应到达的先后顺序。 |
| 导入金额与源文件不符 | 读取原始 XML 或 JSON 中的十进制文本，追踪金额转换过程，检查是逐行舍入还是合计后舍入。 |
| FIFO 成本相差几分钱 | 检查每批的累计分摊额和最后一次出库分摊的尾数，确认已知零单价与未知单价得到区分。 |
| 横坐标标签重叠 | 按实际字体和容器宽度测量文字，为末端刻度和换行标签留足空间，再检查窗口变宽或变窄时是否重新绘制。 |
| 桌面窗口太宽 | 按出现问题的窗口尺寸检查控件最小宽度、控制行换行、滚动区域及 Matplotlib 布局。 |
| 工作簿上传失败 | 先检查 Nginx 请求大小限制，再核对后端上限、内容类型、工作簿结构、目标账本和用户权限。 |
| 部署核验发现数据库摘要变化 | 在备份仍可用时比较升级前后的记录，检查期间是否有获准的业务写入或审计记录到期。 |
| 重新构建的 macOS 应用仍表现得像旧版 | 先确认实际启动的可执行文件，再对照最终源码检查包内的主脚本字节码，最后核对签名及实际运行的架构。 |

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

完整 ZIP 或解压目录也按相同步骤扫描。逐项核对工具列出的工作簿、数据库或配置文件。分享前再检查截图和日志。扫描器会统计图片数量，并匹配已知标识及私钥特征。仅出现在图片里的文字需要单独检查。凭据、真实数据和恢复备份存放在私有位置。测试报告随对应的版本或 CI 运行记录保存。
