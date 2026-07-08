#!/usr/bin/env python3
"""Source-checkout shim for the `satmap` CLI (see satchange/make_map.py).

Run `python3 make_map.py ...` from a clone, or use the `satmap` command after
`pip install satchange`.
"""

from satchange.make_map import main

if __name__ == "__main__":
    main()
