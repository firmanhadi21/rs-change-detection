# Publishing `satchange` to PyPI

The package lives in [`satchange/`](satchange/) and is configured by
[`pyproject.toml`](pyproject.toml). These steps build and upload it. **Nothing
here uploads automatically** — you run the final step with your own PyPI token.

## 0. One-time prerequisites

```bash
pip install --upgrade build twine
```

- Create accounts on **[TestPyPI](https://test.pypi.org/)** and **[PyPI](https://pypi.org/)**.
- Create an **API token** for each (Account → API tokens). You'll paste it as the
  password with username `__token__`.
- **Check the name is free:** https://pypi.org/project/satchange/ must 404.
  If taken, change `name = "..."` in `pyproject.toml` (the import package
  `satchange/` can keep its name, but the PyPI distribution name must be unique).

## 1. Build the distributions

```bash
python -m build          # writes dist/satchange-0.1.0.tar.gz and .whl
python -m twine check dist/*
```

## 2. Test on TestPyPI first

```bash
python -m twine upload --repository testpypi dist/*
# then try installing it in a clean venv:
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple 'satchange[all]'
satchange --list
```

## 3. Upload to the real PyPI

```bash
python -m twine upload dist/*
```

Then anyone can:

```bash
pip install 'satchange[gee]'      # Earth Engine backend
pip install 'satchange[mpc,maps]' # Planetary Computer + maps, no GEE account
pip install 'satchange[all]'      # everything
satchange -s deforestation --lat -3.333 --lon 122.25 --map
```

## Cutting a new version

1. Bump `version` in `pyproject.toml` (PyPI versions are immutable — you can't
   re-upload the same one).
2. Rebuild (`rm -rf dist && python -m build`) and re-upload.
3. Tag the release: `git tag v0.1.0 && git push --tags`.

## Notes

- **Extras** keep the install lean: core is tiny (`requests`); `gee`, `mpc`,
  `maps` pull only what that path needs.
- The Capkala investigation (`data-collection/`, `scripts/`, `narration/`,
  `images/`) is **not** shipped in the wheel — only the `satchange/` package is.
- Outputs are written to `./output/<run-id>/` in the current directory, and the
  GEE service-account key (if used) is read from `./scripts/config/ee-geodetic.json`
  or `~/.config/earthengine/` — never bundled.
