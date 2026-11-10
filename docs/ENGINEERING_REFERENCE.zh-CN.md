# 工程技术详解 — v1.0.2

日期：**2026 Nov 10**。构建修订：**20261110-analytics-english-final**。本文说明仓库根目录的源码（对应 ZIP 的 `Nov10/source/`）；实际部署状态见 [发布状态](RELEASE_STATUS_v1.0.2.md)。[English](ENGINEERING_REFERENCE.md) · [根目录交接](../项目交接说明.md)。

## 1. 产品与交付对象的边界

系统包含餐饮收入、采购、日常费用、月固定支出、现金余额、菜品耗用、库存、多账本、账号权限、变更历史和 Excel 交换。同一本账支持 A/B 店收入渠道；店名、商品名等是用户数据，账本是独立的权限和持久化边界。

三个执行部分是静态网页、PostgreSQL 支撑的 FastAPI，以及支持本地 Excel/云同步的 PySide6 macOS 程序。服务器 tar 只包含 API 和网页运行文件；外层完整 ZIP 还包括原生运行库、全部源码、文档和核验材料。两个 ZIP 软件版本相同，只有 For自己包增加 `私人运维资料/`。

| 对象 | 它能证明什么 | 不能由此推断 |
| --- | --- | --- |
| `VERSION` / API `v1.0.2` | 软件兼容版本标签。 | 两个同版本构建拥有相同功能/文件。 |
| HTML build revision / `RELEASE_INFO.json` | 本次同日修订的身份。 | 线上已经部署该修订。 |
| 仓库根目录（ZIP 的 `source/`） | 当前可编辑的权威源码。 | 历史 Git 提交含有本次所有改动。 |
| 服务器 `MANIFEST.json` | 运行包文件的 SHA-256。 | 部署中真实业务记录没有变化。 |
| `PACKAGE_MANIFEST.json` 与 ZIP `.sha256` | 全包文件、权限/符号链接，以及 ZIP 字节。 | 私人快照无需核对依赖即可恢复。 |
| 部署前后证据 | 特定时间的服务器状态和比较结果。 | 老备份现在仍存在，或后来改动也经过验证。 |

这里的管理记账视图不自动等同于法定报表、支付成功凭证或不可变的月结。用户明确保留已有毛利润和其他支出分类。

## 2. 源码拓扑与网页载入顺序

网页使用原生 JavaScript，而不是组件框架。一个 HTML 内有多个页面面板，共用 `state`，再叠加历史功能模块和后加载的封装/覆盖。`web/index.html` 的脚本顺序有实际含义：精确金额必须先于业务脚本，当前 workbench/chart/dashboard/analytics 层后于旧基础模块。定位问题须找最后生效的实现，不能只在 `app.js` 里 grep 到一个同名函数就修改。

| 路径 | 职责与修改注意 |
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
| `build/web-exact-source/analytics-oct30.js`、`web/analytics-oct30.css` | 统计状态、经营/费用/客流分析、费用口径、来源表格及统计工作区。 |
| `desktop/restaurant_cost_manager.py` | 原生控件、本地与云端数据、财务和同步；大型单文件，应按符号/类定位，不依赖旧行号。 |
| `backend/app/main.py` | API 路由、记录策略、权限、现金汇总、启动兼容和审计维护。 |
| `backend/app/models.py`、`database.py`、`security.py` | 表结构、精确 JSON 保存、会话、JWT 和密码。 |
| `backend/app/money.py`、`money_routes.py`、`excel_io.py` | 金额输入/序列化、HTTP 原始 JSON 精确解析和工作簿边界。 |
| `backend/app/inventory_balance.py`、`inventory_validation.py` | 数量重放、事务时库存/单据金额检查；不是第三套 FIFO 成本引擎。 |
| `backend/app/name_corrections.py`、`ingredient_corrections.py` | 更名预览、关联改写、盘点调整、过期状态校验及持久幂等回执。 |
| `backend/app/store_settings.py`、`wechat_pay.py`、`wechat_sync.py` | 店铺配置和保留的微信账单代码；当前启动不会开启旧自动同步。 |

