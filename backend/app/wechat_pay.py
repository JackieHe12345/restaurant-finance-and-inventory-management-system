from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


from .money import money, money_text as _exact_money_text


API_HOST = "https://api.mch.weixin.qq.com"


class WeChatPayError(RuntimeError):
    def __init__(self, message: str, *, code: str = "", status_code: int = 0):
        super().__init__(message)
        self.code = str(code or "")
        self.status_code = int(status_code or 0)


@dataclass(frozen=True)
class WeChatMerchantConfig:
    mchid: str
    merchant_serial_no: str
    private_key_path: str
    public_key_id: str
    public_key_path: str

    def validate(self) -> None:
        values = {
            "微信支付商户号": self.mchid,
            "商户 API 证书序列号": self.merchant_serial_no,
            "商户私钥路径": self.private_key_path,
            "微信支付公钥 ID": self.public_key_id,
            "微信支付公钥路径": self.public_key_path,
        }
        missing = [name for name, value in values.items() if not str(value or "").strip()]
        if missing:
            raise WeChatPayError("微信支付配置不完整：" + "、".join(missing))
        for label, path in (("商户私钥", self.private_key_path), ("微信支付公钥", self.public_key_path)):
            if not Path(path).is_file():
                raise WeChatPayError(f"{label}文件不存在：{path}")


@dataclass
class BillTotals:
    order_amount: Decimal = Decimal("0")
    requested_refund_amount: Decimal = Decimal("0")
    settlement_amount: Decimal = Decimal("0")
    settlement_refund_amount: Decimal = Decimal("0")
    fee_amount: Decimal = Decimal("0")
    detail_count: int = 0
    payment_count: int = 0
    refund_count: int = 0

    @property
    def order_net(self) -> Decimal:
        return self.order_amount - self.requested_refund_amount

    @property
    def settlement_net(self) -> Decimal:
        return self.settlement_amount - self.settlement_refund_amount


@dataclass
class TradeBill:
    bill_date: str
    rows: list[dict[str, str]]
    totals: BillTotals
    sha1: str = ""


def _clean_cell(value: Any) -> str:
    text = str(value or "").replace("\ufeff", "").strip()
    return text[1:].strip() if text.startswith("`") else text


def money_text(value: Any) -> str:
    try:
        return _exact_money_text(value, limit=None)
    except ValueError as exc:
        raise WeChatPayError(f"金额无效：{exc}") from exc


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise WeChatPayError("微信账单金额不能是布尔值。")
    text = _clean_cell(value).replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return money(text)
    except ValueError as exc:
        raise WeChatPayError(f"微信账单金额无效：{exc}") from exc


def parse_trade_bill(content: bytes | str, bill_date: str = "") -> TradeBill:
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig")
    else:
        text = str(content).lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header_index = None
    header: list[str] = []
    for index, row in enumerate(rows):
        cleaned = [_clean_cell(value) for value in row]
        if "交易时间" in cleaned and "微信订单号" in cleaned and "商户号" in cleaned:
            header_index = index
            header = cleaned
            break
    if header_index is None:
        raise WeChatPayError("微信交易账单格式无法识别：未找到交易明细表头。")

    details: list[dict[str, str]] = []
    for raw_row in rows[header_index + 1 :]:
        cleaned = [_clean_cell(value) for value in raw_row]
        if not any(cleaned):
            if details:
                break
            continue
        first = cleaned[0] if cleaned else ""
        if first in {"总交易单数", "总交易单数（笔）"} or first.startswith("总交易单数"):
            break
        # Summary rows have a different width; malformed details are not allowed to
        # shift columns silently because that could corrupt store allocation.
        if len(cleaned) != len(header):
            if details:
                break
            continue
        record = dict(zip(header, cleaned))
        if record.get("交易时间"):
            details.append(record)

    totals = BillTotals(detail_count=len(details))
    for row in details:
        totals.order_amount += _decimal(row.get("订单金额"))
        totals.requested_refund_amount += _decimal(row.get("申请退款金额"))
        totals.settlement_amount += _decimal(row.get("应结订单金额") or row.get("总金额"))
        totals.settlement_refund_amount += _decimal(row.get("退款金额"))
        totals.fee_amount += _decimal(row.get("手续费"))
        status = str(row.get("交易状态") or "").upper()
        if _decimal(row.get("订单金额")) > 0 or status == "SUCCESS":
            totals.payment_count += 1
        if _decimal(row.get("申请退款金额")) > 0 or str(row.get("微信退款单号") or "").strip():
            totals.refund_count += 1
    # Per-row inputs are capped by _decimal; an aggregate is allowed to
    # exceed the per-transaction limit without truncation or float conversion.
    for field in ("order_amount", "requested_refund_amount", "settlement_amount", "settlement_refund_amount", "fee_amount"):
        setattr(totals, field, Decimal(money_text(getattr(totals, field))))
    return TradeBill(bill_date=bill_date, rows=details, totals=totals)


