from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from . import config
from .wechat_pay import WeChatMerchantConfig, WeChatPayError


STORE_SLOTS = {"A", "B"}


def _safe_dataset_id(dataset_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(dataset_id or "").strip())
    if not value:
        raise WeChatPayError("账本 ID 不能为空。")
    return value[:120]


def dataset_secret_dir(dataset_id: str) -> Path:
    root = Path(config.PAYMENT_SECRET_ROOT).expanduser().resolve()
    path = root / _safe_dataset_id(dataset_id)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def store_secret_dir(dataset_id: str, store: str) -> Path:
    slot = str(store or "").strip().upper()
    if slot not in STORE_SLOTS:
        raise WeChatPayError("店铺槽位只能是 A 或 B。")
    path = dataset_secret_dir(dataset_id) / slot
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def _meta_path(dataset_id: str, store: str) -> Path:
    return store_secret_dir(dataset_id, store) / "merchant.json"


def load_store_payment_meta(dataset_id: str, store: str) -> dict[str, Any]:
    path = _meta_path(dataset_id, store)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_and_save_wechat_files(
    dataset_id: str,
    store: str,
    *,
    mchid: str,
    public_key_id: str,
    cert_bytes: bytes,
    private_key_bytes: bytes,
    public_key_bytes: bytes,
    p12_bytes: bytes | None = None,
    readme_bytes: bytes | None = None,
) -> dict[str, Any]:
    mchid = str(mchid or "").strip()
    public_key_id = str(public_key_id or "").strip()
    if not re.fullmatch(r"\d{6,32}", mchid):
        raise WeChatPayError("微信支付商户号格式不正确，应为纯数字。")
    if not public_key_id.startswith("PUB_KEY_ID_"):
        raise WeChatPayError("微信支付公钥 ID 格式不正确，应以 PUB_KEY_ID_ 开头。")
    if not cert_bytes or not private_key_bytes or not public_key_bytes:
        raise WeChatPayError("必须上传 apiclient_cert.pem、apiclient_key.pem 和 pub_key.pem。")

    try:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except Exception as exc:
        raise WeChatPayError(f"apiclient_cert.pem 无法解析：{exc}") from exc
    try:
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
    except Exception as exc:
        raise WeChatPayError(f"apiclient_key.pem 无法解析：{exc}") from exc
    try:
        public_key = serialization.load_pem_public_key(public_key_bytes)
    except Exception as exc:
        raise WeChatPayError(f"pub_key.pem 无法解析：{exc}") from exc

    try:
        cert_public = cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except Exception as exc:
        raise WeChatPayError(f"无法检查商户证书与私钥：{exc}") from exc
    if cert_public != private_public:
        raise WeChatPayError("apiclient_cert.pem 与 apiclient_key.pem 不配套，已拒绝保存。")

    # Force public-key parsing now so a malformed WeChat Pay key never reaches a scheduled job.
    try:
        _ = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except Exception as exc:
        raise WeChatPayError(f"微信支付公钥无法使用：{exc}") from exc

    serial = format(cert.serial_number, "X")
    folder = store_secret_dir(dataset_id, store)
    _atomic_write(folder / "apiclient_cert.pem", cert_bytes)
    _atomic_write(folder / "apiclient_key.pem", private_key_bytes)
    _atomic_write(folder / "pub_key.pem", public_key_bytes)
    if p12_bytes:
        _atomic_write(folder / "apiclient_cert.p12", p12_bytes)
    if readme_bytes:
        _atomic_write(folder / "README_CN.txt", readme_bytes)

    meta = {
        "mchid": mchid,
        "merchant_serial_no": serial,
        "public_key_id": public_key_id,
        "configured": True,
    }
    _atomic_write(
        folder / "merchant.json",
        json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return payment_status(dataset_id, store)


def payment_status(dataset_id: str, store: str) -> dict[str, Any]:
    folder = store_secret_dir(dataset_id, store)
    meta = load_store_payment_meta(dataset_id, store)
    configured = bool(
        meta.get("mchid")
        and meta.get("merchant_serial_no")
        and meta.get("public_key_id")
        and (folder / "apiclient_key.pem").is_file()
        and (folder / "pub_key.pem").is_file()
    )
    return {
        "configured": configured,
        "mchid": str(meta.get("mchid") or "") if configured else "",
        "merchant_serial_no": str(meta.get("merchant_serial_no") or "") if configured else "",
        "public_key_id": str(meta.get("public_key_id") or "") if configured else "",
        "files": {
            "apiclient_cert.pem": (folder / "apiclient_cert.pem").is_file(),
            "apiclient_key.pem": (folder / "apiclient_key.pem").is_file(),
            "pub_key.pem": (folder / "pub_key.pem").is_file(),
            "apiclient_cert.p12": (folder / "apiclient_cert.p12").is_file(),
            "README_CN.txt": (folder / "README_CN.txt").is_file(),
        },
    }


def merchant_for_store(dataset_id: str, store: str) -> WeChatMerchantConfig | None:
    folder = store_secret_dir(dataset_id, store)
    meta = load_store_payment_meta(dataset_id, store)
    if not meta:
        return None
    merchant = WeChatMerchantConfig(
        mchid=str(meta.get("mchid") or "").strip(),
        merchant_serial_no=str(meta.get("merchant_serial_no") or "").strip(),
        private_key_path=str(folder / "apiclient_key.pem"),
        public_key_id=str(meta.get("public_key_id") or "").strip(),
        public_key_path=str(folder / "pub_key.pem"),
    )
    try:
        merchant.validate()
    except WeChatPayError:
        return None
    return merchant


def delete_store_payment_config(dataset_id: str, store: str) -> None:
    folder = store_secret_dir(dataset_id, store)
    for name in (
        "merchant.json", "apiclient_cert.pem", "apiclient_key.pem", "pub_key.pem",
        "apiclient_cert.p12", "README_CN.txt",
    ):
        try:
            (folder / name).unlink()
        except FileNotFoundError:
            pass
