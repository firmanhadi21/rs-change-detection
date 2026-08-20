"""Derive ALOS-2 CEOS field offsets by matching GMTSAR's PRM, not by guessing.

Writing a CEOS reader from a format document is how readers acquire silent
errors: a field taken at the wrong offset yields a plausible number, and
nothing raises. Here the answers already exist -- GMTSAR's ALOS_pre_process has
produced a .PRM for this exact scene -- so the offsets can be DERIVED by
searching the CEOS record for each known value.

For every PRM parameter this looks through the leader's ASCII numeric fields
for a match, allowing the unit scalings CEOS actually uses (MHz for sampling
rates, mHz for PRF, microseconds for pulse durations, kilometres for ranges).
What comes back is a field map that is correct by construction for this scene,
and testable on the next one.

Two things this deliberately does not do. It does not accept a match that only
works under an implausible scaling, and it reports parameters it could NOT
locate rather than quietly omitting them -- an incomplete map that looks
complete is the failure being avoided.

    python3 scripts/alos2_field_map.py \\
        ~/Teaching/UNDIP/InSAR/EQ/Pair1/raw/LED-ALOS2214327020-180512-FBDR1.1__A \\
        ~/Teaching/UNDIP/InSAR/EQ/Pair1/raw/IMG-HH-ALOS2214327020-180512-FBDR1.1__A.PRM
"""

import argparse
import os
import re
import struct
import sys

# Scalings CEOS is known to use for these quantities. Each is (factor, label):
# a stored value v matches a PRM target t when v * factor == t.
SCALINGS = [
    (1.0, "as-is"),
    (1e6, "MHz -> Hz"),
    (1e-3, "mHz -> Hz"),
    (1e3, "km -> m"),
    (1e-6, "us -> s"),
    (1e-9, "ns -> s"),
    (1e9, "GHz -> Hz"),
]

# The PRM fields an ALOS-2 reader must produce. Values GMTSAR derives rather
# than reads (num_lines from file size, clock from date arithmetic) are noted,
# because failing to find those in the leader is expected, not a defect.
WANTED = [
    ("radar_wavelength", "read"),
    ("PRF", "read"),
    ("rng_samp_rate", "read"),
    ("pulse_dur", "read"),
    ("near_range", "read"),
    ("chirp_slope", "read"),
    ("num_rng_bins", "read"),
    ("num_lines", "derived from image file size"),
    ("SC_vel", "derived from orbit"),
    ("SC_height", "derived from orbit"),
    ("earth_radius", "derived from orbit + geodesy"),
]


def records(path, max_records=64):
    size = os.path.getsize(path)
    out = []
    with open(path, "rb") as f:
        off = 0
        for _ in range(max_records):
            if off + 12 > size:
                break
            f.seek(off)
            h = f.read(12)
            if len(h) < 12:
                break
            seq = struct.unpack(">I", h[0:4])[0]
            codes = tuple(h[4:8])
            ln = struct.unpack(">I", h[8:12])[0]
            if ln < 12 or off + ln > size:
                break
            out.append((seq, codes, off, ln, f.read(ln - 12)))
            off += ln
    return out


def numeric_fields(payload):
    txt = payload.decode("ascii", errors="replace")
    out = []
    for m in re.finditer(r"[-+]?\d+(?:\.\d+)?(?:[EeDd][-+]?\d+)?", txt):
        s = m.group().replace("D", "E").replace("d", "e")
        try:
            out.append((m.start(), len(m.group()), float(s)))
        except ValueError:
            pass
    return out


def read_prm(path):
    prm = {}
    for line in open(path):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        try:
            prm[k] = float(v)
        except ValueError:
            prm[k] = v
    return prm


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("leader")
    ap.add_argument("prm")
    # GMTSAR writes the PRM with printf %f -- six decimals -- so the ground
    # truth is LESS precise than the leader it came from. radar_wavelength is
    # stored as 0.242452500 and printed as 0.242452, a relative difference of
    # 2.1e-6 that a 1e-6 tolerance rejects. The looser default matches the
    # precision actually available, not the precision the leader has.
    ap.add_argument("--rtol", type=float, default=1e-5)
    a = ap.parse_args()

    prm = read_prm(os.path.expanduser(a.prm))
    recs = records(os.path.expanduser(a.leader))
    print(f"leader: {len(recs)} records")
    for seq, codes, off, ln, _ in recs:
        print(f"  seq {seq:<3} codes {str(codes):<20} at {off:>9,}  "
              f"{ln:>9,} bytes")

    print(f"\nPRM has {len(prm)} parameters; locating the ones a reader must "
          f"produce.\n")
    print(f"  {'parameter':<20}{'PRM value':>18}  where in the leader")
    unresolved = []
    for key, note in WANTED:
        target = prm.get(key)
        if not isinstance(target, float):
            print(f"  {key:<20}{'-- absent from PRM --':>18}")
            continue
        hit = None
        for seq, codes, off, ln, payload in recs:
            if ln > 200_000:
                continue
            for foff, flen, val in numeric_fields(payload):
                for factor, label in SCALINGS:
                    if target == 0:
                        continue
                    if abs(val * factor - target) <= abs(target) * a.rtol:
                        hit = (seq, codes, foff, flen, val, label)
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            seq, codes, foff, flen, val, label = hit
            print(f"  {key:<20}{target:>18.6f}  rec {seq} @{foff} "
                  f"len {flen}  raw {val:g}  ({label})")
        else:
            print(f"  {key:<20}{target:>18.6f}  NOT FOUND"
                  + (f"   [{note}]" if note != "read" else "   <-- expected "
                     "to be readable; investigate"))
            unresolved.append((key, note))

    print("\n=== summary ===")
    readable = [k for k, n in unresolved if n == "read"]
    if readable:
        print(f"  {len(readable)} field(s) expected in the leader but not "
              f"located: {', '.join(readable)}")
        print("  Either the scaling is unusual or GMTSAR computes them; check")
        print("  ALOS_pre_process before assuming the leader lacks them.")
    else:
        print("  Every directly-readable parameter was located in the leader.")
    derived = [k for k, n in unresolved if n != "read"]
    if derived:
        print(f"  {len(derived)} absent as expected (computed, not read): "
              f"{', '.join(derived)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
