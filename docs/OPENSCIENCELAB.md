# Running the Flores InSAR stack in OpenScienceLab

A runbook for reproducing the ascending/descending analysis in ASF OpenScienceLab,
starting from HyP3 jobs that already exist.

The stack is 705 `INSAR_GAMMA` interferograms over Flores, Indonesia — 351
ascending, 354 descending, Aug 2022 to Aug 2026 — plus two look-vector jobs.
All are already processed and paid for; nothing here spends credits.

---

## Why not just use ASF's notebook

`a_Load_HyP3_Data.ipynb` lists one radio button per HyP3 job **name** and loads a
single "project". These jobs are named uniquely per interferogram so that
resubmitting is idempotent and never pays twice for the same pair — correct, but
it makes the stack appear as 705 projects instead of one. HyP3 names are fixed at
submission, so consolidating them would mean resubmitting all 705 (~7,050
credits).

`opensciencelab_fetch.py` selects by name **prefix** instead. Everything after
that is ordinary MintPy, and ASF's notebooks 4+ work normally on the result.

---

## 0. Prerequisites

**Use the MintPy kernel.** `opensarlab_mintpy_recipe_book` — the scripts call
`prep_hyp3.py`, `smallbaselineApp.py` and friends from `PATH`. Wrong kernel gives
a clear message rather than a traceback, but it wastes a step.

**Create `~/.cdsapirc` before you start.** ERA5 is downloaded by `pyaps3` roughly
two hours into the run, and a missing token fails *there*, not at startup:

```bash
cat > ~/.cdsapirc <<'EOF'
url: https://cds.climate.copernicus.eu/api
key: <your-CDS-token>
EOF
```

Accept the ERA5 licence on the CDS website under the same account, or the
download 403s with the file list already queued.

**Copy these scripts** into your working directory:

```
opensciencelab_fetch.py     normalize_grid.py     common_reference.py
opensciencelab_run.py       check_stack.py        decompose_mintpy.sh
```

**Earthdata credentials** — `hyp3_sdk` prompts on first use, or reads `~/.netrc`.
The jobs belong to the account that submitted them; a different login sees
nothing.

**Disk**: ~125 GB total (53 GB products, 38 GB `ifgramStack.h5`, 26 GB time
series, 8 GB ERA5).

---

## 1. Fetch the stack

```bash
python3 opensciencelab_fetch.py --dry-run     # sizes, no download
python3 opensciencelab_fetch.py               # both tracks, ~1.5-2 h
```

Expected:

```
705 SUCCEEDED jobs match 'earthchange-'
  asc: 351   desc: 354   unknown: 0
look-vector jobs found: ['asc', 'desc']
```

`unknown: 0` means `asf_search` resolved every flight direction. Anything else
means it fell back to a time-of-day heuristic that is only valid for this AOI.

`look-vector jobs found` must list both. Those two jobs are the *only* source of
`lv_theta`/`lv_phi` — the other 705 were submitted with
`include_look_vectors=False`. Without them there is no azimuth angle, ASF's
notebook rejects the stack, and a decomposition has to assume look directions
instead of reading them.

Result:

```
stack/insar_asc/hyp3/<job>/*.tif
stack/insar_desc/hyp3/<job>/*.tif
```

To take a subset instead: `--track asc`, `--start 2025-01-01`, `--max-pairs 100`.

---

## 2. Process both tracks

```bash
python3 opensciencelab_run.py stack/insar_asc  --run &
python3 opensciencelab_run.py stack/insar_desc --run &
wait
```

Parallel is fine — separate directories, and MintPy is CPU-bound. Both will queue
ERA5 requests at CDS, which costs time, not correctness.

Each track: **4–6 hours.** Per track this does

1. **Normalise grids.** HyP3 sizes each product to its own granule footprint, so
   the raster size drifts a pixel or two between acquisitions — the descending
   track has 26 distinct grids. `load_data` keeps only the modal size and
   discards the rest **with no error**. Skipping this cost 198 descending and 189
   ascending interferograms, and truncated ascending eleven months short of the
   event. Nearest-neighbour, so unwrapped phase is never averaged across a
   fringe; ≤80 m shift.
2. **`prep_hyp3` per product**, writing `.rsc` sidecars. Per-product because 705
   products is far past `ARG_MAX`, and a loop survives one bad product. Rasters
   only — handing it the `.txt` makes it open that with GDAL and abort.
3. **Write the config** (below), naming geometry only if the files exist.
4. **`smallbaselineApp --end correct_topography`**, then `timeseries2velocity`.

### Why it stops at `correct_topography`

