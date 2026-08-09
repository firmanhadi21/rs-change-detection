"""smoke-track option handling, up to the point where data is needed.

Everything here runs before Earth Engine and before the met download, on
purpose: these are the mistakes a user makes at the prompt, and each one should
come back in a second rather than after a 571 MiB download.
"""

import pytest

from earthchange import smoke_track as st


def test_parses_named_receptors():
    got = st.parse_receptors("Pontianak,109.33,-0.02; Kuching,110.34,1.55")
    assert got == [(109.33, -0.02, "Pontianak"), (110.34, 1.55, "Kuching")]


def test_tolerates_whitespace_and_trailing_semicolon():
    got = st.parse_receptors("  Pontianak , 109.33 , -0.02 ;  ")
    assert got == [(109.33, -0.02, "Pontianak")]


@pytest.mark.parametrize("spec,why", [
    ("Pontianak,-0.02", "two fields, not three"),
    ("Pontianak,109.33,-0.02,extra", "four fields"),
    ("Pontianak,x,y", "coordinates are not numbers"),
    ("", "nothing at all"),
])
def test_rejects_malformed(spec, why):
    with pytest.raises(SystemExit):
        st.parse_receptors(spec)


def test_swapped_lat_lon_says_longitude_first():
    """Latitude-first is the mistake people actually make.

    Out of range is the only signal available -- 109.33 as a latitude is
    impossible -- so the message has to spend it on naming the real cause.
    """
    with pytest.raises(SystemExit) as exc:
        st.parse_receptors("Pontianak,-0.02,109.33")
    assert "longitude first" in str(exc.value)


def test_receptors_refused_going_forward():
    with pytest.raises(SystemExit, match="arrive AT"):
        st._check_opts("gee", "2019-09-15", "hysplit", "forward",
                       "Pontianak,109.33,-0.02", None)


def test_backward_refused_on_the_kinematic_engine():
    """Reversing a single-level integrator would look like source attribution
    while being no more defensible than the forward fan."""
    with pytest.raises(SystemExit, match="needs --engine hysplit"):
        st._check_opts("gee", "2019-09-15", "kinematic", "backward", None, None)


def test_mpc_backend_refused():
    with pytest.raises(SystemExit, match="backend gee"):
        st._check_opts("mpc", "2019-09-15", "kinematic", "forward", None, None)


def test_missing_date_refused():
    with pytest.raises(SystemExit, match="--date"):
        st._check_opts("gee", None, "kinematic", "forward", None, None)


def test_kinematic_forward_passes_and_needs_no_binary():
    named, exe = st._check_opts("gee", "2019-09-15", "kinematic", "forward",
                                None, None)
    assert named is None and exe is None


def test_release_heights_default_spans_the_boundary_layer():
    # The spread between these is the wind shear a single-level engine cannot
    # show; 100 m alone under-reaches, which is the whole reason for HYSPLIT.
    assert st.DEFAULT_HEIGHTS == (100.0, 500.0, 1500.0)


def test_caveats_say_which_engine_produced_the_figure():
    assert "ILUSTRASI, BUKAN ATRIBUSI" in st.DEFAULT_CAVEAT
    assert "hysplit" in st.DEFAULT_CAVEAT
    assert "HYSPLIT" in st.HYSPLIT_CAVEAT
    assert "bukan dispersi" in st.HYSPLIT_CAVEAT


LONG_NAMES = {"Kota Pontianak": 9, "Kotawaringin Timur": 8,
              "Kota Singkawang": 7, "Bengkayang": 6, "Sambas": 5}


@pytest.mark.parametrize("direction", ["forward", "backward"])
def test_subtitle_fits_the_figure(direction):
    """The rendered line, prefix included -- not just the district list.

    Counting districts overflowed the moment one was called "Kota Pontianak".
    Budgeting only the list still overflowed, because the prefix ahead of it is
    another seventy characters and is longer going backward than forward.
    """
    cap = st._captions("X", "2019-09-15", 48, LONG_NAMES, direction, [(0, 0)],
                       None, 48)
    line = cap["title"].splitlines()[-1]
    assert len(line) <= st.SUBTITLE_CHARS, f"{len(line)}: {line}"
    assert "Kota Pontianak (9)" in line       # the top district still shown


def test_subtitle_survives_absurd_names():
    cap = st._captions("X", "2019-09-15", 48, {"Q" * 200: 1}, "forward",
                       [(0, 0)], None, 48)
    assert len(cap["title"].splitlines()[-1]) <= st.SUBTITLE_CHARS


def test_coverage_message_names_the_range():
    """The default failure is 'Image.gt: ... Got 0 and 1', which says nothing
    about dates. This message has to."""
    msg = st.coverage_message("FIRMS", "2026-08-09", "2000-11-01", "2026-08-08")
    assert "2026-08-09" in msg and "2000-11-01" in msg and "2026-08-08" in msg


def test_coverage_message_explains_a_day_past_the_archive():
    msg = st.coverage_message("FIRMS", "2026-08-09", "2000-11-01", "2026-08-08",
                              st.LATE_HINT[st.FIRMS_IC])
    assert "smoke-video" in msg          # the live feed, for recent days


def test_coverage_message_explains_a_day_before_the_archive():
    msg = st.coverage_message("CAMS PM2.5", "2015-09-30", "2016-06-22",
                              "2026-08-08", st.LATE_HINT[st.CAMS_IC])
    assert "begins 2016-06-22" in msg
    # The lag hint is about recent days and would be nonsense for 2015.
    assert "lags" not in msg


def test_window_message_does_the_arithmetic_for_you():
    """Partial coverage is the trap: FIRMS has the seed day, ERA5 does not have
    the second day of the run. Naming the archive's end leaves the user to work
    out a usable --date, so the message works it out."""
    import datetime as dt
    have_hi = dt.datetime(2026, 8, 3, 23, tzinfo=dt.UTC)
    msg = st.window_message(
        "ERA5 100 m wind",
        dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
        dt.datetime(2026, 8, 10, tzinfo=dt.UTC),
        dt.datetime(1943, 5, 11, 4, tzinfo=dt.UTC), have_hi, 48, "forward")
    # 48 h forward off an archive ending 3 Aug means the last usable day is 1 Aug.
    assert "2026-08-01" in msg
    assert "smoke-video" in msg


def test_window_message_backward_shifts_the_other_end():
    import datetime as dt
    msg = st.window_message(
        "ERA5 100 m wind",
        dt.datetime(2016, 6, 22, tzinfo=dt.UTC),
        dt.datetime(2016, 6, 24, tzinfo=dt.UTC),
        dt.datetime(2016, 6, 22, tzinfo=dt.UTC),
        dt.datetime(2026, 8, 3, tzinfo=dt.UTC), 48, "backward")
    # Going back 48 h, the EARLIEST usable date moves forward instead.
    assert "2016-06-24" in msg


def test_subtitle_with_no_districts():
    cap = st._captions("X", "2019-09-15", 48, {}, "forward", [(0, 0)], None, 48)
    assert "melintasi" not in cap["title"]
