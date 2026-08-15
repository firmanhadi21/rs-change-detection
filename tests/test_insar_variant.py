"""Job identity must include the job PARAMETERS, not only the granules.

Resubmitting the same pairs to get the DEM and incidence-angle bands produced a
name identical to the geometry-less jobs already on the account. find_jobs would
then return those, and the run would hand back products missing exactly the
bands it was rerun to obtain -- silently, looking like a successful resume.
"""

from earthchange.insar import job_name


def scene(date, path=163, frame=620):
    return {"granule":
            f"S1A_IW_SLC__1SDV_{date.replace('-', '')}T2127{frame % 100:02d}_"
            f"{path:03d}_{frame}",
            "date": date, "path": path, "frame": frame,
            "direction": "descending"}


PAIR = (scene("2024-08-12"), scene("2024-08-24"))


def test_variant_changes_the_name():
    plain = job_name("x", "ts", PAIR)
    geom = job_name("x", "ts", PAIR, "geom")
    assert plain != geom
    assert "geom" in geom


def test_variant_is_still_deterministic():
    assert job_name("a", "ts", PAIR, "geom") == job_name("b", "co", PAIR, "geom")


def test_no_variant_keeps_the_old_name():
    """Existing jobs stay findable: an empty variant must not alter the hash."""
    assert job_name("x", "ts", PAIR, "") == job_name("x", "ts", PAIR)


def test_different_variants_do_not_collide():
    names = {job_name("x", "ts", PAIR, v)
             for v in ("", "geom", "geom2", "burst")}
    assert len(names) == 4