`residual_RMS` dies in matplotlib — `ValueError: Axis limits cannot be NaN or
Inf` — on both tracks of this stack. It is a *plotting* failure: ERA5, solid
Earth tides and the topographic residual have all completed and their outputs are
on disk. Running the full app spends hours doing correct work and then exits
non-zero with no velocity, so the runner stops ahead of the broken figure.

### The settings, and why

Every one of these cost real debugging, and every one failed **silently** — the
run continued and produced a shorter or emptier result rather than stopping.

| Setting | Value | Reason |
|---|---|---|
| `unwrapError.method` | `no` | Both methods need `connectComponent`, which HyP3 GAMMA does not produce. `bridging` raises; `phase_closure` writes an all-zero dataset. |
| `networkInversion.obsDatasetName` | `unwrapPhase` | `auto` **prefers** that zeroed dataset over the good raw phase. The inversion then reports 0 pixels of 1.6 million, with no error. |
| `networkInversion.minTempCoh` | `0.1` | The mask is built **before** `correct_troposphere`. Uncorrected median temporal coherence here is ~0.06, so the 0.7 default passes one pixel and aborts the run ahead of the correction that would fix it. Permissive by design: it lets the run finish, it does not certify the pixels. |
| `deramp` | `no` | A plane fit needs pixels spread across the frame. With a sparse, clustered mask it is singular — the field exploded to 1e22 mm. |
| `load.incAngleFile` | `*_lv_theta.tif` | MintPy converts HyP3 angles itself, but only for `lv_theta`/`lv_phi` filenames: `prep_hyp3` tags them `UNIT=radian` and applies `90 - deg(theta)`. It does none of that for `inc_map`, which then needs converting by hand. |
| `load.azAngleFile` | `*_lv_phi.tif` | Azimuth angle. Without it a decomposition assumes a heading. |
| `solidEarthTides` | `yes` | Off by default. Tens of mm across a 245 km frame. |

---

## 3. Verify nothing was dropped — do not skip

```bash
python3 check_stack.py stack/insar_asc stack/insar_desc
```

Expect `351/351` and `354/354`, and exit code 0. Short means the grid
normalisation did not take and MintPy silently discarded products again. This is
the check that would have caught 387 lost interferograms on the day rather than
weeks later.

**Only after this passes** should you consider the delete cell in
`a_Load_HyP3_Data.ipynb` §5, which removes all 53 GB of GeoTIFFs. With 480 GB of
quota there is no reason to.

---

## 4. Put both tracks on one reference point

```bash
python3 common_reference.py stack/insar_asc stack/insar_desc          # report
python3 common_reference.py stack/insar_asc stack/insar_desc --apply
```

Each track auto-selects its own reference pixel, and the two landed **~178 km
apart** — so each velocity field was expressed against different ground.
`asc_desc2horz_vert` refuses to combine them until this is fixed.

This does **not** change the agreement test: Pearson correlation is invariant to
a constant offset. It fixes the decomposition, where absolute values must share
an origin.

---

## 5. Decompose

```bash
bash decompose_mintpy.sh stack/insar_asc stack/insar_desc
```

Writes `vertical.h5` and `horizontal.h5`. North–south is not recoverable: both
orbits are near-polar, so the look directions are nearly parallel to it and the
inversion is singular in that component. This is a standard limitation, not a
property of this data.

---

## 6. Network plots (optional)

ASF's notebook 4 (`plot_network`) produces `network.pdf`, `coherenceMatrix.pdf`
and `pbaseHistory.pdf` from `inputs/ifgramStack.h5`. Worth running — this
pipeline does not generate them. Point the notebook's FileChooser at
`stack/insar_asc/hyp3`.

---

## What to expect from the result

The corrected tracks **do not agree**: `r = +0.094` across 61,092 overlapping
pixels, RMS difference ~26 mm/yr. That held through ERA5, solid Earth tides,
measured look vectors and a common reference point. If your run lands somewhere
else, that is worth investigating.

The decomposition will still produce a smooth, convincing vertical/east–west
field. With `r ≈ 0` it is arithmetic on two unrelated inputs, not a measurement —
which is exactly what makes it dangerous to report.

The limitation is **atmospheric, not coherence**. Coherence persists well here
(median 67 of 156 interferograms descending, 144 of 162 ascending) — Flores is
largely savanna, not high-canopy forest, so the easy "it decorrelated"
explanation does not apply. The phase is present and self-consistent within each
track; it just does not agree between two viewing geometries. That points at
turbulent tropospheric delay, which ERA5's ~30 km reanalysis grid cannot resolve
over a narrow, steep, convectively active volcanic island.

A co-seismic measurement is a different matter: decimetre signal against a
~26 mm/yr floor, from a single interferogram, needing none of this correction
machinery.
