"""ALOS-2 PALSAR-2 L1.1 support for insardev_pygmtsar.

insardev's mission contract is small. A mission class scans a directory into a
GeoDataFrame, then answers `_make_scene` with

    (prm_dict, orbit_df, slc_data, reramp_params)

and for a stripmap sensor the last is None. PALSAR-2 FBS/FBD is stripmap, so
NISAR is the template here rather than the much larger Sentinel-1 TOPS path,
and the align and transform layers -- which are ~97% mission-agnostic -- are
inherited rather than rewritten.

WHERE THE NUMBERS COME FROM. Every CEOS offset below was DERIVED by searching
the records for values GMTSAR's ALOS_pre_process had already produced for the
same scene, never taken from a format document. A CEOS field read at the wrong
offset returns a plausible number rather than an error, so a reader written
from a spec can be wrong in a way nothing surfaces. The map was then checked
against a SECOND scene it was not fitted to, where near_range and num_rng_bins
legitimately differ and were both read correctly -- which is what shows the
reader parses rather than echoes.

    LED- leader, CEOS records with self-describing 12-byte headers
      rec 2  data set summary
               @495  radar_wavelength  m    @704  rng_samp_rate  MHz
               @736  pulse_dur         us   @923  PRF            mHz
               header: scene id, acquisition time, GRS80 radii
      rec 3  platform position
               @149  start second of day   @171  interval
               @374  state vectors, x y z vx vy vz repeating

    IMG- image
      720 B descriptor, then one record per line
      record = 544 B prefix + num_rng_bins * 8 B (complex float32)
               prefix @64  chirp_slope x1e6   @104  near_range m

num_rng_bins follows from the record length and num_lines from the file size;
neither is stored. GMTSAR's PRM reports bytes_per_line 34840 because it
rewrites the SLC as complex short -- that is its OUTPUT, not this input, and
taking it as an input property would halve the sample width.

THE FOOTPRINT IS COMPUTED, NOT READ. L1.1 is slant-range and carries no map
projection record, so there are no corner coordinates anywhere in the product.
The polygon is derived from the orbit and the range geometry, and is therefore
approximate -- good enough to plot, to pick a DEM and to intersect with an area
of interest, not a substitute for geocoding.
"""

import datetime as dt
import glob
import os
import re
import struct

import numpy as np

# --- CEOS layout, derived against GMTSAR output -------------------------
LEADER_FIELDS = {
    "radar_wavelength": (2, 495, 1.0),
    "rng_samp_rate":    (2, 704, 1e6),
    "PRF":              (2, 923, 1e-3),
    # Located only at rtol 1e-4: the leader holds 30.6894840 us while GMTSAR
    # prints 3.068900e-05. The ground truth is the LESS precise of the two, so
    # a tolerance set by the reference rejects a correct field.
    "pulse_dur":        (2, 736, 1e-6),
}
ORBIT_REC = 3
ORBIT_T0_OFF, ORBIT_DT_OFF, ORBIT_SV_OFF = 149, 171, 374
IMG_DESC_LEN, IMG_PREFIX_LEN = 720, 544
IMG_NEAR_RANGE_OFF, IMG_CHIRP_OFF, IMG_CHIRP_SCALE = 104, 64, 1e6
BYTES_PER_SAMPLE = 8                 # complex float32
C = 299_792_458.0

DERIVED_SUFFIXES = (".PRM", ".PRM0", ".PRMresamp", ".SLC", ".LED", ".raw",
                    ".jpg", ".tif", ".png")


# --- low-level CEOS -----------------------------------------------------
def _records(path, limit=64, max_payload=200_000):
    size = os.path.getsize(path)
    out = []
    with open(path, "rb") as f:
        off = 0
        for _ in range(limit):
            if off + 12 > size:
                break
            f.seek(off)
            h = f.read(12)
            if len(h) < 12:
                break
            seq = struct.unpack(">I", h[0:4])[0]
            ln = struct.unpack(">I", h[8:12])[0]
            # A record shorter than its own header, or overrunning the file,
            # means the walk has desynchronised. Stop rather than emit noise.
            if ln < 12 or off + ln > size:
                break
            out.append((seq, off, ln,
                        f.read(ln - 12) if ln <= max_payload else b""))
            off += ln
    return out


def _float_at(payload, off):
    txt = payload[off:off + 32].decode("ascii", errors="replace")
    m = re.match(r"\s*([-+]?\d+(?:\.\d+)?(?:[EeDd][-+]?\d+)?)", txt)
    if not m:
        raise ValueError(f"no numeric field at offset {off}: {txt[:24]!r}")
    return float(m.group(1).replace("D", "E").replace("d", "e"))


