# FIFO verification contract

The cross-client FIFO contract is in `build/test_fifo_contract.py`. It compares FIFO costs and batch allocations between the web and desktop implementations, then checks quantity balances against the API. All three use the same receipt and issue fixtures, including this example:

- 9 October: 9 jin at 20 yuan, issue 8 jin, leave 1 jin.
- 10 October: 10 jin at 15 yuan, issue 3 jin.
- The second issue consumes 1 jin × 20 yuan and 2 jin × 15 yuan: 50 yuan total, 16.67 yuan average.

After installing the test and desktop dependencies and rebuilding the web scripts as described in the README, run `python build/test_fifo_contract.py` from the repository root. The fixtures are created in memory; the contract does not connect to a production API or write ledger records.
