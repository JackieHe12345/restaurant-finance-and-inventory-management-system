"""Exact monetary arithmetic and schema-aware JSON boundaries.

Amounts are decimal strings; unchanged historical values retain their original
representation. Quantity/count/id/unknown extension fields are never money.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json
from typing import Any

CENT = Decimal('0.01')
PRICE_STEP = Decimal('0.000001')
MAX_ABS_AMOUNT = Decimal('999999999999.99')
MAX_ABS_PRICE = Decimal('999999999999.999999')
ZERO = Decimal('0')

class MoneyError(ValueError):
    pass

def decimal_value(value: Any, *, blank_zero: bool = True, limit: Decimal | None = MAX_ABS_AMOUNT) -> Decimal:
    if value is None or isinstance(value, str) and not value.strip():
        if blank_zero:
            return ZERO
        raise MoneyError('金额必须填写有效十进制数字。')
    if isinstance(value, bool):
        raise MoneyError('金额不能是布尔值。')
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (ValueError, InvalidOperation, TypeError):
        raise MoneyError('金额必须填写有效十进制数字。') from None
    if not result.is_finite() or (limit is not None and result.copy_abs() > limit):
        raise MoneyError('金额必须是有限数字，且整数部分不能超过 999999999999。')
    # Bound exponents/digits as well as magnitude, avoiding pathological inputs.
    if len(result.as_tuple().digits) > 100 or abs(result.as_tuple().exponent) > 100:
        raise MoneyError('金额精度超出允许范围。')
    return result

def money(value: Any, *, limit: Decimal | None = MAX_ABS_AMOUNT) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 256
        result = decimal_value(value, limit=limit).quantize(CENT, rounding=ROUND_HALF_UP)
    if limit is not None and result.copy_abs() > limit:
        raise MoneyError('金额超出允许范围。')
    return abs(result) if result == 0 else result

def money_text(value: Any, *, limit: Decimal | None = MAX_ABS_AMOUNT) -> str:
    return format(money(value, limit=limit), '.2f')

def price_text(value: Any) -> str:
    with localcontext() as ctx:
        ctx.prec = 256
        result = decimal_value(value, limit=MAX_ABS_PRICE).quantize(PRICE_STEP, rounding=ROUND_HALF_UP)
    if result.copy_abs() > MAX_ABS_PRICE:
        raise MoneyError('单价超出允许范围。')
    return format(abs(result) if result == 0 else result, '.6f')

def product(quantity: Any, unit_price: Any) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 256
        return money(decimal_value(quantity, limit=None) * decimal_value(unit_price, limit=MAX_ABS_PRICE))

def json_money(value: Any) -> Any:
    """Serialize computed monetary Decimals, leaving all non-Decimal values alone."""
    if isinstance(value, Decimal):
        return money_text(value, limit=None)
    if isinstance(value, dict):
        return {key: json_money(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_money(item) for item in value]
    return value

DAILY_MONEY = set('收益 总金额 收入 总收入 食材成本 佐料成本 水电 其他 其它 总现金 总线上 A店收入 B店收入 学生外卖 A店外卖 B店外卖 手续费 可用余额 向股东借款'.split())
for _slot in ('A店', 'B店'):
    DAILY_MONEY.update(_slot + suffix for suffix in ('现金', '微信增加', '微信自动', '微信覆盖', '支付宝增加', '支付宝覆盖', '微信支付金额', '微信退款金额'))
MONTH_MONEY = set('人工总额 房租总额 水费支出 电费支出 水电费 实际使用水费 实际使用电费 煤气费 其它固定成本 预计水费 预计电费 预计煤气费'.split())
DETAIL_MONEY = {'total', '总价', '金额', 'amount', 'cost', '成本', '总成本'}
PRICE_FIELDS = {'unit_price', 'unitPrice', 'price', '单价', '单位价'}
CASH_MONEY = set('opening_balance base_balance current_balance shareholder_loan amount 金额 income expense running_balance previous_month_balance target_balance force_balance'.split())
DETAIL_FIELDS = {'食材明细', '佐料明细', '其他明细', '其它明细'}
SCHEMA_FIELDS = {'daily': DAILY_MONEY, 'monthly_fixed': MONTH_MONEY, 'fixed_expenses': {'金额', 'amount'},
                 'dishes': {'总成本', 'cost', 'total_cost'}, '菜品数据': {'总成本', '成本', 'cost', 'total_cost', '单份成本'},
                 'detail': DETAIL_MONEY | PRICE_FIELDS,
                 'entries': DETAIL_MONEY | PRICE_FIELDS, 'adjustments': DETAIL_MONEY | PRICE_FIELDS,
                 'overrides': DETAIL_MONEY | PRICE_FIELDS, 'transactions': CASH_MONEY}

_MISSING = object()

def _same_amount(left, right, formatter):
    try:
        return formatter(left) == formatter(right)
    except MoneyError:
        return False

def _scalar(value, previous, key, *, aggregate=False):
    if value in (None, ''):
        return value
    if previous is not _MISSING and (type(value) is type(previous) or isinstance(previous, LegacyMoneyNumber)) and value == previous:
        return deepcopy(previous)
    formatter = price_text if key in PRICE_FIELDS else (lambda item: money_text(item, limit=None)) if aggregate else money_text
    normalized = formatter(value)
    if previous is not _MISSING and previous not in (None, '') and _same_amount(value, previous, formatter):
        return deepcopy(previous)
    return normalized

def _is_derived_money(key: str, row: dict, context: str) -> bool:
    if context != 'daily':
        return False
    def entered(field):
        return field in row and row[field] is not None and str(row[field]).strip() != ''
    channels = {slot: [slot + suffix for suffix in ('现金', '微信增加', '微信自动', '微信覆盖',
                   '支付宝增加', '支付宝覆盖', '外卖')] for slot in ('A店', 'B店')}
    if key in ('A店收入', 'B店收入'):
        return any(entered(field) for field in channels[key[:2]])
    if key == '总现金':
        return any(entered(field) for field in ('A店现金', 'B店现金'))
    if key == '总线上':
        return any(entered(field) for field in channels['A店'][1:] + channels['B店'][1:] + ['学生外卖'])
    if key in ('收益', '总金额', '收入', '总收入'):
        return any(entered(field) for field in channels['A店'] + channels['B店'] + ['学生外卖'])
    if key in ('食材成本', '佐料成本'):
        detail = row.get('食材明细' if key == '食材成本' else '佐料明细')
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                return bool(detail.strip())
        return isinstance(detail, (list, dict)) and bool(detail)
    return False


def _matched(items, previous):
    previous = previous if isinstance(previous, list) else []
    by_key = {}
    for old in previous:
        if isinstance(old, dict):
            key = next(((field, str(old[field])) for field in ('id', '日期', 'date', '月份', 'month') if old.get(field) not in (None, '')), None)
            if key:
                by_key[key] = old
    for index, item in enumerate(items):
        key = next(((field, str(item[field])) for field in ('id', '日期', 'date', '月份', 'month') if isinstance(item, dict) and item.get(field) not in (None, '')), None)
        yield item, by_key.get(key, _MISSING) if key else previous[index] if index < len(previous) else _MISSING

def _validate_detail_text(value: str) -> None:
    import re
    for token in re.split(r'[,，;；\n]+', value):
        body = re.split(r'\s+备注[:：]', token, maxsplit=1)[0].strip()
        body = re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', body).strip()
        if re.search(r'\s+[-+]?(?:nan|inf|infinity)\s*$', body, re.I):
            raise MoneyError('采购明细金额必须是有限数字。')
        match = re.search(r'\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$', body)
        if match:
            money_text(match.group(1))


def _container(value, previous, context, plain=None):
    if isinstance(value, str):
        if isinstance(previous, str) and value == previous:
            return previous
        if not value.lstrip().startswith(('[', '{')):
            if value != previous:
                _validate_detail_text(value)
            return value  # Plain detail text is already exact decimal text.
        try:
            parsed = json.loads(value, parse_float=Decimal, parse_int=int)
            plain = json.loads(value)
            if isinstance(previous, str):
                old = exact_request_numbers({context: json.loads(previous)},
                    {context: json.loads(previous, parse_float=Decimal)},
                    _number_factory=LegacyMoneyNumber)[context]
            else:
                old = previous
        except (ValueError, TypeError):
            _validate_detail_text(value)
            return value
        normalized = _node(parsed, old, context, plain)
        if isinstance(previous, str) and normalized == old:
            return previous
        if normalized == plain:
            return value
        return storage_json_dumps(normalized)
    return _node(value, previous, context, plain)

def _node(value, previous, context, plain=None):
    if isinstance(value, list):
        return [_node(item, old, context, plain[index] if isinstance(plain, list) and index < len(plain) else None)
                for index, (item, old) in enumerate(_matched(value, previous))]
    if not isinstance(value, dict):
        return deepcopy(plain if isinstance(value, Decimal) and plain is not None else value)
    previous = previous if isinstance(previous, dict) else {}
    known = SCHEMA_FIELDS.get(context, set())
    result = deepcopy(plain if isinstance(plain, dict) else value)
    for key, item in value.items():
        old = previous.get(key, _MISSING)
        if key in known:
            result[key] = _scalar(item, old, key, aggregate=_is_derived_money(key, value, context))
        elif key in DETAIL_FIELDS:
            result[key] = _container(item, old, 'detail', plain.get(key) if isinstance(plain, dict) else None)
        elif key == '菜品数据':
            result[key] = _container(item, old, key, plain.get(key) if isinstance(plain, dict) else None)
    return result

def normalize_payload(payload: Any, previous: Any = None) -> Any:
    if not isinstance(payload, dict):
        return deepcopy(payload)
    previous = previous if isinstance(previous, dict) else {}
    result = deepcopy(payload)
    # Bare legacy daily rows and root cash tables are both supported.
    for key in DAILY_MONEY | MONTH_MONEY | CASH_MONEY:
        if key in payload:
            result[key] = _scalar(payload[key], previous.get(key, _MISSING), key, aggregate=_is_derived_money(key, payload, "daily"))
    for key in DETAIL_FIELDS:
        if key in payload:
            result[key] = _container(payload[key], previous.get(key, _MISSING), 'detail')
    for key in SCHEMA_FIELDS:
        if key != 'detail' and key in payload:
            result[key] = _container(payload[key], previous.get(key, _MISSING), key)
    return result


def exact_request_numbers(plain: Any, precise: Any, *, _number_factory=str) -> Any:
    """Keep raw JSON monetary lexemes before request validation touches floats.

    Legacy JSON number inputs are accepted without losing their decimal digits.
    Non-money numbers are left to the existing API schema unchanged.
    """
    if not isinstance(plain, dict) or not isinstance(precise, dict):
        return plain
    result = deepcopy(plain)
    def overlay(node, raw, context):
        if isinstance(node, list) and isinstance(raw, list):
            return [overlay(v, raw[i], context) for i, v in enumerate(node)]
        if not isinstance(node, dict) or not isinstance(raw, dict):
            return node
        out = deepcopy(node)
        for key in SCHEMA_FIELDS.get(context, set()):
            if isinstance(raw.get(key), Decimal):
                out[key] = _number_factory(str(raw[key]))
        for key in DETAIL_FIELDS:
            if key in node and not isinstance(node[key], str):
                out[key] = overlay(node[key], raw.get(key), 'detail')
        if '菜品数据' in node and not isinstance(node['菜品数据'], str):
            out['菜品数据'] = overlay(node['菜品数据'], raw.get('菜品数据'), '菜品数据')
        return out
    for key in DAILY_MONEY | MONTH_MONEY | CASH_MONEY:
        if isinstance(precise.get(key), Decimal):
            result[key] = _number_factory(str(precise[key]))
    for key in SCHEMA_FIELDS:
        if key in plain and not isinstance(plain[key], str):
            result[key] = overlay(plain[key], precise.get(key), key)
    for key in DETAIL_FIELDS:
        if key in plain and not isinstance(plain[key], str):
            result[key] = overlay(plain[key], precise.get(key), 'detail')
    for key in ('payload', 'merged_payload'):
        if key in plain:
            result[key] = exact_request_numbers(plain[key], precise.get(key), _number_factory=_number_factory)
    if isinstance(plain.get('final_quantities'), list):
        result['final_quantities'] = overlay(plain['final_quantities'], precise['final_quantities'], 'detail')
    return result


def detail_for_comparison(item: Any) -> Any:
    """Canonical monetary tokens only; used to keep permission clocks stable."""
    import re
    if isinstance(item, dict):
        return _node(item, {}, 'detail')
    if not isinstance(item, str):
        return item
    note = re.search(r'\s+备注[:：]', item)
    end = note.start() if note else len(item)
    body = item[:end]
    match = re.search(r'(?<=\s)([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$', body)
    if match:
        return body[:match.start()] + money_text(match.group(1)) + item[end:]
    return item


class LegacyMoneyNumber(str):
    """Exact old JSON numeric token; serializers must preserve its numeric type."""


def storage_json_loads(text: str) -> Any:
    return exact_request_numbers(json.loads(text), json.loads(text, parse_float=Decimal), _number_factory=LegacyMoneyNumber)


def storage_json_dumps(value: Any, *, sort_keys: bool = False) -> str:
    """Recursive structural encoder, never placeholder/token text substitution."""
    if isinstance(value, LegacyMoneyNumber):
        import re
        if not re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?', value):
            raise MoneyError('历史金额数值格式无效。')
        return str(value)
    if isinstance(value, dict):
        keys = sorted(value) if sort_keys else value
        return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + storage_json_dumps(value[key], sort_keys=sort_keys) for key in keys) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(storage_json_dumps(item, sort_keys=sort_keys) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
