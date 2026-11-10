"use strict";
/* Backend presentation translations only. Storage/schema/error codes are unchanged.
 * Templates are anchored. Captured user names, units, paths and values remain opaque;
 * only declared backend-owned label/location/nested-message slots are translated.
 * Load after i18n-en.js and before UI modules. See build/test_i18n_backend.cjs.
 */
globalThis.BACKEND_EN_MESSAGE_DEFINITIONS = [
  {
    "zh": "采购 JSON 明细必须是对象数组，已取消合并。",
    "en": "Purchase JSON details must be an array of objects. Merge canceled.",
    "source": "excel_io.py:305"
  },
  {
    "zh": "文件不是有效的 .xlsx（ZIP）工作簿。",
    "en": "The file is not a valid .xlsx (ZIP) workbook.",
    "source": "excel_io.py:480"
  },
  {
    "zh": "工作表「{0}」缺少表头。",
    "en": "Worksheet “{0}” has no header row.",
    "source": "excel_io.py:565"
  },
  {
    "zh": "工作表「{0}」存在重复列名。",
    "en": "Worksheet “{0}” contains duplicate column names.",
    "source": "excel_io.py:578"
  },
  {
    "zh": "工作表「{0}」缺少列：{1}。",
    "en": "Worksheet “{0}” is missing columns: {1}.",
    "source": "excel_io.py:582",
    "parameters": {
      "1": "labels"
    }
  },
  {
    "zh": "{0} 的 dataset_id 无效。",
    "en": "{0}: invalid dataset_id.",
    "source": "excel_io.py:610",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的日期无效，应为 YYYY-MM-DD。",
    "en": "{0}: invalid date; expected YYYY-MM-DD.",
    "source": "excel_io.py:622",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的月份无效，应为 YYYY-MM。",
    "en": "{0}: invalid month; expected YYYY-MM.",
    "source": "excel_io.py:637",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的月份无效：{1}。",
    "en": "{0}: invalid month: {1}.",
    "source": "excel_io.py:640",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的记录类型无效。",
    "en": "{0}: invalid record type.",
    "source": "excel_io.py:647",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的 payload_json 为空。",
    "en": "{0}: payload_json is empty.",
    "source": "excel_io.py:653",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的 payload_json 超过 Excel 单元格 32,767 字符上限。",
    "en": "{0}: payload_json exceeds Excel's 32,767-character cell limit.",
    "source": "excel_io.py:656",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的 payload_json 过大。",
    "en": "{0}: payload_json is too large.",
    "source": "excel_io.py:659",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "不允许的数值 {0}",
    "en": "Unsupported numeric value: {0}",
    "source": "excel_io.py:662"
  },
  {
    "zh": "{0} 的 payload_json 必须是 JSON 对象。",
    "en": "{0}: payload_json must be a JSON object.",
    "source": "excel_io.py:671",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "year 必须在 2000 至 2200 之间。",
    "en": "year must be between 2000 and 2200.",
    "source": "excel_io.py:1228"
  },
  {
    "zh": "云端记录 {0}/{1} 的 payload 不是对象。",
    "en": "Cloud record {0}/{1}: payload must be an object.",
    "source": "excel_io.py:1013"
  },
  {
    "zh": "记录 {0} 的 {1} 不是数组。",
    "en": "Record {0}: {1} must be an array.",
    "source": "excel_io.py:1196",
    "parameters": {
      "1": "label"
    }
  },
  {
    "zh": "采购 JSON 明细无法识别，已取消合并。",
    "en": "Purchase JSON details could not be parsed. Merge canceled.",
    "source": "excel_io.py:303"
  },
  {
    "zh": "记录内容不能转换为有效 JSON：{0}",
    "en": "Record contents cannot be converted to valid JSON: {0}",
    "source": "excel_io.py:471",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "文件不是有效的 .xlsx 工作簿。",
    "en": "The file is not a valid .xlsx workbook.",
    "source": "excel_io.py:501"
  },
  {
    "zh": "无法读取 Excel 工作簿：{0}",
    "en": "Unable to read the Excel workbook: {0}",
    "source": "excel_io.py:548",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "工作簿记录数超过安全上限。",
    "en": "The workbook exceeds the record-count limit.",
    "source": "excel_io.py:603"
  },
  {
    "zh": "{0} 的日期无效：{1}。",
    "en": "{0}: invalid date: {1}.",
    "source": "excel_io.py:627",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的 payload_json 已损坏：{1}",
    "en": "{0}: payload_json is damaged: {1}",
    "source": "excel_io.py:669",
    "parameters": {
      "0": "location",
      "1": "message"
    }
  },
  {
    "zh": "这不是有效的内部 Excel，缺少工作表：{0}。",
    "en": "This is not a valid internal workbook. Missing worksheets: {0}.",
    "source": "excel_io.py:682"
  },
  {
    "zh": "内部 Excel 的 __meta 同时包含多套 dataset_id。",
    "en": "The internal workbook's __meta contains multiple dataset_id values.",
    "source": "excel_io.py:698"
  },
  {
    "zh": "内部 Excel 的 source_order 必须为全体记录提供不重复的来源顺序。",
    "en": "The internal workbook must provide a unique source_order for every record.",
    "source": "excel_io.py:754"
  },
  {
    "zh": "内部 Excel 同时包含多套 dataset_id，不能自动合并。",
    "en": "The internal workbook contains multiple dataset_id values and cannot be merged automatically.",
    "source": "excel_io.py:756"
  },
  {
    "zh": "内部 Excel 的 dataset_id 不一致。",
    "en": "The internal workbook contains inconsistent dataset_id values.",
    "source": "excel_io.py:764"
  },
  {
    "zh": "{0} 金额无效：{1}",
    "en": "{0}: invalid amount: {1}",
    "source": "excel_io.py:1280",
    "parameters": {
      "0": "location",
      "1": "message"
    }
  },
  {
    "zh": "用户 Excel 将整体替换所选年份，为防止误删，必须包含完整六张工作表；当前缺少：{0}。",
    "en": "A user workbook replaces the entire selected year. All six worksheets are required to prevent unintended deletion. Missing: {0}.",
    "source": "excel_io.py:824"
  },
  {
    "zh": "用户 Excel 属于 {0} 年，不能按 {1} 年导入。",
    "en": "This user workbook belongs to {0}; it cannot be imported as {1}.",
    "source": "excel_io.py:865"
  },
  {
    "zh": "用户 Excel 属于账本 {0}，不能替换当前账本 {1}。",
    "en": "This user workbook belongs to ledger {0}; it cannot replace the current ledger {1}.",
    "source": "excel_io.py:873"
  },
  {
    "zh": "用户 Excel 的总记录数超过安全上限。",
    "en": "The user workbook exceeds the total record-count limit.",
    "source": "excel_io.py:920"
  },
  {
    "zh": "工作簿包含 {0} 年的数据；整年替换文件只能包含 {1} 年。",
    "en": "The workbook contains data for {0}; a whole-year replacement may contain only {1}.",
    "source": "excel_io.py:938"
  },
  {
    "zh": "{0} 超过 Excel 单元格 32,767 字符上限。",
    "en": "{0}: exceeds Excel's 32,767-character cell limit.",
    "source": "excel_io.py:1030",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 包含 Excel 不允许的控制字符。",
    "en": "{0}: contains control characters not allowed by Excel.",
    "source": "excel_io.py:1032",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "记录 {0}/{1} 的 JSON 超过 Excel 单元格 32,767 字符上限。",
    "en": "Record {0}/{1}: JSON exceeds Excel's 32,767-character cell limit.",
    "source": "excel_io.py:1113"
  },
  {
    "zh": "记录 {0} 的 {1} 含有非对象行。",
    "en": "Record {0}: {1} contains a row that is not an object.",
    "source": "excel_io.py:1200",
    "parameters": {
      "1": "label"
    }
  },
  {
    "zh": "工作簿内部文件数量异常，已拒绝读取。",
    "en": "The workbook contains too many internal files and was rejected.",
    "source": "excel_io.py:485"
  },
  {
    "zh": "文件缺少 Excel 工作簿结构。",
    "en": "The file is missing the Excel workbook structure.",
    "source": "excel_io.py:499"
  },
  {
    "zh": "内部 Excel 有业务记录，但 __meta 中没有 dataset_id。",
    "en": "The internal workbook contains business records but __meta has no dataset_id.",
    "source": "excel_io.py:759"
  },
  {
    "zh": "内部记录的 dataset_id 与 __meta 不一致。",
    "en": "Internal records have a dataset_id that does not match __meta.",
    "source": "excel_io.py:761"
  },
  {
    "zh": "另有 {0} 条记录的 SHA-256 已重算。",
    "en": "SHA-256 was recalculated for {0} additional records.",
    "source": "excel_io.py:766"
  },
  {
    "zh": "工作簿包含不安全的内部路径。",
    "en": "The workbook contains an unsafe internal path.",
    "source": "excel_io.py:490"
  },
  {
    "zh": "工作簿解压后过大，已拒绝读取。",
    "en": "The workbook is too large when decompressed and was rejected.",
    "source": "excel_io.py:493"
  },
  {
    "zh": "不接受包含宏或嵌入对象的工作簿。",
    "en": "Workbooks containing macros or embedded objects are not accepted.",
    "source": "excel_io.py:496"
  },
  {
    "zh": "内部 Excel 存在重复记录：{0}/{1}。",
    "en": "The internal workbook contains a duplicate record: {0}/{1}.",
    "source": "excel_io.py:729"
  },
  {
    "zh": "内部 Excel 的记录数超过安全上限。",
    "en": "The internal workbook exceeds the record-count limit.",
    "source": "excel_io.py:750"
  },
  {
    "zh": "{0} 的词条名称为空。",
    "en": "{0}: the dictionary entry name is empty.",
    "source": "excel_io.py:912",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "{0} 的类别名称为空。",
    "en": "{0}: the category name is empty.",
    "source": "excel_io.py:916",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "混合采购明细存在无法识别的文本，已取消合并；请先核对明细格式。",
    "en": "Mixed purchase details contain unrecognized text. Merge canceled; check the detail format first.",
    "source": "excel_io.py:325"
  },
  {
    "zh": "{0} 的 source_order 必须为正整数。",
    "en": "{0}: source_order must be a positive integer.",
    "source": "excel_io.py:744",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "工作表「{0}」{1} 含有公式；请先复制并粘贴为数值后再上传。",
    "en": "Worksheet “{0}”, {1}, contains a formula. Copy and paste it as a value before uploading.",
    "source": "excel_io.py:837"
  },
  {
    "zh": "{0} 的 SHA-256 已按实际内容重算。",
    "en": "{0}: SHA-256 was recalculated from the actual contents.",
    "source": "excel_io.py:740",
    "parameters": {
      "0": "location"
    }
  },
  {
    "zh": "__app_meta 第 {0} 行的 user_year 无效。",
    "en": "__app_meta row {0}: invalid user_year.",
    "source": "excel_io.py:854"
  },
  {
    "zh": "无法定位 JSON 更名字段",
    "en": "Unable to locate the JSON field to rename",
    "source": "ingredient_corrections.py:100"
  },
  {
    "zh": "JSON 字段类型发生改变",
    "en": "A JSON field's type changed",
    "source": "ingredient_corrections.py:42"
  },
  {
    "zh": "先将原品名和目标品名库存按单位相加，再按本次实际数量新增盘点；盘盈单价未填时记为待定价。",
    "en": "First combine the original and target item balances by unit, then add a stocktake using the entered actual quantities. Stock gains without a unit price remain unpriced.",
    "source": "ingredient_corrections.py:545"
  },
  {
    "zh": "新旧品名相同，无需更正。",
    "en": "The original and new item names are identical; no correction is needed.",
    "source": "ingredient_corrections.py:562"
  },
  {
    "zh": "没有找到需要更正的精确品名。",
    "en": "No exact matching item name was found to correct.",
    "source": "ingredient_corrections.py:551"
  },
  {
    "zh": "JSON 明细行数发生改变",
    "en": "The number of JSON detail rows changed",
    "source": "ingredient_corrections.py:46"
  },
  {
    "zh": "匹配品名的 JSON 字段重复或格式不明确",
    "en": "The matching item-name field is duplicated or ambiguous in JSON",
    "source": "ingredient_corrections.py:94"
  },
  {
    "zh": "库存原始记录格式异常，请先核对。",
    "en": "The original inventory record has an invalid format. Check it first.",
    "source": "ingredient_corrections.py:130"
  },
  {
    "zh": "食材词典格式异常，请先核对。",
    "en": "The ingredient dictionary has an invalid format. Check it first.",
    "source": "ingredient_corrections.py:134"
  },
  {
    "zh": "食材词典行格式异常，请先核对。",
    "en": "An ingredient dictionary row has an invalid format. Check it first.",
    "source": "ingredient_corrections.py:138"
  },
  {
    "zh": "“{0}”同时出现在不同分类，无法确定菜品用量归属。",
    "en": "“{0}” appears in multiple categories; its dish consumption category cannot be determined.",
    "source": "ingredient_corrections.py:159"
  },
  {
    "zh": "{0} 的相关菜品数据不是明细数组。",
    "en": "{0}: the related dish data is not a detail array.",
    "source": "ingredient_corrections.py:246"
  },
  {
    "zh": "目标品名已存在；合并后 FIFO 批次分摊和历史出库成本会重新计算，原采购数量、单价和金额不变。",
    "en": "The target item name already exists. Merging recalculates FIFO allocations and historical outbound costs; original purchase quantities, unit prices and amounts remain unchanged.",
    "source": "ingredient_corrections.py:355"
  },
  {
    "zh": "安全库存配置格式异常，请先核对。",
    "en": "Safety-stock settings have an invalid format. Check them first.",
    "source": "ingredient_corrections.py:373"
  },
  {
    "zh": "更正会改变菜品的分类、单位或用量归属，不能自动合并。",
    "en": "This correction would change the category, unit or item associated with dish consumption; automatic merging is unavailable.",
    "source": "ingredient_corrections.py:470"
  },
  {
    "zh": "更正前后的库存事件数量不同。",
    "en": "The number of inventory events differs before and after the correction.",
    "source": "ingredient_corrections.py:476"
  },
  {
    "zh": "盘点原始记录格式异常，请先核对。",
    "en": "The original stocktake record has an invalid format. Check it first.",
    "source": "ingredient_corrections.py:507"
  },
  {
    "zh": "JSON 明细字段发生改变",
    "en": "The JSON detail fields changed",
    "source": "ingredient_corrections.py:51"
  },
  {
    "zh": "更名不得修改原数量或金额",
    "en": "Renaming must not change original quantities or amounts",
    "source": "ingredient_corrections.py:55"
  },
  {
    "zh": "{0} 的相关 JSON 明细无法解析，请先修正。",
    "en": "{0}: related JSON details cannot be parsed. Correct them first.",
    "source": "ingredient_corrections.py:191"
  },
  {
    "zh": "{0}（{1}）更正后库存与原两项合计不符。",
    "en": "{0} ({1}): corrected inventory does not equal the original combined balance.",
    "source": "ingredient_corrections.py:461"
  },
  {
    "zh": "更正无法保持每个历史事件后的合计库存。",
    "en": "The correction cannot preserve the combined inventory balance after every historical event.",
    "source": "ingredient_corrections.py:489"
  },
  {
    "zh": "单位“{0}”不属于本次受影响库存。",
    "en": "Unit “{0}” is not part of the inventory affected by this correction.",
    "source": "ingredient_corrections.py:502"
  },
  {
    "zh": "在历史合并后新增今日盘点，以本次填写的实际数量为最终库存；差额不改变原采购支出。",
    "en": "Add a stocktake for today after merging history. The entered actual quantity becomes the final balance; the difference does not change original purchase expenses.",
    "source": "ingredient_corrections.py:537"
  },
  {
    "zh": "新增盘点未得到指定的最终库存，不能执行更正。",
    "en": "The new stocktake did not produce the specified final balance. Correction cannot proceed.",
    "source": "ingredient_corrections.py:544"
  },
  {
    "zh": "{0} 的相关明细有互相矛盾的名称字段。",
    "en": "{0}: related details contain conflicting name fields.",
    "source": "ingredient_corrections.py:217"
  },
  {
    "zh": "{0} 的相关原始来源不是对象，不能遗漏执行更正。",
    "en": "{0}: a related original source is not an object. Correction cannot omit it.",
    "source": "ingredient_corrections.py:257"
  },
  {
    "zh": "{0} 的相关采购行格式异常。",
    "en": "{0}: a related purchase row has an invalid format.",
    "source": "ingredient_corrections.py:262"
  },
  {
    "zh": "{0} 的相关菜品行格式异常。",
    "en": "{0}: a related dish row has an invalid format.",
    "source": "ingredient_corrections.py:275"
  },
  {
    "zh": "{0}（{1}）完全相同的安全库存配置合并为一条，原值保留于审计。",
    "en": "{0} ({1}): identical safety-stock settings were merged into one entry; original values remain in the audit log.",
    "source": "ingredient_corrections.py:391"
  },
  {
    "zh": "{0}（{1}）的安全库存阈值或扩展字段冲突，请先保留一条明确配置后再预览。",
    "en": "{0} ({1}): safety-stock thresholds or extension fields conflict. Keep one unambiguous setting, then preview again.",
    "source": "ingredient_corrections.py:393"
  },
  {
    "zh": "{0} {1}：{2}，不能据此合并盘点。",
    "en": "{0} {1}: {2}; this cannot be used to merge stocktakes.",
    "source": "ingredient_corrections.py:399",
    "parameters": {
      "2": "message"
    }
  },
  {
    "zh": "{0} 的相关菜品 JSON 无法解析。",
    "en": "{0}: related dish JSON cannot be parsed.",
    "source": "ingredient_corrections.py:231"
  },
  {
    "zh": "“{0}”存在数量或日期无效的历史库存行，无法验证更正结果。",
    "en": "“{0}” has historical inventory rows with invalid quantities or dates; the correction result cannot be verified.",
    "source": "ingredient_corrections.py:368"
  },
  {
    "zh": "{0} {1}采购缺少明确数量／单位，不能据此合并盘点。",
    "en": "{0} {1}: the purchase has no explicit quantity or unit and cannot be used to merge stocktakes.",
    "source": "ingredient_corrections.py:405"
  },
  {
    "zh": "{0} {1}（{2}）合并实盘会为负数，不能自动更正。",
    "en": "{0} {1} ({2}): the combined stocktake would be negative; automatic correction is unavailable.",
    "source": "ingredient_corrections.py:422"
  },
  {
    "zh": "原{0}实盘加另一品名当时余额 {1}；保留两项合计库存",
    "en": "Original stocktake for {0} plus the other item's balance of {1}; preserves their combined inventory",
    "source": "ingredient_corrections.py:437"
  },
  {
    "zh": "相关库存 {0} 行格式异常，不能遗漏来源执行更正。",
    "en": "A related inventory row in {0} has an invalid format. Correction cannot omit a source.",
    "source": "ingredient_corrections.py:279"
  },
  {
    "zh": "{0} {1} 的事件时间不明确，无法安全合并。",
    "en": "{0} {1}: event ordering is ambiguous; safe merging is unavailable.",
    "source": "ingredient_corrections.py:337"
  },
  {
    "zh": "盘点已有无法识别的更正元数据，请先核对。",
    "en": "A stocktake contains unrecognized correction metadata. Check it first.",
    "source": "ingredient_corrections.py:429"
  },
  {
    "zh": "当前日有无法确定先后顺序的库存记录，不能追加本次盘点。",
    "en": "Inventory records for today have ambiguous ordering; this stocktake cannot be appended.",
    "source": "ingredient_corrections.py:520"
  },
  {
    "zh": "相关库存行有互相矛盾的名称字段，请先核对。",
    "en": "A related inventory row contains conflicting name fields. Check it first.",
    "source": "ingredient_corrections.py:289"
  },
  {
    "zh": "{0} {1} 的{2}，请先在菜品明细核对后再出库／盘点。",
    "en": "{0} {1}: {2}. Check the dish details before posting an outbound or stocktake.",
    "source": "inventory_balance.py:289",
    "parameters": {
      "2": "message"
    }
  },
  {
    "zh": "{0}库存不足，此操作会新增短缺 {1} {2}；请刷新并核对入库、菜品用量和盘点记录。",
    "en": "Insufficient inventory for {0}. This operation would add a shortage of {1} {2}. Refresh and check receipts, dish usage and stocktakes.",
    "source": "inventory_balance.py:296"
  },
  {
    "zh": "{0}盘点账面数量已变化，请刷新库存后重新盘点。",
    "en": "The book balance for {0} has changed. Refresh inventory and enter the stocktake again.",
    "source": "inventory_balance.py:301"
  },
  {
    "zh": "菜品数据不是明细数组",
    "en": "Dish data is not a detail array",
    "source": "inventory_balance.py:194"
  },
  {
    "zh": "菜品行格式无效",
    "en": "A dish row has an invalid format",
    "source": "inventory_balance.py:198"
  },
  {
    "zh": "{0}存在数量或日期无效的历史库存记录，请管理员核对后再操作。",
    "en": "{0} has historical inventory records with invalid quantities or dates. Ask an administrator to check them before proceeding.",
    "source": "inventory_balance.py:285"
  },
  {
    "zh": "菜品数据无法解析",
    "en": "Dish data cannot be parsed",
    "source": "inventory_balance.py:191"
  },
  {
    "zh": "菜品食材缺少有效用量",
    "en": "Dish ingredients have no valid usage quantity",
    "source": "inventory_balance.py:204"
  },
  {
    "zh": "库存单据：{0}",
    "en": "Inventory document: {0}",
    "source": "inventory_validation.py:28",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "安全库存设置仅对修改权限和管理员开放。",
    "en": "Only editors and administrators can change safety-stock settings.",
    "source": "main.py:4143"
  },
  {
    "zh": "{0}必须填写有效数字。",
    "en": "{0} must be a valid number.",
    "source": "inventory_validation.py:56",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}必须是{1}的有限数字。",
    "en": "{0} must be a finite number that is {1}.",
    "source": "inventory_validation.py:58",
    "parameters": {
      "0": "label",
      "1": "condition"
    }
  },
  {
    "zh": "每行须填写食材／佐料分类、名称和单位。",
    "en": "Each row requires an ingredient/seasoning category, name and unit.",
    "source": "inventory_validation.py:81"
  },
  {
    "zh": "voided 必须是布尔值。",
    "en": "voided must be a boolean.",
    "source": "inventory_validation.py:86"
  },
  {
    "zh": "新增行必须具有唯一 id。",
    "en": "Each new row must have a unique id.",
    "source": "inventory_validation.py:97"
  },
  {
    "zh": "price_known 必须是布尔值。",
    "en": "price_known must be a boolean.",
    "source": "inventory_validation.py:155"
  },
  {
    "zh": "安全库存配置必须是数组。",
    "en": "Safety-stock settings must be an array.",
    "source": "inventory_validation.py:226"
  },
  {
    "zh": "同一食材、分类和单位的安全库存不能重复。",
    "en": "Safety-stock settings cannot repeat the same item, category and unit.",
    "source": "inventory_validation.py:241"
  },
  {
    "zh": "录入权限不能修改已有库存扩展配置。",
    "en": "Entry accounts cannot change existing inventory extension settings.",
    "source": "inventory_validation.py:273"
  },
  {
    "zh": "{0}须为 UTC ISO 时间。",
    "en": "{0} must be a UTC ISO timestamp.",
    "source": "inventory_validation.py:69",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "盘点单不能作废，请新增盘点单纠正。",
    "en": "A stocktake cannot be voided. Add a new stocktake to correct it.",
    "source": "inventory_validation.py:89"
  },
  {
    "zh": "作废必须填写原因。",
    "en": "A reason is required to void a document.",
    "source": "inventory_validation.py:91"
  },
  {
    "zh": "业务日期必须是 YYYY-MM-DD。",
    "en": "The business date must use YYYY-MM-DD.",
    "source": "inventory_validation.py:105"
  },
  {
    "zh": "必须填写单据编号。",
    "en": "A document number is required.",
    "source": "inventory_validation.py:113"
  },
  {
    "zh": "新单据只能提交今天，请刷新日期后重试。",
    "en": "New documents can be posted only for today. Refresh the date and try again.",
    "source": "inventory_validation.py:116"
  },
  {
    "zh": "自动采购应在原食材明细中修改，不能另存为库存入库单。",
    "en": "Edit automatic purchases in the original ingredient details; they cannot be saved separately as inventory receipts.",
    "source": "inventory_validation.py:120"
  },
  {
    "zh": "新入库单必须填写单价，包括零元入库。",
    "en": "New receipts require a unit price, including an explicit zero for free receipts.",
    "source": "inventory_validation.py:125"
  },
  {
    "zh": "同一单据的日期、编号、时间和作废状态必须一致。",
    "en": "All rows in a document must have the same date, document number, timestamp and void status.",
    "source": "inventory_validation.py:218"
  },
  {
    "zh": "安全库存配置无效。",
    "en": "Invalid safety-stock settings.",
    "source": "inventory_validation.py:238"
  },
  {
    "zh": "录入权限仅可在该库存记录保存后 30 分钟内作废或修改。",
    "en": "Entry accounts may void or edit an inventory record only within 30 minutes of saving it.",
    "source": "inventory_validation.py:270"
  },
  {
    "zh": "document_id 必须是 UUID。",
    "en": "document_id must be a UUID.",
    "source": "inventory_validation.py:111"
  },
  {
    "zh": "入库总价须等于数量乘单价。",
    "en": "The receipt total must equal quantity multiplied by unit price.",
    "source": "inventory_validation.py:130"
  },
  {
    "zh": "出库用途须为领用或损耗。",
    "en": "An outbound must be classified as normal use or loss.",
    "source": "inventory_validation.py:137"
  },
  {
    "zh": "盘点必须填写原因。",
    "en": "A reason is required for a stocktake.",
    "source": "inventory_validation.py:140"
  },
  {
    "zh": "盘盈已定价时必须填写单价。",
    "en": "A priced stock gain must have a unit price.",
    "source": "inventory_validation.py:153"
  },
  {
    "zh": "行 id 重复，不能重复提交同一行。",
    "en": "Duplicate row id. The same row cannot be submitted twice.",
    "source": "inventory_validation.py:168"
  },
  {
    "zh": "{0} 必须是数组。",
    "en": "{0} must be an array.",
    "source": "inventory_validation.py:173"
  },
  {
    "zh": "库存行必须是对象。",
    "en": "An inventory row must be an object.",
    "source": "inventory_validation.py:185"
  },
  {
    "zh": "本账本已使用新版库存单据，请更新 App／刷新网页后再录入，不能用旧版无单号记录覆盖。",
    "en": "This ledger uses the new inventory documents. Update the app or refresh the webpage before entering data; legacy records without document numbers cannot replace it.",
    "source": "inventory_validation.py:191"
  },
  {
    "zh": "不能撤销已保存的作废操作。",
    "en": "A saved void operation cannot be undone.",
    "source": "inventory_validation.py:193"
  },
  {
    "zh": "自动采购只能在原食材明细中改正。",
    "en": "Automatic purchases can be corrected only in the original ingredient details.",
    "source": "inventory_validation.py:195"
  },
  {
    "zh": "此历史行 id 重复，请先由管理员核对记录。",
    "en": "This historical row has a duplicate id. Ask an administrator to check it first.",
    "source": "inventory_validation.py:197"
  },
  {
    "zh": "已保存单据不能追加行，请创建新单据。",
    "en": "Rows cannot be appended to a saved document. Create a new document.",
    "source": "inventory_validation.py:223"
  },
  {
    "zh": "已保存单据不能删除，请作废入／出库单，或新增盘点单纠正。",
    "en": "Saved documents cannot be deleted. Void a receipt/outbound, or add a stocktake to correct inventory.",
    "source": "inventory_validation.py:180"
  },
  {
    "zh": "{0} 必须是文本。",
    "en": "{0} must be text.",
    "source": "inventory_validation.py:189"
  },
  {
    "zh": "已保存单据不可直接修改，请作废后重新录入。",
    "en": "Saved documents cannot be edited directly. Void the document and enter it again.",
    "source": "inventory_validation.py:202"
  },
  {
    "zh": "已保存单据仅能作废，不能撤销作废或改写记录。",
    "en": "Saved documents may only be voided; voids cannot be undone and records cannot be rewritten.",
    "source": "inventory_validation.py:204"
  },
  {
    "zh": "盘点账面数量必须是有限数字。",
    "en": "The book quantity for a stocktake must be a finite number.",
    "source": "inventory_validation.py:148"
  },
  {
    "zh": "普通账号至少要绑定一套账本。",
    "en": "A regular account must be assigned to at least one ledger.",
    "source": "main.py:1628"
  },
  {
    "zh": "数据集不存在。",
    "en": "Ledger not found.",
    "source": "main.py:1744"
  },
  {
    "zh": "当前账号无权访问这套账本。",
    "en": "This account does not have access to this ledger.",
    "source": "main.py:1766"
  },
  {
    "zh": "当前账号只读，不能修改账本。",
    "en": "This account has read-only access and cannot edit the ledger.",
    "source": "main.py:1768"
  },
  {
    "zh": "只接受 .xlsx 文件，不接受 .xls/.xlsm。",
    "en": "Only .xlsx files are accepted; .xls and .xlsm are not supported.",
    "source": "main.py:2057"
  },
  {
    "zh": "上传的 Excel 文件为空。",
    "en": "The uploaded Excel file is empty.",
    "source": "main.py:2063"
  },
  {
    "zh": "Excel 文件超过 25 MB 上限。",
    "en": "The Excel file exceeds the 25 MB limit.",
    "source": "main.py:2065"
  },
  {
    "zh": "现金余额表记录格式不正确。",
    "en": "Invalid cash-balance record format.",
    "source": "main.py:2352"
  },
  {
    "zh": "目前余额和向股东借款不能为负数。",
    "en": "The current balance and shareholder loan amount cannot be negative.",
    "source": "main.py:2704"
  },
  {
    "zh": "现金余额表记录版本冲突。",
    "en": "Cash-balance record version conflict.",
    "source": "main.py:2740"
  },
  {
    "zh": "账号或密码不正确。",
    "en": "Incorrect username or password.",
    "source": "main.py:2944"
  },
  {
    "zh": "Test 快速登录未启用。",
    "en": "Test quick sign-in is not enabled.",
    "source": "main.py:2957"
  },
  {
    "zh": "Test 演示账号当前不可用。",
    "en": "The Test demonstration account is currently unavailable.",
    "source": "main.py:2962"
  },
  {
    "zh": "Test 演示账本尚未配置。",
    "en": "The Test demonstration ledger has not been configured.",
    "source": "main.py:2970"
  },
  {
    "zh": "role 必须是 admin/editor/entry/viewer。",
    "en": "role must be admin, editor, entry or viewer.",
    "source": "main.py:3034"
  },
  {
    "zh": "Test 是系统保留账号。",
    "en": "Test is a reserved system account.",
    "source": "main.py:3001"
  },
  {
    "zh": "用户名已存在。",
    "en": "This username already exists.",
    "source": "main.py:3006"
  },
  {
    "zh": "用户不存在。",
    "en": "User not found.",
    "source": "main.py:3077"
  },
  {
    "zh": "不能删除当前登录的管理员账号。",
    "en": "You cannot delete the administrator account currently signed in.",
    "source": "main.py:3079"
  },
  {
    "zh": "公开 Test 账号不能删除。",
    "en": "The public Test account cannot be deleted.",
    "source": "main.py:3081"
  },
  {
    "zh": "目标账号不存在或已停用。",
    "en": "The target account does not exist or has been disabled.",
    "source": "main.py:3107"
  },
  {
    "zh": "管理员或公开 Test 账号不需要临时权限。",
    "en": "Administrators and the public Test account do not need temporary access.",
    "source": "main.py:3109"
  },
  {
    "zh": "临时权限必须是录入权限或修改权限。",
    "en": "Temporary access must grant entry or editing permissions.",
    "source": "main.py:3112"
  },
  {
    "zh": "结束时间必须晚于开始时间。",
    "en": "The end time must be later than the start time.",
    "source": "main.py:3116"
  },
  {
    "zh": "业务结束日期不能早于开始日期。",
    "en": "The last business date cannot precede the first business date.",
    "source": "main.py:3118"
  },
  {
    "zh": "临时权限记录不存在。",
    "en": "Temporary-access record not found.",
    "source": "main.py:3143"
  },
  {
    "zh": "账本名称不能为空。",
    "en": "A ledger name is required.",
    "source": "main.py:3201"
  },
  {
    "zh": "Test 独立演示账本不能删除。",
    "en": "The independent Test demonstration ledger cannot be deleted.",
    "source": "main.py:3217"
  },
  {
    "zh": "确认名称与当前账本名称不一致。",
    "en": "The confirmation name does not match the current ledger name.",
    "source": "main.py:3219"
  },
  {
    "zh": "仍有用户绑定这套账本，请先在用户管理中解除绑定。",
    "en": "Users are still assigned to this ledger. Remove those assignments in Users first.",
    "source": "main.py:3228"
  },
  {
    "zh": "双重确认失败：两次确认都必须匹配目标账本名称。",
    "en": "Both confirmations must match the target ledger name.",
    "source": "main.py:3327"
  },
  {
    "zh": "两家店的显示名称不能完全相同。",
    "en": "The two store display names must differ.",
    "source": "main.py:3522"
  },
  {
    "zh": "{0} 超过 2 MB 上限。",
    "en": "{0} exceeds the 2 MB limit.",
    "source": "main.py:3739"
  },
  {
    "zh": "{0} 为空。",
    "en": "{0} is empty.",
    "source": "main.py:3741"
  },
  {
    "zh": "这家店还没有完整的微信支付配置。",
    "en": "This store does not have a complete WeChat Pay configuration.",
    "source": "main.py:3801"
  },
  {
    "zh": "微信交易账单只能同步已经结束的历史日期。",
    "en": "WeChat statements can be synced only for completed dates.",
    "source": "main.py:3828"
  },
  {
    "zh": "结束日期不能早于开始日期。",
    "en": "The end date cannot precede the start date.",
    "source": "main.py:3907"
  },
  {
    "zh": "一次最多删除 10 年范围的数据。",
    "en": "A deletion can cover no more than 10 years at once.",
    "source": "main.py:3910"
  },
  {
    "zh": "源账本和目标账本不能是同一套账本。",
    "en": "The source and target ledgers must differ.",
    "source": "main.py:3989"
  },
  {
    "zh": "第一次确认失败：源账本名称不匹配。",
    "en": "First confirmation failed: the source ledger name does not match.",
    "source": "main.py:3991"
  },
  {
    "zh": "第二次确认失败：目标账本名称不匹配。",
    "en": "Second confirmation failed: the target ledger name does not match.",
    "source": "main.py:3993"
  },
  {
    "zh": "现金余额表只对修改权限和管理员开放。",
    "en": "Cash balance is available only to editors and administrators.",
    "source": "main.py:4305"
  },
  {
    "zh": "记录不存在。",
    "en": "Record not found.",
    "source": "main.py:4307"
  },
  {
    "zh": "当前账号在所选日期没有录入或修改权限。",
    "en": "This account has no entry or editing access for the selected date.",
    "source": "main.py:4299"
  },
  {
    "zh": "记录版本冲突。",
    "en": "Record version conflict.",
    "source": "main.py:4139"
  },
  {
    "zh": "库存单据需保留记录，不能删除整表；请作废入／出库单或新增盘点单纠正。",
    "en": "Inventory documents must be retained; the entire record cannot be deleted. Void a receipt/outbound or add a stocktake to correct inventory.",
    "source": "main.py:4313"
  },
  {
    "zh": "包含系统锁定的余额强制修改记录，不能删除整张现金余额表。",
    "en": "The cash-balance record contains system-locked balance overrides and cannot be deleted.",
    "source": "main.py:4321"
  },
  {
    "zh": "录入权限不能删除整日记录；请在各项目自己的 30 分钟修改时间内修改。",
    "en": "Entry accounts cannot delete an entire day's records. Edit each entry within its own 30-minute window.",
    "source": "main.py:4330"
  },
  {
    "zh": "请指定要删除的修改记录。",
    "en": "Specify the change-log entries to delete.",
    "source": "main.py:4431"
  },
  {
    "zh": "修改记录不存在。",
    "en": "Change-log entry not found.",
    "source": "main.py:4445"
  },
  {
    "zh": "冲突不存在。",
    "en": "Conflict not found.",
    "source": "main.py:4503"
  },
  {
    "zh": "冲突对应记录不存在。",
    "en": "The record associated with this conflict was not found.",
    "source": "main.py:4511"
  },
  {
    "zh": "{0}人数只能在首次保存后 30 分钟内修改或清空。",
    "en": "{0} counts may be changed or cleared only within 30 minutes of first saving them.",
    "source": "main.py:807",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "总客人数不能少于新客人数。",
    "en": "Total customers cannot be fewer than new customers.",
    "source": "main.py:835"
  },
  {
    "zh": "默认账本必须包含在 dataset_ids 中。",
    "en": "The default ledger must be included in dataset_ids.",
    "source": "main.py:1623"
  },
  {
    "zh": "Test 账号只能绑定 Test 独立账本。",
    "en": "The Test account can be assigned only to the independent Test ledger.",
    "source": "main.py:1631"
  },
  {
    "zh": "账本不存在：{0}。",
    "en": "Ledger not found: {0}.",
    "source": "main.py:1635"
  },
  {
    "zh": "现金明细必须是列表。",
    "en": "Cash entries must be a list.",
    "source": "main.py:2271"
  },
  {
    "zh": "现金明细格式不正确。",
    "en": "Invalid cash-entry format.",
    "source": "main.py:2288"
  },
  {
    "zh": "现金明细必须填写正确日期。",
    "en": "Each cash entry must have a valid date.",
    "source": "main.py:2291"
  },
  {
    "zh": "现金明细 id 不能重复。",
    "en": "Cash-entry ids must be unique.",
    "source": "main.py:2294"
  },
  {
    "zh": "不支持的现金明细类型：{0}。",
    "en": "Unsupported cash-entry type: {0}.",
    "source": "main.py:2329"
  },
  {
    "zh": "通过‘把余额强行修正成：’保存的余额强制修改记录不能删除或修改。",
    "en": "Balance overrides saved through the balance-correction control cannot be deleted or modified.",
    "source": "main.py:2398"
  },
  {
    "zh": "公开 Test 账号必须保持只读权限。",
    "en": "The public Test account must retain read-only access.",
    "source": "main.py:3036"
  },
  {
    "zh": "公开 Test 快速登录账号不能停用。",
    "en": "The public Test quick-sign-in account cannot be disabled.",
    "source": "main.py:3042"
  },
  {
    "zh": "缺少必需的微信支付文件。",
    "en": "A required WeChat Pay file is missing.",
    "source": "main.py:3732"
  },
  {
    "zh": "bill_date 必须是 YYYY-MM-DD。",
    "en": "bill_date must use YYYY-MM-DD.",
    "source": "main.py:3826"
  },
  {
    "zh": "月份格式不正确。",
    "en": "Invalid month format.",
    "source": "main.py:3965"
  },
  {
    "zh": "{0}必须是大于或等于 0 的整数。",
    "en": "{0} must be an integer greater than or equal to 0.",
    "source": "main.py:831",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}与对应明细或收款输入合计不一致，请重新计算后保存。",
    "en": "{0} does not match the corresponding details or revenue inputs. Recalculate before saving.",
    "source": "main.py:1293",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}项目只能在各自首次保存后 30 分钟内修改或删除。",
    "en": "{0} entries may be changed or deleted only within 30 minutes of each entry's first save.",
    "source": "main.py:1391",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "当日{0}新增窗口已截止（该分类首条明细保存后 12 小时）。",
    "en": "Today's window for adding {0} has closed (12 hours after the first entry in this category was saved).",
    "source": "main.py:1413",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}只能在首次保存后 30 分钟内修改或清空。",
    "en": "{0} may be changed or cleared only within 30 minutes of first saving it.",
    "source": "main.py:1456",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "总收入只能在保存后 30 分钟内修改。",
    "en": "Total revenue may be changed only within 30 minutes of saving it.",
    "source": "main.py:1491"
  },
  {
    "zh": "录入权限仅可继续填写空白或 0 字段；以下已有数据已超过 30 分钟，不能修改：{0}",
    "en": "Entry accounts may continue filling blank or zero fields only. These existing values were saved more than 30 minutes ago and cannot be changed: {0}",
    "source": "main.py:1529",
    "parameters": {
      "0": "paths"
    }
  },
  {
    "zh": "旧版股东借款",
    "en": "Legacy shareholder loan",
    "source": "main.py:2535"
  },
  {
    "zh": "resolution 必须是 use_local/use_cloud/merged。",
    "en": "resolution must be use_local, use_cloud or merged.",
    "source": "main.py:4547"
  },
  {
    "zh": "{0}只能在首次保存后 30 分钟内修改；补录收款渠道不能重新开始修改期限。",
    "en": "{0} may be edited only within 30 minutes of its first save. Adding revenue channels does not restart this window.",
    "source": "main.py:1277",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}只能在首次保存后 30 分钟内修改；合计必须与对应明细或收款输入一致。",
    "en": "{0} may be edited only within 30 minutes of its first save. The total must match the corresponding details or revenue inputs.",
    "source": "main.py:1287",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "{0}未录入时最晚须在第二天 11:00 前首次保存。",
    "en": "If {0} has not been entered, its first save must be completed by 11:00 the next day.",
    "source": "main.py:1291",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "当日总收入未录入时最晚须在第二天 11:00 前首次保存。",
    "en": "If today's total revenue has not been entered, its first save must be completed by 11:00 the next day.",
    "source": "main.py:1499"
  },
  {
    "zh": "余额强制修改的保存时间格式不正确。",
    "en": "The saved timestamp for the balance override is invalid.",
    "source": "main.py:2312"
  },
  {
    "zh": "当日收入",
    "en": "Daily revenue",
    "source": "main.py:2444"
  },
  {
    "zh": "{0} 月度固定成本",
    "en": "{0} monthly fixed costs",
    "source": "main.py:2520"
  },
  {
    "zh": "找不到管理员账号，无法记录微信自动同步审计。",
    "en": "No administrator account was found to log the automatic WeChat sync.",
    "source": "main.py:2831"
  },
  {
    "zh": "金额必须填写有效十进制数字。",
    "en": "Enter a valid decimal amount.",
    "source": "money.py:31"
  },
  {
    "zh": "金额不能是布尔值。",
    "en": "An amount cannot be a boolean.",
    "source": "money.py:27"
  },
  {
    "zh": "金额必须是有限数字，且整数部分不能超过 999999999999。",
    "en": "The amount must be finite and its integer part cannot exceed 999999999999.",
    "source": "money.py:33"
  },
  {
    "zh": "金额精度超出允许范围。",
    "en": "The amount exceeds the supported precision.",
    "source": "money.py:36"
  },
  {
    "zh": "金额超出允许范围。",
    "en": "The amount is outside the allowed range.",
    "source": "money.py:44"
  },
  {
    "zh": "单价超出允许范围。",
    "en": "The unit price is outside the allowed range.",
    "source": "money.py:55"
  },
  {
    "zh": "采购明细金额必须是有限数字。",
    "en": "Purchase-detail amounts must be finite numbers.",
    "source": "money.py:150"
  },
  {
    "zh": "历史金额数值格式无效。",
    "en": "A historical amount has an invalid numeric format.",
    "source": "money.py:291"
  },
  {
    "zh": "品名不能为空，也不能含换行或控制字符。",
    "en": "An item name is required and cannot contain line breaks or control characters.",
    "source": "name_corrections.py:66"
  },
  {
    "zh": "实际库存单位不能为空或重复。",
    "en": "Actual-stock units cannot be empty or duplicated.",
    "source": "name_corrections.py:69"
  },
  {
    "zh": "更正前后明细数量不同，无法保留原录入时钟。",
    "en": "The detail-row count changed during correction; original entry timestamps cannot be preserved.",
    "source": "name_corrections.py:197"
  },
  {
    "zh": "品名更正预览仅对修改权限和管理员开放。",
    "en": "Only editors and administrators can preview item-name corrections.",
    "source": "name_corrections.py:221"
  },
  {
    "zh": "请填写品名更正原因。",
    "en": "Enter a reason for the item-name correction.",
    "source": "name_corrections.py:234"
  },
  {
    "zh": "账本在预览后已有更新，请重新预览；本次没有修改任何记录。",
    "en": "The ledger changed after the preview. Preview again; no records were changed by this attempt.",
    "source": "name_corrections.py:249"
  },
  {
    "zh": "请先确认将两个品名的库存按单位相加，并按预览换算盘点。",
    "en": "Confirm that both item balances will be combined by unit and their stocktakes converted as shown in the preview.",
    "source": "name_corrections.py:253"
  },
  {
    "zh": "品名更正已一次性完成，并按确认的实际库存保存；原采购金额和录入时钟已保留。",
    "en": "The item name was corrected atomically and the confirmed actual inventory was saved. Original purchase amounts and entry timestamps were preserved.",
    "source": "name_corrections.py:308"
  },
  {
    "zh": "单价不能为负数",
    "en": "The unit price cannot be negative",
    "source": "name_corrections.py:38"
  },
  {
    "zh": "数量和单价必须是数字",
    "en": "Quantity and unit price must be numeric",
    "source": "name_corrections.py:45"
  },
  {
    "zh": "历史共享日期来源无法安全保序；更正会切换收入、采购或菜品来源，请先核对重复记录。",
    "en": "Historical sources sharing a date cannot be reordered safely. This correction would switch the source of revenue, purchases or dishes; check duplicate records first.",
    "source": "name_corrections.py:149"
  },
  {
    "zh": "另有 {0} 条共享日期来源仅刷新同步版本以保留原顺序，业务内容与原录入时间不变。",
    "en": "{0} additional sources sharing a date have only their sync version refreshed to preserve ordering; business contents and original entry times remain unchanged.",
    "source": "name_corrections.py:153"
  },
  {
    "zh": "相关原始记录格式不完整，无法安全更正：{0}",
    "en": "Related original records are incomplete and cannot be corrected safely: {0}",
    "source": "name_corrections.py:166",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "库存总表已被删除，请管理员先恢复并核对库存后再填写实际数量。",
    "en": "The inventory record was deleted. Ask an administrator to restore and check it before entering actual quantities.",
    "source": "name_corrections.py:168"
  },
  {
    "zh": "该请求编号已用于其他更正，请重新预览并生成新请求。",
    "en": "This request id was already used for another correction. Preview again to generate a new request.",
    "source": "name_corrections.py:244"
  },
  {
    "zh": "当前更正不能执行。",
    "en": "This correction cannot be applied.",
    "source": "name_corrections.py:251"
  },
  {
    "zh": "尚未登录。",
    "en": "Sign in first.",
    "source": "security.py:47"
  },
  {
    "zh": "账号不可用。",
    "en": "This account is unavailable.",
    "source": "security.py:55"
  },
  {
    "zh": "当前账号只读，不能修改数据。",
    "en": "This account has read-only access and cannot change data.",
    "source": "security.py:61"
  },
  {
    "zh": "需要修改权限或管理员权限。",
    "en": "Editing or administrator access is required.",
    "source": "security.py:68"
  },
  {
    "zh": "需要管理员权限。",
    "en": "Administrator access is required.",
    "source": "security.py:74"
  },
  {
    "zh": "登录令牌无效。",
    "en": "Invalid sign-in token.",
    "source": "security.py:52"
  },
  {
    "zh": "账本 ID 不能为空。",
    "en": "A ledger ID is required.",
    "source": "store_settings.py:24"
  },
  {
    "zh": "店铺槽位只能是 A 或 B。",
    "en": "The store slot must be A or B.",
    "source": "store_settings.py:42"
  },
  {
    "zh": "微信支付商户号格式不正确，应为纯数字。",
    "en": "The WeChat Pay merchant id must contain digits only.",
    "source": "store_settings.py:100"
  },
  {
    "zh": "微信支付公钥 ID 格式不正确，应以 PUB_KEY_ID_ 开头。",
    "en": "The WeChat Pay public-key id must begin with PUB_KEY_ID_.",
    "source": "store_settings.py:102"
  },
  {
    "zh": "必须上传 apiclient_cert.pem、apiclient_key.pem 和 pub_key.pem。",
    "en": "Upload apiclient_cert.pem, apiclient_key.pem and pub_key.pem.",
    "source": "store_settings.py:104"
  },
  {
    "zh": "apiclient_cert.pem 与 apiclient_key.pem 不配套，已拒绝保存。",
    "en": "apiclient_cert.pem and apiclient_key.pem do not match. Settings were not saved.",
    "source": "store_settings.py:131"
  },
  {
    "zh": "apiclient_cert.pem 无法解析：{0}",
    "en": "Unable to parse apiclient_cert.pem: {0}",
    "source": "store_settings.py:109",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "apiclient_key.pem 无法解析：{0}",
    "en": "Unable to parse apiclient_key.pem: {0}",
    "source": "store_settings.py:113",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "pub_key.pem 无法解析：{0}",
    "en": "Unable to parse pub_key.pem: {0}",
    "source": "store_settings.py:117",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "无法检查商户证书与私钥：{0}",
    "en": "Unable to check the merchant certificate and private key: {0}",
    "source": "store_settings.py:129",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信支付公钥无法使用：{0}",
    "en": "The WeChat Pay public key cannot be used: {0}",
    "source": "store_settings.py:140",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信账单金额不能是布尔值。",
    "en": "A WeChat statement amount cannot be a boolean.",
    "source": "wechat_pay.py:104"
  },
  {
    "zh": "微信交易账单格式无法识别：未找到交易明细表头。",
    "en": "The WeChat transaction statement is missing a recognized transaction header.",
    "source": "wechat_pay.py:130"
  },
  {
    "zh": "A店/B店设备号配置重复：{1}",
    "en": "Store A and Store B have duplicate device ids: {1}",
    "source": "wechat_pay.py:214"
  },
  {
    "zh": "WECHAT_UNMATCHED_STORE 只能是 A、B、IGNORE 或 ERROR。",
    "en": "WECHAT_UNMATCHED_STORE must be A, B, IGNORE or ERROR.",
    "source": "wechat_pay.py:217"
  },
  {
    "zh": "微信账单中存在无法归属 A店/B店 的交易。请配置 WECHAT_A_DEVICE_IDS / WECHAT_B_DEVICE_IDS，或明确设置 WECHAT_UNMATCHED_STORE。示例设备号：{1}",
    "en": "Some WeChat transactions cannot be assigned to Store A or Store B. Configure WECHAT_A_DEVICE_IDS / WECHAT_B_DEVICE_IDS, or explicitly set WECHAT_UNMATCHED_STORE. Example device ids: {1}",
    "source": "wechat_pay.py:239"
  },
  {
    "zh": "微信支付配置不完整：{1}",
    "en": "The WeChat Pay configuration is incomplete: {1}",
    "source": "wechat_pay.py:56",
    "parameters": {
      "1": "labels"
    }
  },
  {
    "zh": "金额无效：{0}",
    "en": "Invalid amount: {0}",
    "source": "wechat_sync.py:51",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信账单金额无效：{0}",
    "en": "Invalid WeChat statement amount: {0}",
    "source": "wechat_pay.py:111",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信支付响应缺少验签请求头。",
    "en": "The WeChat Pay response is missing signature-verification headers.",
    "source": "wechat_pay.py:291"
  },
  {
    "zh": "微信支付响应公钥ID不匹配：收到 {0}，配置为 {1}。",
    "en": "WeChat Pay response public-key id mismatch: received {0}, configured {1}.",
    "source": "wechat_pay.py:294"
  },
  {
    "zh": "暂不支持微信账单哈希类型：{0}",
    "en": "Unsupported WeChat statement hash type: {0}",
    "source": "wechat_pay.py:353"
  },
  {
    "zh": "微信交易账单 SHA1 校验失败，已拒绝写入收入。",
    "en": "WeChat transaction statement SHA1 verification failed. Revenue was not updated.",
    "source": "wechat_pay.py:357"
  },
  {
    "zh": "{0}文件不存在：{1}",
    "en": "{0} file not found: {1}",
    "source": "wechat_pay.py:59",
    "parameters": {
      "0": "label"
    }
  },
  {
    "zh": "无法读取商户私钥：{0}",
    "en": "Unable to read the merchant private key: {0}",
    "source": "wechat_pay.py:256",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "无法读取微信支付公钥：{0}",
    "en": "Unable to read the WeChat Pay public key: {0}",
    "source": "wechat_pay.py:262",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信支付响应签名验证失败。",
    "en": "WeChat Pay response signature verification failed.",
    "source": "wechat_pay.py:301"
  },
  {
    "zh": "微信支付 API 请求失败（HTTP {0}）{1}：{2}",
    "en": "WeChat Pay API request failed (HTTP {0}){1}: {2}",
    "source": "wechat_pay.py:325",
    "parameters": {
      "2": "message"
    }
  },
  {
    "zh": "无法连接微信支付 API：{0}",
    "en": "Unable to connect to the WeChat Pay API: {0}",
    "source": "wechat_pay.py:330",
    "parameters": {
      "0": "message"
    }
  },
  {
    "zh": "微信支付申请账单响应格式不正确。",
    "en": "The WeChat Pay statement response has an invalid format.",
    "source": "wechat_pay.py:351"
  },
  {
    "zh": "WECHAT_AMOUNT_MODE 只能是 order 或 settlement。",
    "en": "WECHAT_AMOUNT_MODE must be order or settlement.",
    "source": "wechat_sync.py:403"
  },
  {
    "zh": "当前账本的两家店都还没有配置微信支付商户资料。",
    "en": "Neither store in the current ledger has a WeChat Pay merchant configuration.",
    "source": "wechat_sync.py:414"
  },
  {
    "zh": "微信同步指定的账本不存在。",
    "en": "The ledger specified for WeChat sync does not exist.",
    "source": "wechat_sync.py:440"
  },
  {
    "zh": "账本金额无效：{0}",
    "en": "Invalid ledger amount: {0}",
    "source": "wechat_sync.py:59",
    "parameters": {
      "0": "message"
    }
  }
];
globalThis.BACKEND_EN_LABELS = {
  "daily": "Daily ledger",
  "dishes": "Dishes",
  "monthly_fixed": "Monthly fixed costs",
  "entries": "Receipts",
  "adjustments": "Inventory adjustments",
  "overrides": "Stocktakes",
  "transactions": "Cash entries",
  "opening_balance": "Opening cash balance",
  "opening_date": "Balance reference date",
  "shareholder_loan": "Shareholder loan",
  "name": "Name",
  "date": "Date",
  "amount": "Amount",
  "quantity": "Quantity",
  "unit": "Unit",
  "total": "Total amount",
  "note": "Notes",
  "数量": "Quantity",
  "单价": "Unit price",
  "份数": "Servings",
  "食材名称": "Ingredient name",
  "佐料名称": "Seasoning name",
  "入库单价": "Receipt unit price",
  "入库总价": "Receipt total",
  "安全库存": "Safety stock",
  "作废时间": "Voided-at timestamp",
  "记账时间": "Recorded-at timestamp",
  "首次保存时间": "First-saved timestamp",
  "新客": "New customer",
  "总客数": "Total customer",
  "新客人数量": "New customers",
  "总客人数": "Total customers",
  "食材": "Ingredient",
  "佐料": "Seasoning",
  "其它": "Other",
  "其他": "Other",
  "食材金额": "Ingredient amount",
  "佐料金额": "Seasoning amount",
  "其它金额": "Other amount",
  "收益": "Revenue",
  "收入": "Revenue",
  "总收入": "Total revenue",
  "总金额": "Total amount",
  "总现金": "Cash total",
  "总线上": "Online total",
  "食材成本": "Ingredient cost",
  "佐料成本": "Seasoning cost",
  "水电": "Utilities",
  "日期": "Date",
  "月份": "Month",
  "记录类型": "Record type",
  "名称": "Name",
  "单位": "Unit",
  "总价": "Total amount",
  "金额": "Amount",
  "备注": "Notes",
  "当日备注": "Daily notes",
  "月度备注": "Monthly notes",
  "类别": "Category",
  "明细": "Details",
  "词条名称": "Dictionary entry name",
  "类别名称": "Category name",
  "菜品明细": "Dish details",
  "菜品数据": "Dish data",
  "菜品名称": "Dish name",
  "菜品份数": "Dish servings",
  "总成本": "Total costs",
  "成本": "Cost",
  "食材明细": "Ingredient details",
  "佐料明细": "Seasoning details",
  "其他明细": "Other details",
  "其它明细": "Other details",
  "人工总额": "Total labor cost",
  "房租总额": "Total rent",
  "水费支出": "Water expense",
  "电费支出": "Electricity expense",
  "水电费": "Utility costs",
  "实际使用水费": "Actual water cost",
  "实际使用电费": "Actual electricity cost",
  "煤气费": "Gas cost",
  "其它固定成本": "Other fixed costs",
  "预计水费": "Estimated water cost",
  "预计电费": "Estimated electricity cost",
  "预计煤气费": "Estimated gas cost",
  "手续费": "Fees",
  "学生外卖": "Student delivery",
  "微信支付商户号": "WeChat Pay merchant id",
  "商户 API 证书序列号": "Merchant API certificate serial number",
  "商户私钥路径": "Merchant private-key path",
  "微信支付公钥 ID": "WeChat Pay public-key id",
  "微信支付公钥路径": "WeChat Pay public-key path",
  "商户私钥": "Merchant private key",
  "微信支付公钥": "WeChat Pay public key",
  "微信账单日期": "WeChat statement date",
  "微信账单同步时间": "WeChat statement sync time",
  "微信账单口径": "WeChat statement basis",
  "微信账单SHA1": "WeChat statement SHA1",
  "微信账单未归属笔数": "Unassigned WeChat transactions",
  "微信账单强制更新": "Force WeChat statement update",
  "当日账本": "Daily ledger",
  "今日做出的菜品": "Dishes prepared today",
  "固定成本": "Fixed costs",
  "入库": "Receipts",
  "库存调整": "Inventory adjustments",
  "库存覆盖": "Stocktake overrides",
  "现金流水": "Cash entries",
  "期初现金余额": "Opening cash balance",
  "余额基准日期": "Balance reference date",
  "向股东借款": "Shareholder loan",
  "现金项目": "Cash entry",
  "其它现金收入": "Other cash income",
  "其它现金支出": "Other cash expense",
  "现金收入": "Cash income",
  "现金支出": "Cash expense",
  "余额强制修改": "Balance override",
  "账本内容": "Ledger contents",
  "计入可用余额": "Include in cash balance",
  "空白": "Blank",
  "旧版股东借款": "Legacy shareholder loan",
  "当日收入": "Daily revenue",
  "A店微信": "Store A WeChat",
  "A店支付宝": "Store A Alipay",
  "A店现金": "Store A Cash",
  "A店收入": "Store A Revenue",
  "A店外卖": "Store A Delivery",
  "A店微信增加": "Store A WeChat additions",
  "A店微信自动": "Store A WeChat automatic amount",
  "A店微信覆盖": "Store A WeChat override",
  "A店支付宝增加": "Store A Alipay additions",
  "A店支付宝覆盖": "Store A Alipay override",
  "A店微信支付金额": "Store A WeChat payments",
  "A店微信退款金额": "Store A WeChat refunds",
  "A店微信支付笔数": "Store A WeChat payment count",
  "A店微信退款笔数": "Store A WeChat refund count",
  "B店微信": "Store B WeChat",
  "B店支付宝": "Store B Alipay",
  "B店现金": "Store B Cash",
  "B店收入": "Store B Revenue",
  "B店外卖": "Store B Delivery",
  "B店微信增加": "Store B WeChat additions",
  "B店微信自动": "Store B WeChat automatic amount",
  "B店微信覆盖": "Store B WeChat override",
  "B店支付宝增加": "Store B Alipay additions",
  "B店支付宝覆盖": "Store B Alipay override",
  "B店微信支付金额": "Store B WeChat payments",
  "B店微信退款金额": "Store B WeChat refunds",
  "B店微信支付笔数": "Store B WeChat payment count",
  "B店微信退款笔数": "Store B WeChat refund count"
};
globalThis.BACKEND_EN_EXTRAS = {
  "Input should be '食材' or '佐料'": "Choose Ingredient or Seasoning.",
  "没有实际数据变化": "No actual data changes.",
  "账本内容已更新": "Ledger contents updated.",
  "品名更正": "Item-name correction",
  "品名更正（关联来源保序）": "Item-name correction (source ordering preserved)",
  "保留原数量、金额、分隔符和备注": "Preserve original quantities, amounts, separators and notes",
  "目标品名原盘点同步换算为合计实盘": "Convert the target item's original stocktake to the combined actual quantity",
  "新增实际库存盘点": "Add actual-inventory stocktake",
  "预览盘点": "Stocktake preview",
  "品名更正后的实际库存": "Actual inventory after item-name correction"
};

