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


def test_span_dates_forward_is_start_plus_hours():
    assert st.span_dates("2026-08-01", 48, "forward") == ("2026-08-01",
                                                          "2026-08-03")


def test_span_dates_backward_reaches_back():
    assert st.span_dates("2019-09-15", 48, "backward") == ("2019-09-13",
                                                           "2019-09-15")


def test_span_dates_are_always_oldest_first():
    """So the text reads in the same direction the arrows on the map point."""
    for direction in ("forward", "backward"):
        lo, hi = st.span_dates("2019-09-15", 72, direction)
        assert lo < hi


def test_span_dates_shows_the_time_when_it_is_not_a_whole_day():
    """A 36 h run lands at midday; rounding to a date would be 12 h wrong."""
    lo, hi = st.span_dates("2026-08-01", 36, "forward")
    assert lo == "2026-08-01" and hi == "2026-08-02 12:00"


def test_subtitle_carries_both_dates_not_a_duration():
    cap = st._captions("X", "2026-08-01", 48, {"Ketapang": 3}, "forward",
                       [(0, 0)], None, 48)
    line = cap["title"].splitlines()[-1]
    assert "2026-08-01" in line and "2026-08-03" in line
    assert "jam ke depan" not in line


def test_backward_subtitle_says_arrived_and_came_from():
    cap = st._captions("X", "2019-09-15", 48, {"Ketapang": 3}, "backward",
                       [(0, 0)], None, 48)
    line = cap["title"].splitlines()[-1]
    assert "tiba pada 2019-09-15" in line
    assert "berasal dari 2019-09-13" in line


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


def test_display_box_expands_to_hold_the_paths():
    """A district-sized AOI with 48 h of travel: every path leaves the frame
    unless the figure grows to hold them."""
    aoi = [109.5, -2.5, 110.5, -1.5]                 # roughly Ketapang
    box = st.display_box(aoi, [107.0, 112.0], [-4.0, 1.0])
    assert box[0] < 107.0 and box[2] > 112.0
    assert box[1] < -4.0 and box[3] > 1.0


def test_display_box_never_shrinks_below_the_aoi():
    aoi = [109.0, -2.0, 111.0, 0.0]
    box = st.display_box(aoi, [110.0], [-1.0])       # paths inside the AOI
    assert box[0] <= aoi[0] and box[2] >= aoi[2]
    assert box[1] <= aoi[1] and box[3] >= aoi[3]


def test_display_box_ignores_one_runaway_parcel():
    """Twenty-four parcels together, one 900 km north. The outlier is drawn to
    the edge and clipped rather than deciding the frame for everyone."""
    xs = [110.0] * 24 + [110.0]
    ys = [-1.8] * 24 + [6.0]
    box = st.display_box([109.5, -2.5, 110.5, -1.5], xs, ys)
    assert box[3] < 3.0, box


def test_display_box_is_not_a_sliver():
    """Equal-aspect axes plus a tall thin extent renders as a strip down the
    middle of the page."""
    box = st.display_box([109.9, -2.0, 110.1, -1.9],
                         [110.0] * 20, list(range(-10, 10)))
    w, h = box[2] - box[0], box[3] - box[1]
    assert 0.5 < (w / h) / st.FIG_ASPECT < 2.0, (w, h)


def test_display_box_stays_on_the_globe():
    box = st.display_box([-179.0, -89.0, 179.0, 89.0], [-179.9], [-89.9])
    assert box[0] >= -180.0 and box[1] >= -90.0
    assert box[2] <= 180.0 and box[3] <= 90.0


def test_subtitle_with_no_districts():
    cap = st._captions("X", "2019-09-15", 48, {}, "forward", [(0, 0)], None, 48)
    assert "melintasi" not in cap["title"]
