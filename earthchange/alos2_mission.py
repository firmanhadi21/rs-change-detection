"""ALOS-2 as an insardev mission: scanner, scene extraction, alignment.

WHY THIS INHERITS FROM Nisar RATHER THAN COPYING IT. insardev's align layer is
almost entirely mission-agnostic: align_ref and align_rep talk to
`self._make_scene`, `self._get_topo_llt`, `PRM` and `self._xcorr_refine`, and
nothing else that knows what a satellite is. The alignment itself is
geometry-driven -- project a coarse DEM into both scenes with SAT_llt2rat, fit
a bilinear offset model, then refine it by cross-correlating amplitude patches
-- and none of that cares about the file format.

Exactly one method in that path opens a file: _xcorr_refine. So the class
layout is

    ALOS2_slc(Satellite)             scanning and _make_scene, all ours
    ALOS2_align(ALOS2_slc, Nisar_align)
                                     align_ref/align_rep inherited verbatim,
                                     _xcorr_refine overridden for CEOS

and the MRO puts ALOS2_slc first, so our __init__ and _make_scene win while
Nisar's alignment logic is reused rather than duplicated. The cost is a
dependency on upstream internals; the benefit is that improvements to the
alignment arrive for free and cannot silently diverge. If upstream renames
_xcorr_refine or changes its signature, the import-time check below fails
loudly instead of the pipeline quietly running Nisar's HDF5 path.

WHAT ACTUALLY DIFFERS FROM NISAR, and it is not the parts that look hard:

  * One polarisation per file. A NISAR RSLC holds every polarisation and both
    frequencies in one HDF5, so its records share a path and select a dataset.
    An ALOS-2 CEOS scene is one file per polarisation, named IMG-HH-... , so
    each record carries its own path and the dataset name is meaningless.
  * The pair does not share a range grid. Lombok is 8710 bins on one date and
    8688 on the other; Brazil is 9072 and 9104. This turned out NOT to need
    special handling -- align_rep reads num_rng_bins from each scene's own PRM
    and _xcorr_refine bounds-checks each image against its own shape -- but it
    is the first thing to suspect if alignment misbehaves.
  * No geolocation grid. L1.1 is slant range and carries no corner
    coordinates, so the footprint is computed from the orbit rather than read.

    from earthchange.alos2_mission import ALOS2
    a = ALOS2('~/Teaching/UNDIP/InSAR/EQ/Pair1/raw', DEM='.../dem.grd')
    a.to_dataframe()
"""

import os

import numpy as np

from . import alos2

try:
    from insardev_pygmtsar.Satellite import Satellite
    from insardev_pygmtsar.Nisar_align import Nisar_align
    from insardev_pygmtsar.PRM import PRM
except ImportError as exc:                                # pragma: no cover
    raise ImportError(
        "needs insardev_pygmtsar; run under the insardev-test env"
    ) from exc

# Fail at import, not at the end of a long run, if the method we override has
# moved. Inheriting from a third-party class means its shape is part of our
# contract, so assert the part we depend on.
for _needed in ("align_ref", "align_rep", "_xcorr_refine", "_get_h5_path"):
    if not hasattr(Nisar_align, _needed):
        raise ImportError(
            f"insardev_pygmtsar.Nisar_align has no {_needed}; this module "
            f"was written against an API that has since changed")


def _xcorr_batch_ceos(path1, path2, slc_path, patches, patch_size,
                      min_response=0.2):
    """CEOS twin of Nisar_align._xcorr_batch.

    Kept byte-for-byte equivalent in its statistics -- same Hann window, same
    amplitude normalisation, same phaseCorrelate call, same truncation
    compensation -- because any difference here shows up as a bias in the
    fitted offset model and would be attributed to the data rather than to
    this function. The only change is where the patches come from.

    Runs in a joblib worker, so it takes paths and opens them itself.
    """
    import cv2

    half = patch_size // 2
    hann = np.outer(np.hanning(patch_size),
                    np.hanning(patch_size)).astype(np.float32)

    results = []
    ds1 = alos2.CeosSLC(path1)
    ds2 = alos2.CeosSLC(path2)

    for p in patches:
        cy1, cx1 = p["cy1"], p["cx1"]
        cy2, cx2 = p["cy2"], p["cx2"]
        frac_a = p.get("frac_a", 0.0)
        frac_r = p.get("frac_r", 0.0)

        patch1 = ds1[cy1 - half:cy1 + half, cx1 - half:cx1 + half]
        patch2 = ds2[cy2 - half:cy2 + half, cx2 - half:cx2 + half]
        if patch1.shape != (patch_size, patch_size) or \
           patch2.shape != (patch_size, patch_size):
            continue

        valid = (patch1 != 0) & (patch2 != 0)
        if valid.sum() < 0.5 * valid.size:
            continue

        amp1 = np.abs(patch1).astype(np.float32)
        amp2 = np.abs(patch2).astype(np.float32)
        amp1_norm = ((amp1 - amp1.mean()) / (amp1.std() + 1e-10)).astype(
            np.float32)
        amp2_norm = ((amp2 - amp2.mean()) / (amp2.std() + 1e-10)).astype(
            np.float32)

        (dx, dy), response = cv2.phaseCorrelate(amp1_norm * hann,
                                                amp2_norm * hann)
        if response > min_response:
            results.append({"cy1": cy1, "cx1": cx1,
                            "dy": dy - frac_a, "dx": dx - frac_r,
                            "response": response})
    return results


