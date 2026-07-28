#!/usr/bin/env python3
"""Source-checkout shim for the `earthchange` CLI.

The real code lives in the `earthchange` package (earthchange/detect.py). This lets
you run `python3 detect.py ...` from a clone without installing. After
`pip install earthchange` you can use the `earthchange` command instead.
"""

from earthchange.detect import main

if __name__ == "__main__":
    main()