(function(){
 const root=globalThis, fixed={...root.BACKEND_EN_EXTRAS}, patterns=[];
 const own=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
 const label=value=>own(root.BACKEND_EN_LABELS,String(value))?root.BACKEND_EN_LABELS[String(value)]:String(value);
 const labels=value=>String(value).split(/([、,]\s*)/).map(part=>/^[、,]\s*$/.test(part)?', ':label(part)).join('');
 const location=value=>String(value).replace(/^(.*?) 第 (\d+) 行$/,(_,sheet,row)=>`${sheet} row ${row}`);
 const paths=value=>String(value).split(/([/.,\[\]\s]+)/).map(part=>label(part)).join('');
 function translate(value,depth=0){
  const raw=String(value??'');
  if(own(fixed,raw))return fixed[raw];
  if(depth>8)return raw;
  for(const [pattern,replacer] of patterns){if(pattern.test(raw))return raw.replace(pattern,(...args)=>replacer(args,depth));}
  return raw;
 }
 function parameter(value,mode,depth){
  if(mode==='label')return label(value);
  if(mode==='labels')return labels(value);
  if(mode==='location')return location(value);
  if(mode==='paths')return paths(value);
  if(mode==='condition')return ({'大于零':'greater than zero','非负':'non-negative'})[value]||value;
  if(mode==='message')return translate(value,depth+1);
  return value;
 }
 for(const definition of root.BACKEND_EN_MESSAGE_DEFINITIONS){
  const {zh,en}=definition;
  if(!/\{\d+\}/.test(zh)){fixed[zh]=en;continue;}
  const ids=[],source=zh.split(/(\{\d+\})/).map(part=>{
   const slot=part.match(/^\{(\d+)\}$/);
   if(slot){ids.push(slot[1]);return '([\\s\\S]*?)';}
   return part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  }).join('');
  const expression=new RegExp('^'+source+'$');
  const render=(args,depth)=>{
   const captured={};ids.forEach((id,index)=>{captured[id]=parameter(args[index+1],definition.parameters?.[id],depth);});
   return en.replace(/\{(\d+)\}/g,(_,id)=>captured[id]??'');
  };
  patterns.push([expression,render,(zh.startsWith('{')?0:1000)+zh.replace(/\{\d+\}/g,'').length]);
 }
 patterns.sort((a,b)=>b[2]-a[2]);
 // Pydantic prepends this fixed English prefix to custom ValueError messages.
 patterns.unshift([/^Value error, ([\s\S]*)$/,(args,depth)=>`Validation error: ${translate(args[1],depth+1)}`]);
 root.SYSTEM_EN=Object.assign(root.SYSTEM_EN||{},fixed);
 root.SYSTEM_EN_PATTERNS=root.SYSTEM_EN_PATTERNS||[];
 for(const [pattern,replacer] of patterns)root.SYSTEM_EN_PATTERNS.push([pattern,(...args)=>replacer(args,0)]);
 root.translateBackendMessage=function(value){return typeof state!=='undefined'&&state.language==='en'?translate(value):String(value??'');};
 root.translateBackendFieldLabel=label;

 // Audit summaries contain unquoted user text; punctuation is not a safe parser.
 // The current API supplies structured before/after payloads. Rebuild the display
 // from those values instead of substituting inside user-authored notes or names.
 const auditField=part=>{
  const identity=String(part).match(/^([^:]+):(.*)$/s);
  return identity?`${label(identity[1])}:${identity[2]}`:label(part);
 };
 const auditValue=value=>{
  if(value===null||value===undefined||value==='')return 'Blank';
  if(typeof value==='string')return JSON.stringify(value);
  if(typeof value==='boolean')return value?'True':'False';
  if(Array.isArray(value))return '['+value.map(auditValue).join(', ')+']';
  if(typeof value==='object')return '{'+Object.entries(value).map(([key,val])=>JSON.stringify(label(key))+': '+auditValue(val)).join(', ')+'}';
  return String(value);
 };
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const identity=(value,index)=>{
  if(value&&typeof value==='object'&&!Array.isArray(value)){
   for(const key of ['id','日期','date','月份','month','name','名称','菜品名称'])if(value[key]!==null&&value[key]!==undefined&&value[key]!=='')return key+':'+String(value[key]);
  }
  return '#'+index;
 };
 root.translateAuditSummary=function(summary,item){
  const raw=String(summary??'');
  if(typeof state==='undefined'||state.language!=='en')return raw;
  if(item&&own(item,'before_payload')&&own(item,'after_payload')){
   const changes=[],ignored=new Set(['updated_at','created_at','checksum','version','sequence']);
   const description=path=>path.filter(part=>part!==''&&!/^\d+$/.test(String(part))).slice(-3).map(auditField).join(' · ')||'Ledger contents';
   function walk(before,after,path,depth=0){
    if(changes.length>=20||same(before,after))return;
    const caption=description(path);
    if(depth>25){changes.push(`Changed ${caption}: ${auditValue(before)} → ${auditValue(after)}`);return;}
    if(before&&after&&typeof before==='object'&&typeof after==='object'&&!Array.isArray(before)&&!Array.isArray(after)){
     for(const key of [...new Set([...Object.keys(before),...Object.keys(after)])].sort()){
      if(ignored.has(key))continue;
      walk(own(before,key)?before[key]:undefined,own(after,key)?after[key]:undefined,[...path,key],depth+1);
     }
     return;
    }
    if(Array.isArray(before)&&Array.isArray(after)){
     const oldMap=new Map(before.map((value,index)=>[identity(value,index),value]));
     const newMap=new Map(after.map((value,index)=>[identity(value,index),value]));
     for(const key of [...new Set([...oldMap.keys(),...newMap.keys()])].sort())walk(oldMap.get(key),newMap.get(key),[...path,key],depth+1);
     return;
    }
    if(before===undefined||before===null||before==='')changes.push(`Added ${caption}: ${auditValue(after)}`);
    else if(after===undefined)changes.push(`Removed ${caption}: ${auditValue(before)}`);
    else if(after===null||after==='')changes.push(`Cleared ${caption}: ${auditValue(before)} → Blank`);
    else changes.push(`Changed ${caption}: ${auditValue(before)} → ${auditValue(after)}`);
   }
   walk(item.before_payload??{},item.after_payload??{},[]);
   const reason=item.reason?`${item.action==='name_correction_reindex'?'Item-name correction (source ordering preserved)':'Item-name correction'}: ${String(item.reason)}; `:'';
   return reason+(changes.join('; ')||'No actual data changes.');
  }
  const exact=translate(raw);if(exact!==raw)return exact;
  // Older API responses without payloads: preserve the opaque tail rather than
  // guessing which unescaped punctuation or words came from a user.
  return raw.replace(/^(增加|删除|修改|清空) /,(_,verb)=>({增加:'Added',删除:'Removed',修改:'Changed',清空:'Cleared'})[verb]+' ');
 };
})();