网页业务源码位于 `build/web-exact-source/`。`node build/compile_exact_web.cjs` 用 Acorn 解析后生成对应 `web/*.js`，不能只改生成文件。HTML、CSS、`money.js`、`workbench.js`、本地化资源及许可证直接维护。新增文件先看编译器清单，确认是否应编译。浏览器运行不需要 Node、Acorn、打包器或 CDN。

## 3. 数据模型与身份

生产数据库使用 PostgreSQL 和 JSONB。测试中的 SQLite 适配不代表支持 SQLite 生产部署。初始化是 `create_all` 加少量明确兼容补丁，不是通用数据库迁移框架。

| 表 | 身份和用途 | 不变量 |
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

## 4. 请求生命周期、并发与权限

网页使用同源 `/api/v1`。Nginx 提供静态文件并保留 `/api/` 前缀反向代理。单纯 HTTP 静态文件服务只能显示登录页，不能完成认证和记账。登录返回 bearer JWT；后端重新读取账号并检查启用状态。角色为 `viewer`、`entry`、`editor`、`admin`。管理员有明确跨账本权限；其他用户需要成员关系。临时授权还限定日期和时间。

一次保存的链路是：捕获账本/登录/上下文 generation → 保留编辑基线和无关字段 → 使用该账本设备 → 规范化已知金额并计算 checksum → 带 expected version 发写请求 → 服务端事务校验权限/时钟/库存 → 提交版本、序号和审计 → 仅在当前界面仍匹配捕获上下文时应用响应。A→B→A 也应使旧异步请求失效，不能只比对最终账本 ID。新的保存成功后更新 revision，阻止更早刷新覆盖缓存。

现金有独立服务端结果和 revision，可能在日记录未变时更新。主数据相同不代表可以跳过现金响应。每次现金加载都核对账本和 revision，再更新共用状态；不要添加另一份容易过期的独立现金缓存。

录入角色使用服务端字段/明细时钟，主要是 30 分钟更正、12 小时明细新增，以及既有业务日期/收入截止限制。精确政策以 `_effective_record_role`、`_entry_timing_updates` 等函数及测试为准。不能只用整份文档的 `updated_at`，也不能因改备注或保存等价数字文本而重开窗口。

库存写入先锁账本，再依据当前记录重放数量并检查新短缺；expected version 拒绝过期单据。品名更正先预览影响集合，确认当前状态后在单事务处理所有关联写入并保存持久回执；不能拆成客户端多次无关联 PUT。

审计采用 366 天保留期并有管理员维护接口。启动可清理过期审计，因此部署对比须区分允许的审计保留变化与业务记录变化。

## 5. 金额、利润与库存合同

同时阅读 `build/MONEY_CONTRACT.txt`、`build/FIFO_CONTRACT.md` 和 `backend/MONEY_BACKEND.txt`。已知新/改金额在 API 边界写十进制字符串，计算用 Python `Decimal` 或浏览器 `Exact`。金额两位、单价六位、ROUND_HALF_UP。拒绝非法文本、bool、NaN、Infinity 和超限单笔输入；已知零价与未知价不同。金额单笔限 ±999999999999.99，单价限 ±999999999999.999999；合法派生汇总不按单笔限制处理。

旧 numeric JSON 读取保留原十进制词法；需要时从 OOXML 原始数值读取。只规范已知财务路径，不能递归把任意 metadata 都转金额。绘图坐标可以在最终边界转 float，不能用于财务持久化。Exact 的格式化不能在中间运算中暗中调用 Number。

五项主页指标完整定义见根目录交接。一个容易误改的区别是：当前月日均收入/毛利截至昨日，除以已过自然天数；实际月净利包含今日已录收支和整月已保存固定支出。日均净利使用该实际净利除以已过自然天数；两处净利率用实际月收入。月初没有已过天数，日均不可用。已结束月按整月天数，下个月 1 日起预测卡显示实际净利；未来月不可用。独立本地日期检查即使数据不变也刷新，不写入、不冻结月结结果。

