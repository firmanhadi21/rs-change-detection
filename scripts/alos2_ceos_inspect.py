"""Walk an ALOS-2 PALSAR-2 L1.1 CEOS product and report what is actually in it.

First step toward ALOS-2 support in insardev_pygmtsar. The mission-specific
contract there is small -- three functions producing a PRM dict, an orbit
DataFrame and an SLC array -- but all three depend on reading CEOS correctly,
and CEOS is where a reader quietly goes wrong: a field read at the wrong offset
returns a plausible number rather than an error.

So this deliberately does NOT hardcode field offsets. CEOS records carry a
self-describing 12-byte header (sequence number, four type codes, record
length), which lets the file be walked structurally with no prior knowledge.
Metadata fields in ALOS CEOS are ASCII in Fortran F/I formats, so once a record
is located its contents can be read and the offsets DERIVED from the data in
front of us instead of guessed.

What it reports, per file:
  - every record: sequence, type codes, length
  - for metadata records: the ASCII content, so fields can be located
  - candidate physical values found anywhere (wavelength, PRF, sampling rate),
    cross-checked against what PALSAR-2 must plausibly be

The plausibility check matters. L-band is ~0.2296 m; if a candidate wavelength
comes out at 0.055 m the reader has locked onto the wrong bytes, and saying so
immediately is worth more than a clean-looking parse.

    python3 scripts/alos2_ceos_inspect.py /path/to/ALOS2_scene_dir
    python3 scripts/alos2_ceos_inspect.py /path/to/LED-ALOS2xxxxx --full
"""

import argparse
import glob
import os
import re
import struct
import sys

# PALSAR-2 physical bounds. Used to sanity-check anything the walker proposes,
# never to search for values -- a reader that finds what it expects because it
# was told what to expect has verified nothing.
# Bounds widened after checking against GMTSAR's own PRM for a real FBD scene,
# which gives radar_wavelength = 0.242452 m. My first range (0.22-0.24) was
# taken from the nominal 1270 MHz L-band figure and would have flagged the
# CORRECT value as implausible -- PALSAR-2 shifts centre frequency by mode. A
# sanity check calibrated on a textbook number rather than on the instrument is
# worse than none, because it rejects good data confidently.
PLAUSIBLE = {
    "wavelength_m": (0.21, 0.26),
    "prf_hz": (1000.0, 4000.0),
    "rng_samp_rate_hz": (10e6, 200e6),
    "near_range_m": (5.0e5, 1.5e6),
}

# CEOS record type codes seen in ALOS SAR leader files. Names are for reporting
# only; nothing downstream depends on them being complete.
RECORD_NAMES = {
    (63, 192, 18, 18): "File descriptor",
    (10, 10, 18, 20): "Data set summary",
    (20, 10, 18, 20): "Map projection data",
    (30, 10, 18, 20): "Platform position",
    (40, 10, 18, 20): "Attitude data",
    (50, 10, 18, 20): "Radiometric data",
    (60, 10, 18, 20): "Data quality summary",
    (70, 10, 18, 20): "Facility related",
    (11, 50, 18, 20): "Signal/processed data",
}


def walk(path, max_records=400):
    """Yield (seq, codes, length, payload) for each CEOS record."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        off = 0
        for _ in range(max_records):
            if off + 12 > size:
                break
            f.seek(off)
            head = f.read(12)
            if len(head) < 12:
                break
            seq = struct.unpack(">I", head[0:4])[0]
            codes = tuple(head[4:8])
            length = struct.unpack(">I", head[8:12])[0]
            # A record shorter than its own header, or longer than the file,
            # means the walk has desynchronised -- stop rather than emit noise.
            if length < 12 or off + length > size:
                yield ("DESYNC", codes, length, off)
                break
            payload = f.read(length - 12)
            yield (seq, codes, length, payload)
            off += length


def ascii_fields(payload):
    """Runs of printable ASCII, which is how CEOS stores its metadata."""
    txt = payload.decode("ascii", errors="replace")
    return [s for s in re.findall(r"[ -~]{6,}", txt)]


def numbers_in(payload):
    """Every Fortran-style real in the record, with its byte offset."""
    txt = payload.decode("ascii", errors="replace")
    out = []
    for m in re.finditer(r"[-+]?\d+\.\d+(?:[EeDd][-+]?\d+)?", txt):
        try:
            out.append((m.start(), float(m.group().replace("D", "E")
                                         .replace("d", "e"))))
        except ValueError:
            pass
    return out


def check_plausible(cands):
    print("\n  candidate physical values (offset -> value):")
    for key, (lo, hi) in PLAUSIBLE.items():
        hits = [(o, v) for o, v in cands if lo <= v <= hi]
        if hits:
            shown = ", ".join(f"@{o}={v:g}" for o, v in hits[:4])
            print(f"    {key:<18} {len(hits):>3} candidate(s)  {shown}")
        else:
            print(f"    {key:<18}   0 candidates  <-- nothing in range "
                  f"[{lo:g}, {hi:g}]")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", help="scene directory or a single CEOS file")
    ap.add_argument("--full", action="store_true",
                    help="print all ASCII content of metadata records")
    a = ap.parse_args()

    t = os.path.expanduser(a.target)
    if os.path.isdir(t):
        files = sorted(glob.glob(f"{t}/*"))
        print(f"scene directory: {t}\n{len(files)} file(s)\n")
        groups = {}
        for f in files:
            b = os.path.basename(f)
            groups.setdefault(b.split("-")[0], []).append(f)
        for k in sorted(groups):
            tot = sum(os.path.getsize(x) for x in groups[k]) / 1e6
            print(f"  {k:<10} {len(groups[k]):>2} file(s)  {tot:>10.1f} MB"
                  f"   e.g. {os.path.basename(groups[k][0])[:52]}")
        print("\nALOS-2 L1.1 expects: LED- (leader, metadata+orbit),")
        print("IMG-<POL>- (one per polarisation), TRL-, VOL-.")
        led = groups.get("LED", [])
        if not led:
            sys.exit("\nno LED- leader file found; cannot read metadata")
        targets = led
    else:
        targets = [t]

    for path in targets:
        print(f"\n{'='*70}\n{os.path.basename(path)}  "
              f"({os.path.getsize(path)/1e6:.1f} MB)\n{'='*70}")
        cands = []
        for seq, codes, length, payload in walk(path):
            if seq == "DESYNC":
                print(f"  !! record walk desynchronised at byte {payload}; "
                      f"claimed length {length}")
                print("     Either this is not CEOS, or it uses a variant "
                      "header. Stopping rather than reporting guesses.")
                break
            name = RECORD_NAMES.get(codes, "unknown")
            print(f"  seq {seq:<4} codes {str(codes):<20} "
                  f"{length:>9,} bytes   {name}")
            if length < 200_000:          # metadata, not an image line
                cands += numbers_in(payload)
                if a.full:
                    for s in ascii_fields(payload)[:40]:
                        print(f"        {s[:100]}")
        if cands:
            check_plausible(cands)

    print("\n=== next step ===")
    print("  With the records located, the three functions insardev needs")
    print("  can be written against real offsets rather than a spec:")
    print("    alos2_prm(path, pol)   -> PRM dict")
    print("    alos2_orbit(path)      -> state-vector DataFrame")
    print("    alos2_slc(path, pol)   -> complex SLC array")
    print("  Cross-check the PRM against GMTSAR's ALOS_pre_process on the")
    print("  same scene before trusting any interferogram made from it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