def find_scenes(datadir, pol="HH"):
    """Every (leader, image) pair in a directory, keyed by scene id."""
    out = {}
    for img in sorted(glob.glob(os.path.join(datadir, f"IMG-{pol}-*"))):
        # GMTSAR writes IMG-*.PRM/.SLC/.LED beside the originals. Filter by
        # known suffix, NOT by "contains a dot" -- the CEOS name itself has
        # one, in the product code FBDR1.1.
        if img.endswith(DERIVED_SUFFIXES):
            continue
        base = os.path.basename(img)
        m = re.match(rf"IMG-{pol}-(.+)$", base)
        if not m:
            continue
        sid = m.group(1)
        led = os.path.join(datadir, f"LED-{sid}")
        if os.path.exists(led):
            out[sid] = (led, img)
    return out


def leader_header(leader):
    """Scene id, acquisition time and ellipsoid, from the summary record."""
    recs = {s: p for s, _, _, p in _records(leader)}
    txt = recs[2][:400].decode("ascii", errors="replace")
    sid = re.search(r"(ALOS2\d+-\d+)", txt)
    stamp = re.search(r"(\d{17})", txt)
    radii = re.findall(r"(\d{4}\.\d{7})", txt)
    t = None
    if stamp:
        s = stamp.group(1)
        t = dt.datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]),
                        int(s[10:12]), int(s[12:14]),
                        int(s[14:17]) * 1000)
    return dict(
        scene_id=sid.group(1) if sid else os.path.basename(leader),
        start_time=t,
        # Kilometres in the file; PRM wants metres.
        equatorial_radius=float(radii[0]) * 1e3 if len(radii) > 0 else 6378137.0,
        polar_radius=float(radii[1]) * 1e3 if len(radii) > 1 else 6356752.3141,
        # Seconds of day, so the footprint can be placed at the acquisition
        # instead of at the middle of whatever orbit arc the leader carries.
        second_of_day=((t.hour * 3600 + t.minute * 60 + t.second
                        + t.microsecond / 1e6) if t else None),
    )


def leader_params(leader):
    recs = {s: p for s, _, _, p in _records(leader)}
    return {k: _float_at(recs[rec], off) * scale
            for k, (rec, off, scale) in LEADER_FIELDS.items()}


def orbit(leader):
    """State vectors: t (second of day), x, y, z, vx, vy, vz. Metres."""
    import pandas as pd

    recs = {s: p for s, _, _, p in _records(leader)}
    p = recs[ORBIT_REC]
    t0, dt_s = _float_at(p, ORBIT_T0_OFF), _float_at(p, ORBIT_DT_OFF)
    txt = p[ORBIT_SV_OFF:].decode("ascii", errors="replace")
    vals = [float(m.group().replace("D", "E").replace("d", "e"))
            for m in re.finditer(r"[-+]?\d+\.\d+[EeDd][-+]?\d+", txt)]
    n = len(vals) // 6
    if n == 0:
        raise ValueError("no state vectors in the platform position record")
    sv = np.array(vals[:n * 6]).reshape(n, 6)
    return pd.DataFrame({"t": t0 + dt_s * np.arange(n),
                         "x": sv[:, 0], "y": sv[:, 1], "z": sv[:, 2],
                         "vx": sv[:, 3], "vy": sv[:, 4], "vz": sv[:, 5]})


def image_meta(image):
    """Geometry that lives in the image file, not the leader."""
    size = os.path.getsize(image)
    with open(image, "rb") as f:
        f.seek(IMG_DESC_LEN)
        rec_len = struct.unpack(">I", f.read(12)[8:12])[0]
        prefix = f.read(IMG_PREFIX_LEN)
    return dict(
        record_length=rec_len,
        num_rng_bins=(rec_len - IMG_PREFIX_LEN) // BYTES_PER_SAMPLE,
        num_lines=(size - IMG_DESC_LEN) // rec_len,
        near_range=float(struct.unpack(
            ">i", prefix[IMG_NEAR_RANGE_OFF:IMG_NEAR_RANGE_OFF + 4])[0]),
        chirp_slope=float(struct.unpack(
            ">i", prefix[IMG_CHIRP_OFF:IMG_CHIRP_OFF + 4])[0]) * IMG_CHIRP_SCALE,
    )


def slc(image, lines=None, first_line=0):
    """Complex SLC as (lines, num_rng_bins) complex64."""
    m = image_meta(image)
    n = m["num_lines"] if lines is None else min(lines, m["num_lines"])
    cols = m["num_rng_bins"]
    out = np.empty((n, cols), dtype=np.complex64)
    with open(image, "rb") as f:
        for i in range(n):
            f.seek(IMG_DESC_LEN + (first_line + i) * m["record_length"]
                   + IMG_PREFIX_LEN)
            raw = np.frombuffer(f.read(cols * BYTES_PER_SAMPLE), dtype=">f4")
            out[i] = raw[0::2] + 1j * raw[1::2]
    return out


