"""earthchange — multipurpose satellite change detection.

Map deforestation, mining, urbanisation, floods, burns, surface-water change and
multi-epoch urban growth from free Sentinel-1/2 and Landsat data, via Google
Earth Engine or Microsoft Planetary Computer (no account needed). Pure Python.
"""

__version__ = "0.1.89"

# OpenStreetMap's tile servers answer a client that does not name itself with an
# "Access blocked" tile. It arrives as an ordinary HTTP 200 PNG, so nothing
# raises: the warning is simply drawn into the map. contextily's default
# User-Agent, "contextily-<random hex>", names nothing, and is refused.
USER_AGENT = ("earthchange/" + __version__ +
              " (+https://github.com/firmanhadi21/rs-change-detection)")

# CARTO's basemaps (Positron, Voyager, DarkMatter) now answer every request
# without an API key -- whatever the User-Agent or Referer -- with an "API KEY
# REQUIRED" tile, and again as a normal HTTP 200. Esri's canvas basemaps are the
# keyless equivalents: a quiet light grey and a dark grey, no watermark. Plain
# URL templates, which contextily accepts as a source.
_ESRI_CANVAS = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_{}_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}")
LIGHT_BASEMAP = _ESRI_CANVAS.format("Light")
DARK_BASEMAP = _ESRI_CANVAS.format("Dark")


def identify_to_tile_servers(cx):
    """Make contextily send USER_AGENT with every tile request.

    contextily reads tile.USER_AGENT at request time in every release from 1.5
    through 1.7. add_basemap(headers=...) is the public way, but only from 1.7,
    and an older install would take the TypeError as "no basemap".
    """
    cx.tile.USER_AGENT = USER_AGENT
