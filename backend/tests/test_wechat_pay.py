from decimal import Decimal

import pytest

from app.wechat_pay import (
    WeChatPayError,
    amount_for_row,
    parse_trade_bill,
    split_rows_by_store,
    summarize_rows,
)


HEADER = [
    "交易时间", "公众账号ID", "商户号", "特约商户号", "设备号", "微信订单号", "商户订单号",
    "用户标识", "交易类型", "交易状态", "付款银行", "货币种类", "应结订单金额", "代金券金额",
    "微信退款单号", "商户退款单号", "退款金额", "充值券退款金额", "退款类型", "退款状态",
    "商品名称", "商户数据包", "手续费", "费率", "订单金额", "申请退款金额", "费率备注",
]

# Synthetic CSV fixture identifier only; this is not a real merchant account.
TEST_MCHID = "0" * 10


def line(values):
    return ",".join("`" + str(value) for value in values)


def sample_bill():
    payment_a = [
        "2026-08-24 10:00:00", "wx1", TEST_MCHID, "0", "A001", "wxorder1", "order1", "openid1",
        "MICROPAY", "SUCCESS", "OTHERS", "CNY", "100.00", "0.00", "0", "0", "0.00", "0.00", "", "",
        "午餐", "", "0.60", "0.60%", "100.00", "0.00", "",
    ]
    payment_b = [
        "2026-08-24 11:00:00", "wx1", TEST_MCHID, "0", "B001", "wxorder2", "order2", "openid2",
        "MICROPAY", "SUCCESS", "OTHERS", "CNY", "50.00", "0.00", "0", "0", "0.00", "0.00", "", "",
        "午餐", "", "0.30", "0.60%", "50.00", "0.00", "",
    ]
    refund_a = [
        "2026-08-24 16:00:00", "wx1", TEST_MCHID, "0", "A001", "wxorder1", "order1", "openid1",
        "MICROPAY", "REFUND", "OTHERS", "CNY", "0.00", "0.00", "refund1", "refund-order1", "20.00", "0.00",
        "ORIGINAL", "SUCCESS", "午餐", "", "-0.12", "0.60%", "0.00", "20.00", "",
    ]
    return "\n".join([
        line(HEADER),
        line(payment_a),
        line(payment_b),
        line(refund_a),
        "",
        line(["总交易单数", "应结订单总金额", "退款总金额", "充值券退款总金额", "手续费总金额", "订单总金额", "申请退款总金额"]),
        line(["3", "150.00", "20.00", "0.00", "0.78", "150.00", "20.00"]),
    ])


def test_parse_and_order_net():
    bill = parse_trade_bill(sample_bill(), "2026-08-24")
    assert len(bill.rows) == 3
    assert bill.totals.order_amount == Decimal("150.00")
    assert bill.totals.requested_refund_amount == Decimal("20.00")
    assert bill.totals.order_net == Decimal("130.00")
    summary = summarize_rows(bill.rows, mode="order")
    assert summary["amount"] == "130.00"
    assert summary["payment_amount"] == "150.00"
    assert summary["refund_amount"] == "20.00"
    assert summary["payment_count"] == 2
    assert summary["refund_count"] == 1


def test_split_by_device_and_refund_stays_with_store():
    bill = parse_trade_bill(sample_bill(), "2026-08-24")
    a_rows, b_rows, unmatched = split_rows_by_store(
        bill.rows,
        a_device_ids={"A001"},
        b_device_ids={"B001"},
        unmatched_store="ERROR",
    )
    assert not unmatched
    assert summarize_rows(a_rows)["amount"] == "80.00"
    assert summarize_rows(b_rows)["amount"] == "50.00"


def test_unmatched_device_fails_closed():
    bill = parse_trade_bill(sample_bill(), "2026-08-24")
    with pytest.raises(WeChatPayError):
        split_rows_by_store(
            bill.rows,
            a_device_ids={"A001"},
            b_device_ids=set(),
            unmatched_store="ERROR",
        )


def test_settlement_mode_uses_settlement_fields():
    row = {"应结订单金额": "`10.00", "退款金额": "`3.00", "订单金额": "`12.00", "申请退款金额": "`4.00"}
    assert amount_for_row(row, "settlement") == Decimal("7.00")
    assert amount_for_row(row, "order") == Decimal("8.00")