# --- geometry -----------------------------------------------------------
def _ecef_to_geodetic(x, y, z, a, b):
    """Bowring's method -- one iteration is ample at orbital altitude."""
    e2 = 1 - (b * b) / (a * a)
    ep2 = (a * a) / (b * b) - 1
    p = np.hypot(x, y)
    th = np.arctan2(z * a, p * b)
    lat = np.arctan2(z + ep2 * b * np.sin(th) ** 3,
                     p - e2 * a * np.cos(th) ** 3)
    lon = np.arctan2(y, x)
    N = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - N
    return np.degrees(lat), np.degrees(lon), h


def footprint(orbit_df, meta, params, header, look="R", n=9):
    """Approximate WGS84 polygon for a slant-range scene.

    L1.1 carries no map projection record, so there is nothing to read: the
    outline is reconstructed from where the satellite was and how far the
    radar looked. Ground range comes from the spherical law of cosines on the
    Earth-centred triangle (satellite, Earth centre, target), and the swath is
    laid perpendicular to the ground track, to the right for ALOS-2.

    Approximate on purpose -- it ignores terrain and treats the Earth as
    locally spherical. Adequate to plot, to choose a DEM tile and to test
    intersection with an area of interest; not a geocoding.
    """
    from shapely.geometry import Polygon

    a, b = header["equatorial_radius"], header["polar_radius"]
    near = meta["near_range"]
    far = near + meta["num_rng_bins"] * C / (2 * params["rng_samp_rate"])

    # Centre on the ACQUISITION time, not the orbit record's midpoint. The
    # leader carries ~28 minutes of state vectors while the scene lasts about
    # ten seconds, so using the record's midpoint placed the footprint
    # wherever the satellite happened to be mid-record -- 1.3 degrees from the
    # truth on the validation scenes, which is most of a swath width.
    dur = meta["num_lines"] / params["PRF"]
    t0 = header.get("second_of_day")
    if t0 is None:
        t0 = 0.5 * (orbit_df["t"].iloc[0] + orbit_df["t"].iloc[-1])
    ts = np.linspace(t0, t0 + dur, n)

    left, right = [], []
    for t in ts:
        pos = np.array([np.interp(t, orbit_df["t"], orbit_df[c])
                        for c in ("x", "y", "z")])
        vel = np.array([np.interp(t, orbit_df["t"], orbit_df[c])
                        for c in ("vx", "vy", "vz")])
        lat, lon, h = _ecef_to_geodetic(*pos, a, b)
        Re = a * (1 - (1 - (b / a) ** 2) * np.sin(np.radians(lat)) ** 2) ** .5
        Rs = Re + h

        # up, and the across-track direction (right of the velocity vector)
        up = pos / np.linalg.norm(pos)
        along = vel / np.linalg.norm(vel)
        across = np.cross(along, up)
        if look.upper() == "L":
            across = -across

        for R, store in ((near, left), (far, right)):
            cosg = (Re * Re + Rs * Rs - R * R) / (2 * Re * Rs)
            gamma = np.arccos(np.clip(cosg, -1, 1))       # Earth-centre angle
            gr = Re * gamma                                # ground range, m
            # Small-angle walk along the surface in the across-track direction.
            d = across * gr
            plat, plon, _ = _ecef_to_geodetic(*(pos - up * h + d), a, b)
            store.append((plon, plat))

    ring = left + right[::-1] + [left[0]]
    return Polygon(ring)


