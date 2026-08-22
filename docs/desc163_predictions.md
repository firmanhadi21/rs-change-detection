# Path 163 — predictions registered before the data arrived

Written 2026-08-22, while HyP3 jobs `b8df7c71` (pre-pre) and `9d10d07c`
(co-event) were still `PENDING`. Nothing below was written after seeing a
result. The point is to make the next step falsifiable: several of these
predictions are load-bearing for claims already made, and if they fail those
claims have to change.

**The pair.** S1D 2026-08-09 → S1D 2026-08-21, frame 620, 12 days, same
mission. Control: S1D 2026-07-28 → 2026-08-09, also 12 days, same mission,
same frame.

---

## First, a correction to something I said

I called this "a fourth look direction". That oversells it. Path 163 and path
61 are **both descending**, at 21:27 and 21:35 UTC, so their headings are
nearly identical. They differ mainly in **incidence angle**, because the
target sits at a different position across the swath. That changes how LOS
partitions between vertical and range, but barely changes east–west
sensitivity. The genuine geometric contrast in this investigation remains
ascending vs descending; path 163 is a second sample of the descending
geometry, not a new one.

What it *is* good for is the baseline-matched comparison below.

---

## Predictions

### 1. Coherence — the load-bearing one

Path 61's co-event pair was 18-day cross-mission against a 12-day same-mission
control, and I argued that mismatch inflated its coherence result. Path 163 is
matched, so:

| quantity | path 61 (observed) | ascending (observed) | **path 163 (predicted)** |
|---|---|---|---|
| scene-wide coherence drop | +0.0338 | +0.0169 | **+0.012 to +0.022** |
| co-event mean coherence | 0.511 | 0.457 | **higher than its own control by <0.03** |

**If the scene-wide drop comes out near +0.034 again, my baseline-mismatch
explanation is wrong** and the path 61 / ascending discrepancy needs another
cause.

### 2. The coherence-vs-damage adjudication

If the baseline-mismatch story holds, path 163 should behave like the
ascending frame, not like path 61:

- reports vs random: **null**, p > 0.05
- severe vs light/moderate: **positive**, p < 0.05

**Caveat that weakens this test, stated up front:** path 61, path 163 and
ascending 1148 cover *different ground* and therefore sample *different
reports*. A difference between them could be geography rather than baseline.
The clean version restricts all three to reports inside the intersection of
all three footprints, and that is what should be run regardless of how this
comes out. I expect the intersection to be small enough that the severity
test may lose significance from sample size alone.

### 3. Co-seismic displacement

Both descending, so path 163 should agree with path 61 in sign and be within a
factor of about two in magnitude:

- near-field 20–30 km, raw: **negative, 8 to 16 cm**
- near-field 20–30 km, de-planed: **negative, 2 to 6 cm**
- plane fit R² on the co-event field: **0.4 to 0.65**
- de-planed ring swing: **co-event at least 3× its control**

A path 163 profile that is flat within its control, or positive in the near
field, would contradict path 61 directly and mean one of the two descending
results is wrong.

### 4. Azimuthal coverage

Path 61 gave only 110° around the epicentre, which was the weakest link in the
plane-vs-source argument. Path 163 covers 76% of the deforming ground by area.
I predict **azimuthal coverage between 100° and 150°** — better than path 61
but still not surrounding the source. If it comes out below 90°, the plane
discrimination on this track is as weak as path 61's and the two together do
not add as much as two tracks should.

### 5. A risk worth naming

The 21 August pass recorded a short segment — 14 frames, 554..630 — against
the usual 21 frames spanning 477..630. Frame 620 sits second from the end of
that segment. Frames near a segment edge can have reduced burst overlap. I do
**not** predict a failure, since the 9 August reference spans 477..630 and the
overlap at 620 should be complete, but if the product comes back with a
truncated footprint or a coherence collapse along one edge, this is the first
thing to check.

---

## What would change the overall conclusion

Nothing here can overturn the ascending result, which three independent
processing chains and 76 earthquake-free intervals already support. What path
163 can do:

- **Strengthen it** — a second descending track showing the same source-centred
  residual makes the path 61 result reproducible rather than singular.
- **Undermine the coherence-damage claim** — if reports-vs-random comes back
  strongly positive on a baseline-matched pair, then the ascending null is the
  odd one out and the explanation I committed to is wrong.
- **Expose a problem in path 61** — a direct contradiction in the displacement
  profile between two descending tracks would mean one of them is
  mis-processed, and the 18-day cross-mission pair is the more suspect.