| 项目 | 必须保持的含义 |
| --- | --- |
| 毛利润 | 收入 − 食材 − 佐料 − 手续费。 |
| 变动成本 | 食材 + 佐料 + 日结水电 + 其他 + 手续费。 |
| 月固定支出 | 已保存人工 + 房租/物业 + 实付水/电/煤气 + 其他固定。 |
| 月净利润 | 收入 − 变动成本 − 整月固定支出。 |
| 当前月预测 | 截至昨日的日均收入 × 本月天数 − 上月总成本。 |
| 环比 | `(本期 − 上期) / abs(上期) × 100`；上期零或缺失须说明。 |
| 余额强制修改 | 某日实际余额设定，不是营业收入/支出。 |
| 固定费用比较 | 月保存汇总与逐笔日期支出为两种核对口径，不能相加。 |

库存身份由类别/名称/单位组成，不暗中换算单位。FIFO 保存批次原数量、原金额、原单价和剩余量。每次出库成本为累计分摊差：`round(原批次金额 × 累计耗用量 / 原数量, 2) − 此前已分摊金额`。批次完全耗尽时吃掉全部余分。剩余价值=原入账价值−已分摊，不是剩余数量×显示单价。未知价格数量必须明确显示。

采购支出和 FIFO 耗用成本回答不同问题。月度经营利润继续采用既有采购/费用口径；本次没有授权重新分类包装、耗材或话费。所以毛利减固定支出仍可能要再扣日结水电/其他才能等于净利。

## 6. 英文显示与用户内容

网页英文模式覆盖固定导航、标签、占位符、对话框、验证/状态提示、报表/图例、固定分类、角色及动态系统文字。不能翻译用户输入：账本、店铺、商品、菜品、自定义收入项目、备注、人名、供应商和自定义单位须保留。中文存储字段与枚举仍是兼容键，不因为显示英文而迁移。原生 App 本版仍是中文，没有原生英文模式。

扩展翻译须遵循：

1. 在渲染边界给固定文字中英文映射，存储键独立于显示标签。
2. “店名＋支付渠道”组合须保留店名，只翻译已知渠道后缀；写 HTML 前转义用户内容。
3. 动态错误翻译固定句式，插入的用户内容分别处理；不对所有中文、记录 JSON、输入值或审计 payload 全量替换。
4. 切语言重新渲染当前和以后打开的界面，但不能提交表单、丢草稿、换日期/账本或改金额。
5. 检查所有页面、按角色可见区域、弹窗、placeholder/title/aria 文本，不能只看侧栏。
6. 用恰好与翻译字典相同的中文商品名做合成测试，抓出误翻译用户值；切语言后出站保存 payload 应不变。

英文显示不会把人民币变美元，也不会换算币种。CNY 等英文单位只是显示变化。英文模式的 `input[type=month]` 由 `web/i18n-controls.js` 显示 ISO `YYYY-MM` 覆盖层，应用字段不再露出操作系统本地化的“年/月”后缀；原生 input 的 `.value`、验证、事件和日历选择功能保留。日历弹出层本身及浏览器外壳仍由浏览器/操作系统控制，不宣称由应用翻译。


### 本地化运行架构

四个直接维护的静态字典在 `app.js`/`pro.js` 之后、**`v8.js` 构造显示映射之前**载入：

| 文件 | 范围 |
| --- | --- |
| `web/i18n-en.js` | 共用标签、系统消息模板、`systemMessage` 及 alert/confirm/prompt 显示。 |
| `web/i18n-inventory-en.js` | 库存工作区、入/出库、盘点、批次和品名更正弹窗。 |
| `web/i18n-backend-en.js` | 已知 API 错误/验证/状态模板、规范字段显示名及结构化审计摘要。 |
| `web/i18n-extra-en.js` | 其余历史流水/报表/现金、选择器、账号、临时权限和 Excel 文案。 |