# --- the insardev contract ----------------------------------------------
def prm(leader, image, extra=None):
    """The PRM dictionary insardev's pipeline consumes."""
    hdr = leader_header(leader)
    par = leader_params(leader)
    meta = image_meta(image)
    orb = orbit(leader)

    t = hdr["start_time"]
    doy = t.timetuple().tm_yday if t else 0
    sod = (t.hour * 3600 + t.minute * 60 + t.second
           + t.microsecond / 1e6) if t else 0.0
    clock_start = doy + sod / 86400.0
    duration = meta["num_lines"] / par["PRF"]

    i = len(orb) // 2
    pos = orb.iloc[i][["x", "y", "z"]].to_numpy(dtype=float)
    vel = orb.iloc[i][["vx", "vy", "vz"]].to_numpy(dtype=float)
    lat, lon, height = _ecef_to_geodetic(
        *pos, hdr["equatorial_radius"], hdr["polar_radius"])
    a, b = hdr["equatorial_radius"], hdr["polar_radius"]
    earth_radius = a * (1 - (1 - (b / a) ** 2)
                        * np.sin(np.radians(lat)) ** 2) ** .5

    out = {
        # read from the product
        "radar_wavelength": par["radar_wavelength"],
        "PRF": par["PRF"],
        "rng_samp_rate": par["rng_samp_rate"],
        "pulse_dur": par["pulse_dur"],
        "near_range": meta["near_range"],
        "chirp_slope": meta["chirp_slope"],
        "num_rng_bins": meta["num_rng_bins"],
        "num_lines": meta["num_lines"],
        # implied by the layout
        "bytes_per_line": meta["num_rng_bins"] * 4,   # complex short, on write
        "good_bytes_per_line": meta["num_rng_bins"] * 4,
        "num_valid_az": meta["num_lines"],
        "nrows": meta["num_lines"],
        "first_line": 1,
        "num_patches": 1,
        "first_sample": 0,
        "st_rng_bin": 1,
        # timing
        "SC_clock_start": t.year * 1000 + clock_start if t else 0.0,
        "SC_clock_stop": (t.year * 1000 + clock_start + duration / 86400.0
                          if t else 0.0),
        "clock_start": clock_start,
        "clock_stop": clock_start + duration / 86400.0,
        # geometry, from the orbit
        #
        # SC_vel is the SAR EFFECTIVE velocity, sqrt(V_sat * V_ground), not the
        # state-vector magnitude. The two differ by sqrt(Re / (Re + h)) -- about
        # 4.9% at this altitude, which reads as a plausible number and is
        # wrong. It is the geometric mean of the platform speed and the speed
        # its footprint sweeps the ground, which is what azimuth focusing and
        # the Doppler geometry actually use.
        "SC_vel": float(np.linalg.norm(vel)
                        * np.sqrt(earth_radius / (earth_radius + height))),
        "SC_height": float(height),
        "earth_radius": float(earth_radius),
        "equatorial_radius": a,
        "polar_radius": b,
        # constants for an unprocessed scene
        "fd1": 0.0, "fdd1": 0.0, "fddd1": 0.0,
        "rshift": 0, "ashift": 0,
        "sub_int_r": 0.0, "sub_int_a": 0.0,
        "stretch_r": 0.0, "stretch_a": 0.0,
        "a_stretch_r": 0.0, "a_stretch_a": 0.0,
        "I_mean": 0.0, "Q_mean": 0.0,
        "nlooks": 1, "chirp_ext": 0,
        "deskew": "n", "Flip_iq": "n", "offset_video": "n",
        "scnd_rng_mig": "n", "rng_spec_wgt": 1.0,
        "rm_rng_band": 0.0, "rm_az_band": 0.0,
        "SC_identity": 5,           # ALOS-2, following GMTSAR's table
        "orbdir": "A" if "__A" in os.path.basename(image) else "D",
        "lookdir": "R",             # ALOS-2 is right-looking
        "led_file": os.path.basename(leader),
        "input_file": os.path.basename(image),
        "date": hdr["scene_id"].split("-")[-1] if hdr["scene_id"] else "",
    }
    if extra:
        out.update(extra)
    return out


def scan(datadir, pols=("HH", "HV"), dem=None):
    """Directory -> GeoDataFrame, matching insardev's mission contract."""
    import geopandas as gpd
    import pandas as pd

    records = []
    for pol in pols:
        for sid, (led, img) in find_scenes(datadir, pol).items():
            hdr = leader_header(led)
            par = leader_params(led)
            meta = image_meta(img)
            orb = orbit(led)
            asc = "__A" in sid
            records.append({
                "sceneId": hdr["scene_id"],
                "polarization": pol,
                "scene": os.path.splitext(os.path.basename(img))[0],
                "startTime": hdr["start_time"],
                "path": img,
                "leader": led,
                "flightDirection": "A" if asc else "D",
                "lookDirection": "R",
                "geometry": footprint(orb, meta, par, hdr),
            })
    if not records:
        raise ValueError(f"no ALOS-2 LED-/IMG- pairs found in {datadir}")

    df = gpd.GeoDataFrame(pd.DataFrame(records), geometry="geometry",
                          crs="EPSG:4326")
    return (df.sort_values(by=["sceneId", "polarization", "scene"])
              .set_index(["sceneId", "polarization", "scene"]))


def make_scene(leader, image, mode=2):
    """(prm, orbit, slc, reramp) -- reramp is None, this is stripmap."""
    p, o = prm(leader, image), orbit(leader)
    if mode == 0:
        return p, o
    return p, o, slc(image), None