def amount_for_row(row: dict[str, str], mode: str = "order") -> Decimal:
    if str(mode).lower() == "settlement":
        return _decimal(row.get("应结订单金额") or row.get("总金额")) - _decimal(row.get("退款金额"))
    return _decimal(row.get("订单金额")) - _decimal(row.get("申请退款金额"))


def summarize_rows(rows: list[dict[str, str]], *, mode: str = "order") -> dict[str, Any]:
    amount = Decimal("0")
    payment_amount = Decimal("0")
    refund_amount = Decimal("0")
    payment_count = 0
    refund_count = 0
    for row in rows:
        row_order = _decimal(row.get("订单金额"))
        row_refund = _decimal(row.get("申请退款金额"))
        amount += amount_for_row(row, mode)
        payment_amount += row_order
        refund_amount += row_refund
        if row_order > 0:
            payment_count += 1
        if row_refund > 0:
            refund_count += 1
    return {
        "amount": money_text(amount),
        "payment_amount": money_text(payment_amount),
        "refund_amount": money_text(refund_amount),
        "payment_count": payment_count,
        "refund_count": refund_count,
        "detail_count": len(rows),
    }


def split_rows_by_store(
    rows: list[dict[str, str]],
    *,
    a_device_ids: set[str] | None = None,
    b_device_ids: set[str] | None = None,
    unmatched_store: str = "ERROR",
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    a_ids = {str(value).strip() for value in (a_device_ids or set()) if str(value).strip()}
    b_ids = {str(value).strip() for value in (b_device_ids or set()) if str(value).strip()}
    overlap = a_ids & b_ids
    if overlap:
        raise WeChatPayError("A店/B店设备号配置重复：" + "、".join(sorted(overlap)))
    fallback = str(unmatched_store or "ERROR").strip().upper()
    if fallback not in {"A", "B", "IGNORE", "ERROR"}:
        raise WeChatPayError("WECHAT_UNMATCHED_STORE 只能是 A、B、IGNORE 或 ERROR。")

    store_a: list[dict[str, str]] = []
    store_b: list[dict[str, str]] = []
    unmatched: list[dict[str, str]] = []
    for row in rows:
        device_id = str(row.get("设备号") or "").strip()
        if device_id and device_id in a_ids:
            store_a.append(row)
        elif device_id and device_id in b_ids:
            store_b.append(row)
        elif fallback == "A":
            store_a.append(row)
        elif fallback == "B":
            store_b.append(row)
        elif fallback == "IGNORE":
            unmatched.append(row)
        else:
            unmatched.append(row)
    if unmatched and fallback == "ERROR":
        sample = sorted({str(row.get("设备号") or "（空设备号）") for row in unmatched})[:8]
        raise WeChatPayError(
            "微信账单中存在无法归属 A店/B店 的交易。请配置 WECHAT_A_DEVICE_IDS / "
            "WECHAT_B_DEVICE_IDS，或明确设置 WECHAT_UNMATCHED_STORE。示例设备号："
            + "、".join(sample)
        )
    return store_a, store_b, unmatched


class WeChatPayClient:
    def __init__(self, merchant: WeChatMerchantConfig, *, timeout: float = 20.0):
        merchant.validate()
        self.merchant = merchant
        self.timeout = max(3.0, float(timeout))
        try:
            self._private_key = serialization.load_pem_private_key(
                Path(merchant.private_key_path).read_bytes(), password=None
            )
        except Exception as exc:
            raise WeChatPayError(f"无法读取商户私钥：{exc}") from exc
        try:
            self._public_key = serialization.load_pem_public_key(
                Path(merchant.public_key_path).read_bytes()
            )
        except Exception as exc:
            raise WeChatPayError(f"无法读取微信支付公钥：{exc}") from exc

    @staticmethod
    def _request_target(url: str) -> str:
        parsed = urlsplit(url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    def _authorization(self, method: str, url: str, body: bytes = b"") -> str:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        body_text = body.decode("utf-8") if body else ""
        message = f"{method.upper()}\n{self._request_target(url)}\n{timestamp}\n{nonce}\n{body_text}\n"
        signature = self._private_key.sign(
            message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode("ascii")
        return (
            'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.merchant.mchid}",nonce_str="{nonce}",'
            f'signature="{signature_b64}",timestamp="{timestamp}",'
            f'serial_no="{self.merchant.merchant_serial_no}"'
        )

    def _verify_response(self, headers: Any, body: bytes) -> None:
        timestamp = str(headers.get("Wechatpay-Timestamp") or "")
        nonce = str(headers.get("Wechatpay-Nonce") or "")
        signature_b64 = str(headers.get("Wechatpay-Signature") or "")
        serial = str(headers.get("Wechatpay-Serial") or "")
        if not timestamp or not nonce or not signature_b64:
            raise WeChatPayError("微信支付响应缺少验签请求头。")
        if serial and serial != self.merchant.public_key_id:
            raise WeChatPayError(
                f"微信支付响应公钥ID不匹配：收到 {serial}，配置为 {self.merchant.public_key_id}。"
            )
        message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
        try:
            signature = base64.b64decode(signature_b64)
            self._public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        except (ValueError, InvalidSignature) as exc:
            raise WeChatPayError("微信支付响应签名验证失败。") from exc

    def _request(self, method: str, url: str, *, verify_response: bool = True) -> tuple[bytes, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization(method, url),
            "User-Agent": "RestaurantFinance/25",
        }
        request = Request(url, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content = response.read()
                response_headers = response.headers
        except HTTPError as exc:
            raw = exc.read()
            code = ""
            detail = ""
            try:
                payload = json.loads(raw.decode("utf-8"))
                code = str(payload.get("code") or "")
                detail = str(payload.get("message") or "")
            except Exception:
                detail = raw.decode("utf-8", errors="replace")[:300]
            raise WeChatPayError(
                f"微信支付 API 请求失败（HTTP {exc.code}）{f' {code}' if code else ''}：{detail or exc.reason}",
                code=code,
                status_code=exc.code,
            ) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise WeChatPayError(f"无法连接微信支付 API：{exc}") from exc
        if verify_response:
            self._verify_response(response_headers, content)
        return content, response_headers

    def request_trade_bill(self, bill_date: str | date) -> TradeBill:
        day = bill_date.isoformat() if isinstance(bill_date, date) else str(bill_date)
        query = urlencode({"bill_date": day, "bill_type": "ALL"})
        url = f"{API_HOST}/v3/bill/tradebill?{query}"
        try:
            content, _ = self._request("GET", url, verify_response=True)
        except WeChatPayError as exc:
            if exc.code == "NO_STATEMENT_EXIST":
                return TradeBill(day, [], BillTotals(), "")
            raise
        try:
            payload = json.loads(content.decode("utf-8"))
            download_url = str(payload["download_url"])
            expected_hash = str(payload["hash_value"]).lower()
            hash_type = str(payload.get("hash_type") or "SHA1").upper()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WeChatPayError("微信支付申请账单响应格式不正确。") from exc
        if hash_type != "SHA1":
            raise WeChatPayError(f"暂不支持微信账单哈希类型：{hash_type}")
        bill_bytes, _ = self._request("GET", download_url, verify_response=False)
        actual_hash = hashlib.sha1(bill_bytes).hexdigest().lower()
        if actual_hash != expected_hash:
            raise WeChatPayError("微信交易账单 SHA1 校验失败，已拒绝写入收入。")
        bill = parse_trade_bill(bill_bytes, day)
        bill.sha1 = actual_hash
        return bill


def env_csv(name: str) -> set[str]:
    return {item.strip() for item in os.environ.get(name, "").split(",") if item.strip()}


def merchant_from_env(prefix: str = "WECHAT") -> WeChatMerchantConfig | None:
    prefix = prefix.rstrip("_")
    values = {
        "mchid": os.environ.get(f"{prefix}_MCH_ID", "").strip(),
        "merchant_serial_no": os.environ.get(f"{prefix}_MERCHANT_SERIAL_NO", "").strip(),
        "private_key_path": os.environ.get(f"{prefix}_PRIVATE_KEY_PATH", "").strip(),
        "public_key_id": os.environ.get(f"{prefix}_PUBLIC_KEY_ID", "").strip(),
        "public_key_path": os.environ.get(f"{prefix}_PUBLIC_KEY_PATH", "").strip(),
    }
    if not any(values.values()):
        return None
    return WeChatMerchantConfig(**values)