四字典之后、`v8.js` 之前还载入 `web/i18n-controls.js` 月份显示适配层。它只改变显示格式，不改变规范 `YYYY-MM` 值或输入行为。

字典扩充 `SYSTEM_EN` / `SYSTEM_EN_PATTERNS`；在 `v8.js` 已构造映射之后才增加字典，不等同于正确载入顺序。它们直接维护、进入服务器清单，使用当前修订的缓存参数；不属于 Exact 金额编译器的业务源输入集。

`v8.js` 翻译固定文字节点及 placeholder/title/aria/data-label 等显示属性，以 source/output 成对元数据保存原文和输出。异步渲染真的改了节点时，以新内容为原文，不复用过期句子。排队观察器合并更新，只有值不同时才写。`v28.js` 店名替换使用配合的原文/输出元数据，把固定支付渠道文字与实际店名分开处理。不要重新加入反复写相同值、把自己的输出重复翻译的观察器。

用户来源的单元格、名字、说明和其他不透明显示用 `data-user-content` 标记；输入框以及指定账本/账号选择器也明确排除。`sep07.js` 只读投影同样标为用户内容，仅当原显示值改变才更新。没有这个边界时，只读镜像和翻译观察器可能互相覆盖形成循环，或翻译用户中文值。重建节点时必须保留标记。

没有显式 `value` 的 HTML option 默认以显示文本作为提交值。翻译标签之前，先把规范原值固化到 `value` 属性，保证固定费用类别、现金类型等枚举在切语言后保存值不变。用户选择项保留原标识与文本。

`translateBackendMessage` 只匹配锚定的已知服务端模板；明确标注的字段/位置/嵌套错误参数可翻译，用户名、备注、单位、路径和任意插入值保持不透明。API 存储键和响应数据不变。新后端错误须同步字典，不能把任何服务端字符串中的中文无差别替换。

`translateAuditSummary(summary, item)` 使用结构化 `before_payload`、`after_payload` 和原因，生成英文 Added/Removed/Changed/Cleared 框架与已知字段名，保留实际值；不按分号猜测用户备注。显示摘要有上限（最多 20 项变化并有深度保护），不能代替完整前后记录。旧响应没有结构化内容时，可翻译已识别的固定模板，但不猜测改写含糊、未转义的用户文本。显示翻译不改审计历史。

相关回归入口为 `build/qa_english_ui.cjs`、`build/qa_inventory_english.cjs`、`build/test_i18n_backend.cjs`、`build/qa_enhanced_analytics.cjs` 及既有业务/金额测试。验收包括中英文往返、动态弹窗、错误路径、option 值不变、用户名字恰好等于字典词、只读镜像以及观察器不循环。

## 7. 统计解释与图表合同

统计按所选年/月、指标、日期/筛选上下文组织经营、费用和客流视角。来源明细连通汇总与原记录；固定支出明确区分月保存值和逐笔日期值。CSV 对应当前筛选/排序范围，固定表头随界面语言，用户值原样导出。本次最终展现功能见 Nov10 CHANGELOG 和更新说明。

图表保留全部点，仅选择能容纳的轴标签。渲染器测量文本、结合年份背景缩写日期/月、预留首尾刻度、类别换行，容器变化后重新排布。无记录是空缺，不伪造成零收入日。负净利保持在零轴下方及原符号。悬停、触摸、焦点、方向键、Home/End 查看完整日期/类别和精确金额。表格合计和图表共享计算来源，样式不能引入另一套财务公式。

专业化的含义是明确期间/口径、连贯选择、可比较摘要、趋势/类别/来源视图，以及清晰表格和空状态。不要添加没有数据支撑的“AI 预测”、虚构记录、误导评价或概率。更精致的图不等于改变会计口径。


### 本次最终统计工作流

计算口径/环比条明确所选范围与上月关系。三个观察卡呈现有记录日期覆盖、最大费用，以及视角相关指标：有记录日中的盈利天数、月固定保存值减逐笔值的差额，或最忙客流日/客流覆盖。指标趋势支持折线和柱状，显示精确均值/最小/最大及观察数量。明细按列排序、保留金额符号，合计覆盖跨页全部筛选结果，CSV 遵循筛选/排序。这些是透明的数据观察，不是新增预测或财务分类。

