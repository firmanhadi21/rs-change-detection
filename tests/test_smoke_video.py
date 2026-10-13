"""smoke-video frame geometry: the size flag, and the aspect it implies.

The pipeline renders WIDTH x HEIGHT and places x in longitude but y in
Mercator, so the frame's pixel ratio has to match the bbox's or the map comes
out stretched. These run before anything downloads, because the cost of
getting the frame wrong is a render that takes minutes and looks plausible.
"""

import math

import pytest

from earthchange.detect import _video_size
from earthchange.smoke_video import frame_size, guess_firms_region

KALIMANTAN = (108.669, -5.336, 118.999, 4.995)
INDONESIA = (94.5, -11.5, 141.5, 6.5)


@pytest.mark.parametrize("text,want", [
    ("1080", (1080, 1080)),
    ("720", (720, 720)),
    ("2880x1108", (2880, 1108)),
    ("2880xauto", (2880, None)),
    ("2880x", (2880, None)),
    ("  1080  ", (1080, 1080)),
    ("2880XAUTO", (2880, None)),
])
def test_video_size_parses(text, want):
    assert _video_size(text) == want


@pytest.mark.parametrize("text", ["0", "32", "widexhigh", "x1080", "1080x1080x2"])
def test_video_size_rejects_nonsense(text):
    with pytest.raises(Exception):
        _video_size(text)


def test_explicit_size_is_passed_through_unchanged():
    assert frame_size((1080, 1080), KALIMANTAN) == (1080, 1080)
    assert frame_size((2880, 1108), INDONESIA) == (2880, 1108)
    # A bare int still means a square frame, as it always did.
    assert frame_size(1080, INDONESIA) == (1080, 1080)


def test_auto_height_keeps_a_near_square_bbox_near_square():
    w, h = frame_size((1080, None), KALIMANTAN)
    assert w == 1080
    assert 0.95 < w / h < 1.2, (w, h)


def test_auto_height_is_even():
    """ffmpeg's h264 encoder refuses odd dimensions."""
    for width in (1080, 1920, 2880):
        assert frame_size((width, None), INDONESIA)[1] % 2 == 0


def test_auto_height_undoes_the_distortion_a_square_frame_would_add():
    """A degree of longitude and of latitude must cover the same pixels.

    Indonesia is 47 degrees across and 18 tall, so the square frame the
    scenario used to force stretched it more than twofold.
    """
    w, s, e, n = INDONESIA
    px_w, px_h = frame_size((2880, None), INDONESIA)

    def merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    per_lon = px_w / (e - w)
    mid, d = (s + n) / 2, 0.01
    per_lat = px_h * ((merc(mid + d) - merc(mid - d)) / (merc(n) - merc(s))) / (2 * d)
    assert abs(per_lat / per_lon - 1) < 0.01, (per_lon, per_lat)

    square = 2880 / (e - w), 2880 * ((merc(mid + d) - merc(mid - d))
                                     / (merc(n) - merc(s))) / (2 * d)
    assert square[1] / square[0] > 2, "a square frame should be visibly wrong"


@pytest.mark.parametrize("word,emphasised", [
    ("major", True),    # what --video-cities documents
    ("big", True),      # what --video-labels documents
    ("true", True),
    ("1", True),
    ("", False),
    (None, False),
])
def test_label_emphasis_accepts_both_documented_words(word, emphasised):
    """--video-labels says 'big' and --video-cities says 'major'.

    Both specs are parsed by the same helper, which used to accept only
    'major' -- so a user following the --video-labels help got a small label
    and no complaint.
    """
    from earthchange.smoke_video import _cities_from

    spec = "SUMATERA,101.5,-1.8" + (f",{word}" if word else "")
    got = _cities_from(spec, (94.5, -11.5, 141.5, 6.5))
    assert got == [("SUMATERA", 101.5, -1.8, emphasised)]


def test_region_guess_covers_the_indonesian_islands():
    for lon, lat in [(113.8, -0.2), (100.6, 0.0), (136.0, -4.8), (120.0, -2.0)]:
        assert guess_firms_region(lon, lat) == "SouthEast_Asia"


def test_smoke_grid_is_not_locked_to_a_square():
    """Guard against the crop that made a wide frame draw the wrong smoke.

    compose.py scaled the aerosol field by WIDTH/270 and cropped it to the
    frame, which silently kept only the top of the field when WIDTH != HEIGHT.
    It cannot be imported here (it reads a run's config and data at import
    time), so this checks the expression is gone rather than re-deriving it.
    """
    from pathlib import Path

    import earthchange.smoke_video as sv

    src = (Path(sv.__file__).parent / "pipeline" / "compose.py").read_text()
    assert "zoom(a, WIDTH / 270" not in src
    assert "NG_W" in src and "_resize(a, (HEIGHT, WIDTH)" in src
