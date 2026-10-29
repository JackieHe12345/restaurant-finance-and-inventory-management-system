from __future__ import annotations

import os


DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
CORS_ORIGINS = [
    item.strip()
    for item in os.environ.get("CORS_ORIGINS", "*").split(",")
    if item.strip()
]
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
TEST_LOGIN_ENABLED = os.environ.get("TEST_LOGIN_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TEST_USERNAME = os.environ.get("TEST_USERNAME", "test").strip() or "test"
TEST_DATASET_ID = os.environ.get("TEST_DATASET_ID", "test-demo-v1").strip() or "test-demo-v1"
TEST_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("TEST_ACCESS_TOKEN_EXPIRE_MINUTES", "120")
)
MAX_WORKBOOK_UPLOAD_BYTES = int(
    os.environ.get("MAX_WORKBOOK_UPLOAD_BYTES", str(25 * 1024 * 1024))
)

# 微信支付交易账单同步（v25）
WECHAT_AUTO_SYNC = os.environ.get("WECHAT_AUTO_SYNC", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
WECHAT_DATASET_ID = os.environ.get("WECHAT_DATASET_ID", "").strip()
WECHAT_SYNC_HOUR = int(os.environ.get("WECHAT_SYNC_HOUR", "10"))
# Product rule: the daily previous-day import runs at 10:31 Asia/Shanghai.
WECHAT_SYNC_MINUTE = 31
WECHAT_TIMEZONE = os.environ.get("WECHAT_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
WECHAT_AMOUNT_MODE = os.environ.get("WECHAT_AMOUNT_MODE", "order").strip().lower() or "order"
WECHAT_UNMATCHED_STORE = os.environ.get("WECHAT_UNMATCHED_STORE", "ERROR").strip().upper() or "ERROR"

# 每个账本、每家店独立保存的微信支付凭据目录（由网站上传）
PAYMENT_SECRET_ROOT = os.environ.get("PAYMENT_SECRET_ROOT", "/opt/restaurant-cloud/payment-secrets").strip() or "/opt/restaurant-cloud/payment-secrets"
