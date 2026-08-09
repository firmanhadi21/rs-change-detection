"""HYSPLIT engine: the parts that can be checked without running the model.

HYSPLIT itself is a binary the user installs, so most of what can regress here
is on either side of it -- which met files a run resolves to, what goes into
CONTROL, and what comes back out of tdump. Those are exactly the places this
package has already had bugs, so they are where the tests are.
"""

import datetime as dt
import os

import pytest

from earthchange import hysplit as hy


# --------------------------------------------------------------------------
# met_keys: which GDAS1 weekly files a run needs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("start,hours,direction,want", [
    (dt.datetime(2019, 9, 15), 48, "forward", "gdas1/2019/gdas1.sep19.w3"),
    (dt.datetime(2019, 9, 21), 48, "forward", "gdas1/2019/gdas1.sep19.w4"),
    (dt.datetime(2019, 10, 1), 48, "backward", "gdas1/2019/gdas1.sep19.w5"),
    # Backward across a year boundary is the case that quietly asks for a file
    # in the previous December.
    (dt.datetime(2019, 1, 2), 24, "backward", "gdas1/2018/gdas1.dec18.w5"),
])
def test_met_keys_resolves(start, hours, direction, want):
    keys = [k for k, _ in hy.met_keys(start, hours, direction)]
    assert want in keys


def test_backward_reaches_back_forward_does_not():
    """Margin follows the direction of travel.

    A symmetric margin is the bug this replaced: it made every forward run
    starting early in a week download the previous week too, 571 MiB of
    meteorology the parcels never reach.
    """
    start = dt.datetime(2019, 9, 15)
    back = [k for k, _ in hy.met_keys(start, 48, "backward")]
    fwd = [k for k, _ in hy.met_keys(start, 48, "forward")]
    assert "gdas1/2019/gdas1.sep19.w2" in back
    assert "gdas1/2019/gdas1.sep19.w2" not in fwd


def test_met_keys_refuses_before_the_archive():
    with pytest.raises(SystemExit) as exc:
        hy.met_keys(dt.datetime(1997, 9, 15), 48, "forward")
    # Naming the alternative matters: 1997 is a real fire year someone will try.
    assert "1948" in str(exc.value)


