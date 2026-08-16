"""Undo the mass geometry copy that filled the disk, keeping one set per track.

Look vectors and incidence angle describe the TRACK, not a pair, so MintPy and
the ASF notebook both need exactly one file per track. Copying all four bands
into all 705 product dirs would have written ~127 GB and ran the disk out
partway through.

Two files per track are load-bearing and must survive: the _inc_map.tif each
MintPy config names by full path, already converted from radians to degrees.
Deleting those would break both configs and silently reintroduce the units bug
on the next reload.
"""

import glob
import os
import re
import sys

OUT = "output"
GEOM = ("_lv_theta.tif", "_lv_phi.tif", "_inc_map.tif", "_inc_map_ell.tif")


def config_referenced(track):
    """Absolute paths the track's MintPy config points at."""
    cfg = f"{OUT}/{track}/mintpy/earthchange.cfg"
    keep = set()
    if not os.path.exists(cfg):
        return keep
    root = os.path.dirname(cfg)
    for line in open(cfg):
        if line.startswith("mintpy.load.incAngleFile"):
            rel = line.split("=", 1)[1].strip()
            for p in glob.glob(os.path.join(root, rel)):
                keep.add(os.path.abspath(p))
    return keep


def main():
    dry = "--delete" not in sys.argv
    total_freed = 0

    for track in ("insar_geom_desc", "insar_geom_asc"):
        keep = config_referenced(track)
        print(f"=== {track} ===")
        print(f"  config references {len(keep)} file(s):")
        for k in sorted(keep):
            print(f"    {os.path.basename(k)}")

        victims = []
        for suffix in GEOM:
            for p in glob.glob(f"{OUT}/{track}/hyp3/*/*{suffix}"):
                if os.path.abspath(p) in keep:
                    continue
                victims.append(p)

        size = sum(os.path.getsize(p) for p in victims if os.path.exists(p))
        total_freed += size
        print(f"  {len(victims)} redundant geometry files, "
              f"{size/1e9:.1f} GB")

        if not dry:
            for p in victims:
                try:
                    os.remove(p)
                except OSError:
                    pass
            print(f"  deleted")
        print()

    print(f"total: {total_freed/1e9:.1f} GB "
          f"{'would be freed (pass --delete)' if dry else 'freed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