原生中文“更多统计”提供所选范围/来源数提示、可换行筛选、可折叠采购/耗用/方法区，以及随宽度改变的一列或两列图表。混选金额/人数/比率时提示；表格隐藏时也可导出当前筛选，空数据禁用导出。财务和存储合同不变。

## 8. 配置与运行行为

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

`.env.example` 用于 Compose，`backend/.env.example` 用于直接启动 API，两者不同。不能把私人 runtime.env 覆盖成示例。Compose 按 YAML 使用 PostgreSQL 16、Nginx 1.28，数据库、支付密钥、恢复资料分卷，演示网页端口默认只绑 loopback。普通升级不能执行 `docker compose down -v`，因为卷保存持久数据。

后端启动建立缺失表、执行明确的 entry-timing 兼容列添加、清理过期审计、确保初始管理员并处理旧/演示成员关系。它不会执行任意迁移、批量修复历史金额或开启旧微信定时任务。系统不包含支付下单/退款/清算网关、银行流水接入、高可用或集中监控服务。

## 9. 构建与验收顺序

按本包源码和根目录/更新说明的命令操作，依赖工具放分发目录外。源码环境用 Python 3.12、固定依赖与 Acorn lockfile；复用的 App 运行库可有不同补丁版本，由 App 验证记录确认。不能把新装源码依赖版本当作打包运行库版本。

1. 核对来源和包，分别准备无隐私/For自己暂存树。
2. 隔离安装 `build/test-requirements.txt`、需要的桌面依赖及 `npm ci --prefix build/js-transform`。
3. 修改真正业务源与直接静态资源，执行 `node build/compile_exact_web.cjs`。
4. 跑精确金额、FIFO、既有网页回归、本次仪表盘/图表/英文/统计检查，以及必要 API/原生测试。
5. 在真实浏览器用合成数据、阻断 HTTP，检查手机到电脑的中英文布局/交互、用户内容保留、图表边界和表格滚动。
6. 用 `build/rebuild_macos_app.py` 从最终原生源码生成新的主字节码，核对源码对应、权限、双架构和签名；对实际候选 App 跑已声明架构的隔离 QA，不能只测试源导入。
7. `build/make_release.py` 从明确 Git 跟踪的运行文件构建新路径服务器 tar，记录其清单和哈希。
8. 完成当前修订证据与双语文档，区分本次重跑、继承结果和局限；不能照抄旧通过数作为新验收。
9. 从两个明确暂存目录创建两个外层 ZIP，私密资料不进 App/tar。所有文件最终确定后再生成清单与 ZIP hash。
10. 两包分别解压到新目录，检查内容、权限、符号链接、App 签名和服务器清单；再次扫描解压树及嵌套归档的隐私。

已有入口：`web/test_v1_0_1_regressions.js`、`web/test_v1_0_2_dashboard.js`、`web/test_v1_0_2_charts.js`、`build/test_exact_web.cjs`、`build/test_fifo_contract.py`、`build/test_v1_0_1_desktop*.py`、`build/test_v1_0_2_desktop*.py`、`build/qa_web_browser.cjs`、`build/qa_packaged_desktop.py`、`build/test_deployment_cache_revision.py` 及 `backend/tests/`。新增英文/统计测试路径写在本次证据和日志中。

验收应检查用户数据和权限保持，不只截图。测试不能指向私人 dump 或真实服务器。SQLite 测试不证明生产 PostgreSQL 并发负载；Rosetta 下 x86_64 执行不等于实体 Intel 测试；pg_dump 可读也不等于完整恢复演练通过。

## 10. 分包、私人快照与恢复

