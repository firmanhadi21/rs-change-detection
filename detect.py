#!/usr/bin/env python3
"""Source-checkout shim for the `satchange` CLI.

The real code lives in the `satchange` package (satchange/detect.py). This lets
you run `python3 detect.py ...` from a clone without installing. After
`pip install satchange` you can use the `satchange` command instead.
"""

from satchange.detect import main

if __name__ == "__main__":
    main()