@pytest.mark.network
def test_resolved_keys_exist_in_the_bucket():
    """The names are guesses about someone else's layout until checked."""
    import urllib.request

    for key, _ in hy.met_keys(dt.datetime(2019, 9, 15), 48, "forward"):
        req = urllib.request.Request(f"{hy.ARL_BUCKET}/{key}", method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            assert int(r.headers.get("Content-Length", 0)) > 1_000_000, key


# --------------------------------------------------------------------------
# CONTROL: read positionally by HYSPLIT, so order is the whole contract
# --------------------------------------------------------------------------

@pytest.fixture
def control(tmp_path):
    p = tmp_path / "CONTROL"
    hy.write_control(str(p), dt.datetime(2019, 9, 15, 0),
                     [(-1.85, 110.0, 500.0), (-2.10, 111.3, 1500.0)],
                     -48, ["/met/gdas1.sep19.w3", "/met/gdas1.sep19.w2"],
                     str(tmp_path), "tdump")
    return p.read_text().splitlines()


def test_control_record_order(control):
    """Record order per ARL user's guide S262, with 2 locations on lines 3-4.

    HYSPLIT reads this file positionally: a missing line shifts everything
    after it into the wrong variable and the run succeeds with wrong physics.
    """
    assert control[0] == "19 09 15 00"          # start time
    assert control[1] == "2"                    # n locations
    assert control[2].startswith("-1.8500 110.0000 500.0")
    assert control[3].startswith("-2.1000 111.3000 1500.0")
    assert control[4] == "-48"                  # negative = backward
    assert control[5] == "0"                    # vertical motion = data
    assert control[6] == "10000.0"              # model top
    assert control[7] == "2"                    # n met grids
    assert control[8].endswith(os.sep)          # met dir
    assert control[9] == "gdas1.sep19.w3"       # met file
    assert control[10].endswith(os.sep)
    assert control[11] == "gdas1.sep19.w2"
    assert control[12].endswith(os.sep)         # output dir
    assert control[13] == "tdump"
    assert len(control) == 14


def test_control_forward_is_positive(tmp_path):
    p = tmp_path / "CONTROL"
    hy.write_control(str(p), dt.datetime(2019, 9, 15), [(-1.0, 110.0, 500.0)],
                     48, ["/met/x"], str(tmp_path), "tdump")
    assert p.read_text().splitlines()[3] == "48"


# --------------------------------------------------------------------------
# tdump: endpoints back from the model
# --------------------------------------------------------------------------

TDUMP = """\
     1     2
    GDAS    19     9    15     0     0
     2 BACKWARD OMEGA
    19     9    15     0   -1.850  110.000     500.0
    19     9    15     0   -2.100  111.300    1500.0
     1 PRESSURE
     1     1    19     9    15     0     0     0    0.0   -1.850  110.000     500.0     955.0
     2     1    19     9    15     0     0     0    0.0   -2.100  111.300    1500.0     845.0
     1     1    19     9    14    12     0     0  -12.0   -3.010  112.440     620.0     944.0
     2     1    19     9    14    12     0     0  -12.0   -3.550  113.900    1410.0     851.0
"""


@pytest.fixture
def parsed(tmp_path):
    p = tmp_path / "tdump"
    p.write_text(TDUMP)
    return hy.read_tdump(str(p))


def test_tdump_shape(parsed):
    paths, direction = parsed
    assert direction == "BACKWARD"
    assert len(paths) == 2
    assert all(len(p) == 2 for p in paths)


def test_tdump_lon_lat_order(parsed):
    """(lon, lat), matching what _advect produces.

    The file stores lat before lon. Getting this backwards puts Kalimantan in
    the Indian Ocean, which is obvious on a map and invisible in a test that
    only counts points.
    """
    paths, _ = parsed
    _t, lon, lat, _h = paths[0][0]
    assert lon == pytest.approx(112.44)
    assert lat == pytest.approx(-3.01)


def test_tdump_backward_is_ordered_source_first(parsed):
    """Oldest point first, so the arrow always points the way air travelled."""
    paths, _ = parsed
    assert paths[0][0][0] == dt.datetime(2019, 9, 14, 12, tzinfo=dt.UTC)
    assert paths[0][-1][1] == pytest.approx(110.0)      # ends at the receptor
    assert paths[0][0][3] == pytest.approx(620.0)       # height carried


def test_tdump_short_record_raises(tmp_path):
    """Loudly, not silently -- a truncated run must not look like a short path."""
    p = tmp_path / "tdump"
    p.write_text("     1     2\n    GDAS    19     9    15     0     0\n"
                 "     1 FORWARD OMEGA\n"
                 "    19     9    15     0   -1.850  110.000     500.0\n"
                 "     1 PRESSURE\n     1     1    19     9\n")
    with pytest.raises(SystemExit, match="Unparseable"):
        hy.read_tdump(str(p))


def test_tdump_empty_raises(tmp_path):
    p = tmp_path / "tdump"
    p.write_text("")
    with pytest.raises(SystemExit):
        hy.read_tdump(str(p))


# --------------------------------------------------------------------------
# Locating the binary, and explaining macOS
# --------------------------------------------------------------------------

def test_explicit_bad_path_rejected():
    with pytest.raises(SystemExit):
        hy.find_binary("/nope/hyts_std")


def test_install_root_from_exec_dir():
    assert hy._install_root("/Applications/hysplit/exec/hyts_std") == \
        "/Applications/hysplit"


def test_help_texts_name_the_fix():
    # ARL ships HYSPLIT unsigned, so on macOS it is SIGKILLed with no output at
    # all. The message has to carry the command or it is undebuggable.
    assert "xattr -dr com.apple.quarantine" in hy._QUARANTINE_HELP
    assert "hyts_std" in hy.INSTALL_HELP
    assert "applehysp" in hy.INSTALL_HELP


@pytest.mark.skipif(hy.find_binary() is None, reason="HYSPLIT not installed")
def test_found_binary_is_executable():
    exe = hy.find_binary()
    assert os.access(exe, os.X_OK)
