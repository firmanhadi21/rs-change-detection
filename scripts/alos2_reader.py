"""ALOS-2 PALSAR-2 L1.1 CEOS reader, validated against GMTSAR.

Produces the three things insardev_pygmtsar's mission contract needs:

    alos2_prm(leader, image)   -> PRM dict
    alos2_orbit(leader)        -> state-vector DataFrame
    alos2_slc(image, ...)      -> complex SLC array

Every offset below was DERIVED by searching the CEOS records for values that
GMTSAR's ALOS_pre_process already produced for the same scene, not taken from a
format document. That matters: a CEOS field read at the wrong offset returns a
plausible number rather than an error, so a reader written from a spec can be
wrong in a way nothing surfaces. Here the field map is correct by construction
for the validation scene, and `validate()` re-checks it on any other.

FORMAT, as measured on ALOS2214327020-180512-FBDR1.1:

  LED- leader, 11 CEOS records with self-describing 12-byte headers
    rec 2  data set summary, 4096 B
             @495  radar_wavelength  m      (as-is)
             @704  rng_samp_rate     MHz    (x1e6)
             @923  PRF               mHz    (x1e-3)
    rec 3  platform position, 4680 B
             @149  start seconds of day
             @171  interval, seconds
             @374  first state vector, then x y z vx vy vz repeating

  IMG- image
             720 B file descriptor, then one record per line
             record = 544 B prefix + num_rng_bins * 8 B (complex float32)
             prefix @104  near_range   m
             prefix @64   chirp_slope  x1e6

  num_rng_bins comes from the record length, num_lines from the file size;
  neither is stored. GMTSAR's PRM reports bytes_per_line 34840 because it
  rewrites the SLC as complex short -- that is its OUTPUT, not this input.

    python3 scripts/alos2_reader.py --validate \\
        ~/Teaching/UNDIP/InSAR/EQ/Pair1/raw
"""

import argparse
import glob
import os
import re
import struct
import sys

import numpy as np

# Offsets within each CEOS record payload, derived against GMTSAR output.
LEADER_FIELDS = {
    "radar_wavelength": (2, 495, 1.0),
    "rng_samp_rate":    (2, 704, 1e6),
    "PRF":              (2, 923, 1e-3),
}
ORBIT_REC = 3
ORBIT_T0_OFF, ORBIT_DT_OFF, ORBIT_SV_OFF = 149, 171, 374
IMG_DESC_LEN = 720
IMG_PREFIX_LEN = 544
IMG_NEAR_RANGE_OFF = 104
IMG_CHIRP_OFF, IMG_CHIRP_SCALE = 64, 1e6
BYTES_PER_SAMPLE = 8            # complex float32


def _records(path, max_records=64, keep_large=False):
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
            ln = struct.unpack(">I", h[8:12])[0]
            if ln < 12 or off + ln > size:
                break
            payload = f.read(ln - 12) if (keep_large or ln < 200_000) else b""
            out.append((seq, off, ln, payload))
            off += ln
    return out


def _float_at(payload, off):
    """Read the Fortran-format real beginning at `off`."""
    txt = payload[off:off + 32].decode("ascii", errors="replace")
    m = re.match(r"\s*([-+]?\d+(?:\.\d+)?(?:[EeDd][-+]?\d+)?)", txt)
    if not m:
        raise ValueError(f"no numeric field at offset {off}: {txt[:24]!r}")
    return float(m.group(1).replace("D", "E").replace("d", "e"))


def find_scene(datadir, pol="HH"):
    """Locate the LED-/IMG- pair for one polarisation."""
    led = sorted(glob.glob(os.path.join(datadir, "LED-*")))
    img = sorted(glob.glob(os.path.join(datadir, f"IMG-{pol}-*")))
    # GMTSAR writes IMG-*.PRM/.SLC/.LED/.raw beside the originals, so the
    # derived products must be filtered out. NOT by "has a dot": the CEOS name
    # itself contains one, in the product code FBDR1.1. Match the known
    # derived suffixes instead.
    derived = (".PRM", ".PRM0", ".PRMresamp", ".SLC", ".LED", ".raw", ".jpg")
    img = [p for p in img if not p.endswith(derived)]
    if not led or not img:
        raise SystemExit(f"no LED-/IMG-{pol}- pair in {datadir}")
    return led[0], img[0]


def alos2_leader(leader):
    """Instrument parameters from the leader file."""
    recs = {seq: p for seq, _, _, p in _records(leader)}
    out = {}
    for key, (rec, off, scale) in LEADER_FIELDS.items():
        out[key] = _float_at(recs[rec], off) * scale
    return out


def alos2_orbit(leader):
    """State vectors as a DataFrame: t (s of day), x, y, z, vx, vy, vz."""
    import pandas as pd

    recs = {seq: p for seq, _, _, p in _records(leader)}
    p = recs[ORBIT_REC]
    t0 = _float_at(p, ORBIT_T0_OFF)
    dt = _float_at(p, ORBIT_DT_OFF)

    txt = p[ORBIT_SV_OFF:].decode("ascii", errors="replace")
    vals = [float(m.group().replace("D", "E").replace("d", "e"))
            for m in re.finditer(r"[-+]?\d+\.\d+[EeDd][-+]?\d+", txt)]
    n = len(vals) // 6
    if n == 0:
        raise SystemExit("no state vectors parsed from the platform record")
    sv = np.array(vals[:n * 6]).reshape(n, 6)
    return pd.DataFrame({
        "t": t0 + dt * np.arange(n),
        "x": sv[:, 0], "y": sv[:, 1], "z": sv[:, 2],
        "vx": sv[:, 3], "vy": sv[:, 4], "vz": sv[:, 5],
    })


