"""Are the loop-closure failures the low-coherence interferograms?

Step 11 gates on average coherence at a very permissive 0.05, so nearly
everything reaches step 12, where loop closure rejected 1,026 of 1,183. If
coherence drives those failures, raising the step-11 gate would remove the bad
interferograms earlier and leave a cleaner -- if smaller -- network. If it does
not, the failures are unwrapping errors independent of coherence, and no
threshold will fix them.

Everything needed is already written by steps 11 and 12:
  11ifg_stats.txt  per-interferogram coherence and unwrapped coverage
  12bad_ifg.txt    the ones loop closure rejected
"""

import os
import sys

import numpy as np

TS = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/licsbas/TS_GEOCml10/info")


def main():
    stats = {}
    for line in open(f"{TS}/11ifg_stats.txt", errors="ignore"):
        if line.startswith("#") or not line.strip():
            continue
        # Rows are: date12 bperp dt unw_cov coh_av -- five fields, not six.
        # Requiring six silently discarded nearly every row and made the
        # comparison look empty rather than wrong.
        f = line.split()
        if len(f) >= 5 and "_" in f[0]:
            try:
                stats[f[0]] = {"bperp": float(f[1]), "dt": int(float(f[2])),
                               "unw_cov": float(f[3]), "coh": float(f[4])}
            except ValueError:
                continue
    print(f"{len(stats)} interferograms with step-11 statistics")
    if len(stats) < 100:
        print("  WARNING: far fewer than the 1183 expected — check the parse")

    def load(name):
        p = f"{TS}/{name}"
        if not os.path.exists(p):
            return set()
        return {l.split()[0] for l in open(p) if l.strip()
                and not l.startswith("#")}

    bad11 = load("11bad_ifg.txt")
    bad12 = load("12bad_ifg.txt")
    print(f"  rejected at step 11 (coverage/coherence): {len(bad11)}")
    print(f"  rejected at step 12 (loop closure):       {len(bad12)}")

    survived = [k for k in stats if k not in bad11 and k not in bad12]
    failed12 = [k for k in stats if k in bad12]
    print(f"  survived both:                            {len(survived)}")

    def describe(label, keys, field):
        v = np.array([stats[k][field] for k in keys if k in stats])
        if v.size == 0:
            print(f"  {label:22} (none)")
            return None
        print(f"  {label:22} n={v.size:>5}  median {np.median(v):6.3f}  "
              f"p25 {np.percentile(v,25):6.3f}  p75 {np.percentile(v,75):6.3f}")
        return v

    for field in ("coh", "unw_cov", "dt"):
        print(f"\n=== {field} ===")
        a = describe("failed loop closure", failed12, field)
        b = describe("survived", survived, field)
        if a is not None and b is not None and a.size and b.size:
            diff = np.median(b) - np.median(a)
            print(f"  survivors are {diff:+.3f} higher in median {field}")
            # Rank-based separation: 0.5 means the two are indistinguishable.
            allv = np.concatenate([a, b])
            order = allv.argsort().argsort()
            ra = order[:a.size].mean()
            rb = order[a.size:].mean()
            auc = (rb - ra) / len(allv) + 0.5
            print(f"  separation (AUC): {auc:.3f}  "
                  f"{'strong' if abs(auc-0.5) > 0.2 else 'weak' if abs(auc-0.5) > 0.1 else 'none'}")

    print("\n=== what would a stricter step-11 coherence gate do? ===")
    print("  thre   kept   of which loop-closure failures")
    for thre in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        kept = [k for k, s in stats.items()
                if s["coh"] >= thre and k not in bad11]
        badkept = [k for k in kept if k in bad12]
        if not kept:
            continue
        print(f"  {thre:.2f}  {len(kept):>5}   {len(badkept):>5} "
              f"({100*len(badkept)/len(kept):5.1f}%)")

    print("\n=== reading ===")
    # Judge on the threshold sweep, not on medians. Two groups can differ in
    # median while a gate between them still fails to separate them usefully --
    # which is exactly the case here, and comparing medians alone said the
    # opposite.
    best = None
    for thre in (0.08, 0.10, 0.12, 0.15, 0.20):
        kept = [k for k, s in stats.items()
                if s["coh"] >= thre and k not in bad11]
        if len(kept) < 30:
            continue
        rate = sum(1 for k in kept if k in bad12) / len(kept)
        if best is None or rate < best[1]:
            best = (thre, rate, len(kept))

    if best and best[1] < 0.4:
        print(f"  A coherence gate helps: at {best[0]:.2f}, only "
              f"{100*best[1]:.0f}% still fail, keeping {best[2]}.")
    else:
        if best:
            print(f"  Even the best coherence gate ({best[0]:.2f}) leaves "
                  f"{100*best[1]:.0f}% failing, from {best[2]} kept.")
        print("  Coherence is a contributing factor, not the driver: you cannot")
        print("  threshold your way to a closing network.")

    da = np.array([stats[k]["dt"] for k in failed12 if k in stats])
    ds = np.array([stats[k]["dt"] for k in survived if k in stats])
    if da.size and ds.size and np.median(ds) < np.median(da):
        print(f"  Temporal baseline separates better: survivors median "
              f"{np.median(ds):.0f} d vs {np.median(da):.0f} d for failures.")
        print("  Restricting the network to short baselines is the lever most")
        print("  likely to produce a network that closes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