class ALOS2_slc(Satellite):
    """Scan a directory of CEOS L1.1 scenes into insardev's record frame."""

    def __init__(self, datadir, DEM=None, pols=("HH",), geoid=None):
        import pandas as pd

        self.datadir = os.path.expanduser(datadir)
        self.DEM = DEM
        self.geoid = geoid
        self.pols = tuple(pols)
        # NISAR's frequency band, which ALOS-2 has no equivalent of. It is set
        # to a placeholder rather than left None because transform() reaches
        # for nisar_get_frequencies(h5py) when it is None, and because it is
        # then passed down to the SLC reader, which ignores it. Any value in
        # ('A', 'B') works; none of them mean anything here.
        self.frequency = "A"

        df = alos2.scan(self.datadir, pols=self.pols)

        # Level 0 groups the scenes that can be paired. NISAR builds it from
        # trackNumber and frameNumber, which ALOS-2 L1.1 does not carry as
        # fields -- but the product id does: ALOS2 + 5-digit orbit + 4-digit
        # path/frame. Both Lombok scenes end 7020 and both Brazil scenes end
        # 6990 while their orbit halves differ, which is the grouping we need.
        # Derived from the naming convention rather than read from metadata,
        # so it is checked in scripts/alos2_test_mission.py rather than
        # trusted.
        scene_names = df.index.get_level_values(2)
        group = [self._path_frame(s) for s in scene_names]
        df = df.reset_index()
        df["sceneId"] = group
        df = (df.sort_values(by=["sceneId", "polarization", "scene"])
                .set_index(["sceneId", "polarization", "scene"]))
        self.df = df

        print(f"NOTE: Loaded {len(df)} ALOS-2 scenes "
              f"({', '.join(self.pols)}) from {self.datadir}.")

    @staticmethod
    def _path_frame(scene_name):
        """'IMG-HH-ALOS2214327020-180512-FBDR1.1__A' -> '7020_A'."""
        import re
        m = re.search(r"ALOS2(\d{5})(\d{4})", scene_name)
        if not m:
            raise ValueError(f"cannot read path/frame from {scene_name!r}")
        direction = "A" if scene_name.endswith("__A") else "D"
        return f"{m.group(2)}_{direction}"

    # --- paths -----------------------------------------------------------
    def _get_h5_path(self, scene):
        """Path to the scene's image file. Named for the interface, not HDF5."""
        return self.get_record(scene)["path"].iloc[0]

    def _get_leader_path(self, scene):
        return self.get_record(scene)["leader"].iloc[0]

    def _get_slc_path(self, scene):
        """There is no dataset name inside a CEOS file; one file, one pol."""
        return self.get_record(scene).index.get_level_values(1)[0]

    # --- the mission contract --------------------------------------------
    def _make_scene(self, scene, mode=2, debug=False):
        """(prm_dict, orbit_df) at mode 0, (prm, orbit, slc, None) at mode 2.

        The asymmetry -- a PRM object at mode 0 and a plain dict at mode 2 --
        is insardev's, matched here deliberately so align_ref and align_rep
        can be inherited without adaptation.
        """
        image = self._get_h5_path(scene)
        leader = self._get_leader_path(scene)

        prm_dict = alos2.prm(leader, image)
        orbit_df = alos2.orbit(leader)

        if mode == 0:
            prm = PRM()
            prm.set(**prm_dict)
            prm.orbit_df = orbit_df
            return prm, orbit_df

        # Reading the whole SLC is what insardev expects here; at ~1.5 GB per
        # ALOS-2 scene that is real memory, so it is done only at mode 2.
        slc_data = alos2.CeosSLC(image)[...]
        return prm_dict, orbit_df, slc_data, None