def alos2_image_meta(image):
    """Geometry that lives in the image file, not the leader."""
    size = os.path.getsize(image)
    with open(image, "rb") as f:
        f.seek(IMG_DESC_LEN)
        h = f.read(12)
        rec_len = struct.unpack(">I", h[8:12])[0]
        prefix = f.read(IMG_PREFIX_LEN)
    num_rng_bins = (rec_len - IMG_PREFIX_LEN) // BYTES_PER_SAMPLE
    num_lines = (size - IMG_DESC_LEN) // rec_len
    near_range = float(struct.unpack(
        ">i", prefix[IMG_NEAR_RANGE_OFF:IMG_NEAR_RANGE_OFF + 4])[0])
    chirp = float(struct.unpack(
        ">i", prefix[IMG_CHIRP_OFF:IMG_CHIRP_OFF + 4])[0]) * IMG_CHIRP_SCALE
    return dict(record_length=rec_len, num_rng_bins=num_rng_bins,
                num_lines=num_lines, near_range=near_range,
                chirp_slope=chirp)


def alos2_prm(leader, image):
    prm = alos2_leader(leader)
    prm.update(alos2_image_meta(image))
    prm["led_file"] = os.path.basename(leader)
    prm["input_file"] = os.path.basename(image)
    return prm


def alos2_slc(image, lines=None, first_line=0):
    """Complex SLC as (num_lines, num_rng_bins) complex64. Memory-aware."""
    m = alos2_image_meta(image)
    n = m["num_lines"] if lines is None else min(lines, m["num_lines"])
    cols = m["num_rng_bins"]
    out = np.empty((n, cols), dtype=np.complex64)
    with open(image, "rb") as f:
        for i in range(n):
            off = (IMG_DESC_LEN + (first_line + i) * m["record_length"]
                   + IMG_PREFIX_LEN)
            f.seek(off)
            raw = np.frombuffer(f.read(cols * BYTES_PER_SAMPLE),
                                dtype=">f4").astype(np.float32)
            out[i] = raw[0::2] + 1j * raw[1::2]
    return out


def _read_gmtsar_prm(path):
    prm = {}
    for line in open(path):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        try:
            prm[k.strip()] = float(v.strip())
        except ValueError:
            prm[k.strip()] = v.strip()
    return prm


def validate(datadir, pol="HH"):
    leader, image = find_scene(datadir, pol)
    print(f"leader: {os.path.basename(leader)}")
    print(f"image : {os.path.basename(image)}\n")

    prm = alos2_prm(leader, image)
    orb = alos2_orbit(leader)

    ref = sorted(glob.glob(os.path.join(
        datadir, f"IMG-{pol}-*.PRM")))
    if not ref:
        print("no GMTSAR .PRM alongside; reporting values without comparison")
        for k, v in prm.items():
            print(f"  {k:<20} {v}")
        return 0
    gm = _read_gmtsar_prm(ref[0])

    print(f"{'parameter':<20}{'this reader':>20}{'GMTSAR':>20}   agree")
    ok = True
    for key in ("radar_wavelength", "PRF", "rng_samp_rate", "near_range",
                "chirp_slope", "num_rng_bins", "num_lines"):
        mine, theirs = prm.get(key), gm.get(key)
        if theirs is None or not isinstance(theirs, float):
            continue
        # num_lines legitimately differs: GMTSAR trims a few lines when it
        # rewrites the SLC, so agreement to a handful of lines is correct.
        tol = 8.0 if key == "num_lines" else abs(theirs) * 1e-5
        good = abs(mine - theirs) <= tol
        ok &= good
        print(f"{key:<20}{mine:>20.6f}{theirs:>20.6f}   "
              f"{'yes' if good else 'NO'}")

    led_ref = sorted(glob.glob(os.path.join(datadir, f"IMG-{pol}-*.LED")))
    if led_ref:
        rows = [l.split() for l in open(led_ref[0]).read().split("\n")
                if l.strip()]
        n_gm = int(rows[0][0])
        print(f"\norbit: this reader {len(orb)} state vectors, "
              f"GMTSAR {n_gm}")
        first = [float(v) for v in rows[1][3:9]]
        mine = orb.iloc[0][["x", "y", "z", "vx", "vy", "vz"]].values
        d = np.abs(np.array(first) - mine)
        print(f"  first vector max abs difference: {d.max():.6f} m or m/s   "
              f"{'yes' if d.max() < 1e-3 else 'NO'}")
        ok &= d.max() < 1e-3 and len(orb) == n_gm

    print(f"\n{'ALL CHECKS PASS' if ok else 'MISMATCH — do not use this reader yet'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("datadir")
    ap.add_argument("--pol", default="HH")
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    d = os.path.expanduser(a.datadir)
    if a.validate:
        return validate(d, a.pol)
    leader, image = find_scene(d, a.pol)
    for k, v in alos2_prm(leader, image).items():
        print(f"  {k:<20} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
