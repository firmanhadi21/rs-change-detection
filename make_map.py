#!/usr/bin/env python3
"""Source-checkout shim for the `earthmap` CLI (see earthchange/make_map.py).

Run `python3 make_map.py ...` from a clone, or use the `earthmap` command after
`pip install earthchange`.
"""

from earthchange.make_map import main

if __name__ == "__main__":
    main()
