from datetime import datetime, timedelta, timezone
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import config
from app.store_settings import payment_status, validate_and_save_wechat_files
from app.wechat_pay import WeChatPayError
from app.wechat_sync import recalc_revenue_breakdown


# Local-only placeholders: mchid must pass the numeric-format check, so use an
# all-zero value instead of a realistic merchant identifier. These are not
# credentials. Every certificate/key below is generated in memory for the test;
# monkeypatch redirects saved files to pytest's temporary directory.
TEST_MCHID = "0" * 10
TEST_PUBLIC_KEY_ID = "PUB_KEY_ID_TEST_ONLY"


def _pair_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "merchant-test")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key, cert, private_pem, cert_pem


def test_store_wechat_upload_validates_and_does_not_expose_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAYMENT_SECRET_ROOT", str(tmp_path))
    _merchant_key, cert, private_pem, cert_pem = _pair_and_cert()
    wechat_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wechat_pub = wechat_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    status = validate_and_save_wechat_files(
        "dataset-1", "A", mchid=TEST_MCHID, public_key_id=TEST_PUBLIC_KEY_ID,
        cert_bytes=cert_pem, private_key_bytes=private_pem, public_key_bytes=wechat_pub,
        p12_bytes=b"optional", readme_bytes=b"optional readme",
    )
    assert status["configured"] is True
    assert status["merchant_serial_no"] == format(cert.serial_number, "X")
    assert status["files"]["apiclient_key.pem"] is True
    assert "private" not in status
    assert payment_status("dataset-1", "A")["mchid"] == TEST_MCHID


def test_store_wechat_upload_rejects_mismatched_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAYMENT_SECRET_ROOT", str(tmp_path))
    _key, _cert, _private_pem, cert_pem = _pair_and_cert()
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_private = wrong_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = wrong_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with pytest.raises(WeChatPayError, match="不配套"):
        validate_and_save_wechat_files(
            "dataset-1", "A", mchid=TEST_MCHID, public_key_id=TEST_PUBLIC_KEY_ID,
            cert_bytes=cert_pem, private_key_bytes=wrong_private, public_key_bytes=pub,
        )


def test_manual_payment_override_wins_and_auto_plus_add_is_default():
    row = {
        "A店现金": 100,
        "A店微信自动": 300,
        "A店微信增加": 20,
        "A店微信覆盖": "",
        "A店支付宝增加": 50,
        "A店支付宝覆盖": 40,
        "B店现金": 80,
        "B店微信自动": 200,
        "B店微信增加": 10,
        "B店微信覆盖": 180,
        "B店支付宝增加": 30,
        "B店支付宝覆盖": "",
    }
    recalc_revenue_breakdown(row)
    assert row["A店收入"] == "460.00"
    assert row["B店收入"] == "290.00"
    assert row["收益"] == "750.00"