无隐私包排除原公网 IP/主机名、个人本机路径/聊天链接、实际账户/账本信息、数据库、环境值、密码、私钥和用户内容。合成夹具可有中文测试名字和虚构数值。私密包增加用户授权的 `私人运维资料/` 清单、提供的 SSH 凭据、连接信息及记账系统快照。具体范围/时间由该目录清单说明，本文不虚构已收集全部材料。

私密文件不由网页提供，不编译进 App。SSH 私钥、数据库密码、JWT 密钥和商户签名密钥是不同凭据，不能混用。商户文件可能在 PostgreSQL 之外的 `PAYMENT_SECRET_ROOT`，授权完整恢复时须单独考虑；不能因为同一台机器就顺便复制其他服务文件。

恢复交接需要 dump、对应程序/配置版本、运行密钥、相关外部文件、systemd/Nginx 布局及数据库/角色假设。先在隔离环境恢复、核查 schema/数量/关键功能，再单独验证凭据与配置。程序回退与数据库恢复是不同操作，不能自动把升级前快照覆盖较新的生产数据库。

发布验证时保留新的当前备份；若之后清理，应删除事先审核清单内的旧应用备份。部署脚本本身不删备份。历史路径是当时证据，不是删除指令。附件和旧审查说明提供背景，不构成新的生产修改授权。

## 11. 排障索引

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

## 12. 公开 HTTP 路由清单

以下由交付源码中的路由装饰器提取。`record_key:path` 可以含路径样字符，客户端须正确 URL 编码；一些旧别名刻意保留。具体请求/响应和权限以模型与路由依赖为准，有路由不等于有权调用。运行中 `/openapi.json` 只说明该运行构建，可能与过期本地文件不同。

| Method | Route | Source function |
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


## 13. 历史与私人资料放在哪里

两个 ZIP 共用的核验资料只有 `docs/acceptance/Nov10Final/` 中本次合成/去私人信息的记录。无隐私包刻意不含修复前审查、旧 Nov07/Nov10 日志截图以及旧版本说明 01–05，因为它们可能带原本机、服务器或业务信息。For自己包把这些放在 `私人运维资料/历史开发证据/`；它们是历史背景，不是当前权威源码或验收。两包都保留 CHANGELOG 历史段落，旧段落对“随包文件”的描述只说明当时交付，本次实际目录以当前清单为准。

私人目录另提供 `Admin.pem`、`known_hosts`、`accounting-server-private.tar.gz` 及私密运维说明/清单。服务器快照只读采集本记账系统的 PostgreSQL、运行/服务配置和相关 payment-secret 文件，精确范围与时间由其清单记录，不打包无关服务。使用凭据或计划恢复前先读私密运维说明；共用技术说明无需包含真实主机身份或凭据值。


## 14. 只读分发包隐私检查

`build/audit_distribution_privacy.py` 可检查解压树、ZIP、tar 或 macOS App，不执行归档内代码。真实私人标识必须放在**分发目录之外**的文件中（JSON 字符串数组或 UTF-8 每行一项）；工具源码不写原服务器标识，也不输出密钥片段。它检查 UTF-8/UTF-16 字节、完整私钥标记、归档条目和链接边界，并解开双架构 Mach-O 中 PyInstaller CArchive/PYZ 内容检查。`build/test_distribution_privacy.py` 提供合成扫描回归。

在解压后的 `Nov10/` 根目录检查无隐私包：

```bash
python3 build/audit_distribution_privacy.py \
  /absolute/path/to/无隐私记账系统Nov10V1.0.2.zip \
  --forbid-file /absolute/private/identifiers.txt \
  --report /absolute/path/to/clean-privacy-report.json
```

For自己包刻意包含凭据和数据库快照，不要求它通过无隐私包的密钥排除规则；应核对独立私人目录清单，并确认这些资料没有进入共用 App/服务器 tar 或无隐私 ZIP。扫描器只计数图片，不做 OCR 或内容分类。工作簿、数据库和配置候选仍需审查，签名扫描也不能证明不存在任何未知秘密。因此旧截图/日志/审查和版本说明 01–05 仅放本人历史归档，共用核验使用当前合成夹具。
