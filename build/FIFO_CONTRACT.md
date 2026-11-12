# Verifying first-in, first-out (FIFO) stock costs

**[← Back to the English README](../README.en.md)** · [简体中文](FIFO_CONTRACT.zh-CN.md) · [Engineering Reference](../docs/ENGINEERING_REFERENCE.md#calculations)

The [FIFO regression test](test_fifo_contract.py) runs the same stock movements through the web and macOS implementations. It compares the cost of each issue, the quantity drawn from each lot, and the remaining stock. It also checks the closing quantities against the API’s stock calculation.

## Example with two purchase prices

The example uses pork measured in *jin* (斤), the unit recorded in the test ledger. All prices are in CNY.

| Date | Stock received | Stock issued | Closing stock |
| --- | --- | --- | --- |
| October 9 | 9 jin at CNY 20 per jin | 8 jin from the October 9 lot | 1 jin |
| October 10 | 10 jin at CNY 15 per jin | 1 jin from October 9 and 2 jin from October 10 | 8 jin |

The October 10 issue costs **CNY 50.00** (1 × 20 + 2 × 15). Its displayed average unit cost is **CNY 16.67 per jin** (50 ÷ 3). The 8 jin left in stock all belong to the October 10 lot and have a book value of **CNY 120.00**.

## Running the check

Follow the [README test instructions](../README.en.md#running-the-tests) to install the test and desktop dependencies and rebuild the web scripts. From the repository root, run the command below. It creates the test records in memory and calls the API’s quantity calculation locally.

```bash
python build/test_fifo_contract.py
```
