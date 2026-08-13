# tests/fixtures/

Small inputs committed so the tests do not need the network or a local `data/`
directory. Keep them small — anything over a few hundred kilobytes belongs in
`data/`, which is untracked.

## `semarang_brt_stops.geojson`

673 Point features: BRT stop locations for the Trans Semarang corridors, in
lon/lat (EPSG:4326).

**Where it came from.** It is the `stops.geojson` written by run
`20260721-141407_transit-access_TransSemarang_7ba18f`, which was fed a
`--transit-file` exported from a public ArcGIS layer of the Trans Semarang
corridors. That original export is not in this repository and was not preserved;
this file is what the run consumed. The byte-identical file appears in run
`20260721-172140_transit-access_Kota Semarang_36320f`, which is the same input
clipped to the Kota Semarang boundary.

**What it is not.** Every feature has **empty properties** — no halte name, no
route or corridor ID, no direction. It is geometry only. That is enough to
re-run `transit-access --transit-file`, and not enough for anything that needs
to know which corridor a stop belongs to. If you need those attributes, go back
to the ArcGIS layer.

**Figures it reproduces.** With `--boundary "Kota Semarang"` and WorldPop 2020,
655 of the 673 stops snap to the road network and the run reports 35.8 % of
1,569,975 people within 500 m, 64.2 % within 1 km. Unclipped, over the larger
Semarang extent, the same stops give 32.1 % of 1,775,843.

Bare stop coordinates for a public bus network, with no attributes carried over.
If the corridor layer's licence turns out to restrict redistribution of the
geometry itself, drop this file and have `test_transit.py` skip.
