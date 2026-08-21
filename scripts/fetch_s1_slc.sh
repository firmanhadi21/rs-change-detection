#!/bin/bash
# Download Sentinel-1 SLC granules from ASF, authenticating through ~/.netrc.
#
# CREDENTIALS ARE NEVER HANDLED HERE. curl reads the machine entry for
# urs.earthdata.nasa.gov out of ~/.netrc; nothing is passed on the command
# line, so nothing lands in shell history, in a process listing, or in this
# file. If the download 401s, fix ~/.netrc rather than adding a flag.
#
# TWO FLAGS THAT ARE BOTH MANDATORY, AND THE FAILURE MODE IF EITHER IS MISSING.
#
# --location-trusted: Earthdata authorises on urs.earthdata.nasa.gov and then
# redirects to a signed datapool URL. Plain --location drops credentials across
# that hop. Safe only because the redirect chain stays inside NASA's hosts.
#
# --cookie-jar / --cookie: the OAuth handshake returns its token as a COOKIE.
# Without a jar to hold it, every redirect re-authorises and curl bounces
# between the authorize endpoint and the login until it gives up with
# "Maximum (50) redirects followed". That reads exactly like a rejected
# password and is not one -- worth knowing before anyone rotates a credential
# that was working fine.
#
# Resumes with -C -, so an interrupted 3.5 GB download continues rather than
# restarting.
#
#   bash scripts/fetch_s1_slc.sh <granule> [<granule> ...]
set -euo pipefail

DEST="${S1_DEST:-$HOME/GitHub/rs-change-detection/data/slc}"
BASE="https://datapool.asf.alaska.edu/SLC/SD"

if [ $# -eq 0 ]; then
    echo "usage: $0 <granule> [<granule> ...]" >&2
    exit 2
fi
if [ ! -f "$HOME/.netrc" ] || ! grep -q "urs.earthdata.nasa.gov" "$HOME/.netrc"; then
    echo "no Earthdata entry in ~/.netrc — add one before downloading" >&2
    exit 2
fi

mkdir -p "$DEST"
avail=$(df -k "$DEST" | awk 'NR==2 {printf "%.0f", $4/1024/1024}')
echo "destination $DEST  (${avail} GB free)"

# Session cookies only; removed on exit so no Earthdata token is left on disk.
JAR=$(mktemp -t s1cookies)
trap 'rm -f "$JAR"' EXIT

for g in "$@"; do
    out="$DEST/$g.zip"
    if [ -f "$out" ]; then
        echo "already have $(basename "$out")"
        continue
    fi
    echo "fetching $g"
    curl --netrc --location-trusted --fail --retry 3 --retry-delay 5 \
         -b "$JAR" -c "$JAR" \
         -C - -# -o "$out.part" "$BASE/$g.zip"
    mv "$out.part" "$out"
    printf "  %s  %.2f GB\n" "$(basename "$out")" \
        "$(du -k "$out" | awk '{print $1/1024/1024}')"
done

echo
echo "verifying the archives are complete rather than truncated:"
for g in "$@"; do
    out="$DEST/$g.zip"
    [ -f "$out" ] || continue
    if unzip -t "$out" > /dev/null 2>&1; then
        echo "  OK   $(basename "$out")"
    else
        echo "  BAD  $(basename "$out") — remove it and retry" >&2
    fi
done