class ALOS2_align(ALOS2_slc, Nisar_align):
    """Alignment, reusing Nisar's geometry path and replacing its file reads."""

    def _xcorr_refine(self, scene_ref, scene_rep, prm_rep, patch_size=512,
                      n_jobs=8, min_response=0.2, debug=False):
        """Nisar_align._xcorr_refine with CEOS reads.

        Reproduced rather than inherited because the upstream method resolves
        `_xcorr_batch` and `h5py` from its own module globals, which a
        subclass cannot redirect. The patch grid, the bounds checks and the
        fit are kept identical; only the two file accesses differ.
        """
        from joblib import Parallel, delayed
        from insardev_pygmtsar.utils_satellite import xcorr_fitoffset

        path1 = self._get_h5_path(scene_ref)
        path2 = self._get_h5_path(scene_rep)

        # Each image is measured against ITS OWN shape. The two dates do not
        # share a range grid on either test dataset, so a single nx here would
        # silently drop or invent patches at the swath edge.
        ny1, nx1 = alos2.CeosSLC(path1).shape
        ny2, nx2 = alos2.CeosSLC(path2).shape

        n_rows = max(4, (ny1 - patch_size) // (2 * patch_size) + 1)
        n_cols = max(4, (nx1 - patch_size) // (2 * patch_size) + 1)

        ashift = prm_rep.get("ashift") + prm_rep.get("sub_int_a")
        rshift = prm_rep.get("rshift") + prm_rep.get("sub_int_r")
        stretch_a = prm_rep.get("stretch_a")
        stretch_r = prm_rep.get("stretch_r")
        a_stretch_a = prm_rep.get("a_stretch_a")
        a_stretch_r = prm_rep.get("a_stretch_r")

        if debug:
            print(f"Xcorr refinement: {n_rows}x{n_cols} = "
                  f"{n_rows*n_cols} patches over {ny1}x{nx1} vs {ny2}x{nx2}")
            print(f"Geometry: ashift={ashift:.2f}, rshift={rshift:.2f}")

        half = patch_size // 2
        patches = []
        for row in range(n_rows):
            cy1 = int((row + 0.5) * ny1 / n_rows)
            for col in range(n_cols):
                cx1 = int((col + 0.5) * nx1 / n_cols)
                cy2_f = cy1 + ashift + stretch_a * cx1 + a_stretch_a * cy1
                cx2_f = cx1 + rshift + stretch_r * cx1 + a_stretch_r * cy1
                cy2, cx2 = int(cy2_f), int(cx2_f)
                if cy1 < half or cy1 > ny1 - half:
                    continue
                if cy2 < half or cy2 > ny2 - half:
                    continue
                if cx1 < half or cx1 > nx1 - half:
                    continue
                if cx2 < half or cx2 > nx2 - half:
                    continue
                patches.append({"cy1": cy1, "cx1": cx1, "cy2": cy2,
                                "cx2": cx2, "frac_a": cy2_f - cy2,
                                "frac_r": cx2_f - cx2})

        if debug:
            print(f"Valid patches: {len(patches)}")
        if not patches:
            raise RuntimeError(
                "no patches survived the bounds check -- the geometry offset "
                "is larger than the scene overlap")

        n_batches = min(n_jobs, len(patches))
        size = (len(patches) + n_batches - 1) // n_batches
        batches = [patches[i:i + size]
                   for i in range(0, len(patches), size)]
        batch_results = Parallel(n_jobs=n_batches)(
            delayed(_xcorr_batch_ceos)(path1, path2, None, batch,
                                       patch_size, min_response)
            for batch in batches)
        results = [r for b in batch_results for r in b]

        if debug:
            print(f"Xcorr results: {len(results)} above "
                  f"response {min_response}")

        corrections = xcorr_fitoffset(results, nx=nx1, ny=ny1, debug=debug)
        if corrections is None:
            raise RuntimeError(
                "xcorr fitoffset failed -- too few valid patches")
        return corrections


class ALOS2(ALOS2_align):
    """ALOS-2 PALSAR-2 L1.1 data manager, scanning through alignment.

    For geocoding use earthchange.alos2_transform.ALOS2 instead, which adds
    transform(). The split keeps this module importable without pulling in
    Nisar_transform, so the alignment path can be tested on its own.
    """

    def info(self):
        if self.df is None or len(self.df) == 0:
            return {"error": "No data loaded"}
        dates = self.df.startTime.dt.date.unique()
        return {
            "n_scenes": len(self.df),
            "n_dates": len(dates),
            "date_range": (str(min(dates)), str(max(dates))),
            "groups": sorted(self.df.index.get_level_values(0).unique()),
            "polarizations":
                sorted(self.df.index.get_level_values(1).unique()),
        }
