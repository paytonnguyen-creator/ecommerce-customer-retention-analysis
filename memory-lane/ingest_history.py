"""
Parse a Spotify Extended Streaming History export into memory-lane/data/.

WHY THIS IS THE PREFERRED INPUT
-------------------------------
The whole project rests on one measurement: how a track's plays were
distributed over time. A song welded to one autumn is a different memory object
from a song played evenly for nine years, and only a timestamped play log can
tell them apart. The Web API cannot -- it returns your last 50 plays and three
pre-ranked "top tracks" windows. The export returns every stream since the
account opened.

HOW TO GET IT (free, no developer app needed)
---------------------------------------------
    Spotify → Account → Privacy settings → "Extended streaming history"
    → Request. It arrives by email in a few days as a zip.

Unzip it anywhere and point this script at the folder:

    python memory-lane/ingest_history.py ~/Downloads/my_spotify_data

TWO EXPORT FORMATS EXIST, AND ONLY ONE IS USEFUL
------------------------------------------------
  * Extended streaming history -- `Streaming_History_Audio_YYYY-YYYY_N.json`,
    fields `ts` / `ms_played` / `spotify_track_uri`. Complete account history.
    This is the one to ask for.
  * "Account data" -- `StreamingHistory0.json`, fields `endTime` / `msPlayed`,
    LAST 12 MONTHS ONLY and no track IDs. Both are read here, but the short one
    cannot support the returner label (which needs a year of dormancy plus a
    return), and the script says so rather than silently producing a report
    built on twelve months of data.

Podcast rows are dropped. A 30-second floor is applied to distinguish a play
from a skip, matching Spotify's own definition of a stream.

Writes: memory-lane/data/streams.csv, memory-lane/data/tracks.csv (stub),
        memory-lane/data/source.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
PLAY_FLOOR_MS = 30_000  # Spotify counts a stream at 30s; so does this

EXTENDED = {
    "ts": "played_at",
    "ms_played": "ms_played",
    "master_metadata_track_name": "name",
    "master_metadata_album_artist_name": "artist",
    "master_metadata_album_album_name": "album",
    "spotify_track_uri": "uri",
}
LEGACY = {
    "endTime": "played_at",
    "msPlayed": "ms_played",
    "trackName": "name",
    "artistName": "artist",
}


def read_export(folder: Path) -> tuple[pd.DataFrame, dict]:
    files = sorted(folder.rglob("*.json"))
    if not files:
        sys.exit(f"No .json files under {folder}")

    frames, log = [], {"files_read": [], "files_skipped": [],
                       "format": None, "podcast_rows_dropped": 0}

    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log["files_skipped"].append(f.name)
            continue
        if not isinstance(payload, list) or not payload:
            log["files_skipped"].append(f.name)
            continue

        keys = set(payload[0])
        if "ts" in keys and "ms_played" in keys:
            mapping, fmt = EXTENDED, "extended"
        elif "endTime" in keys and "msPlayed" in keys:
            mapping, fmt = LEGACY, "legacy_12_month"
        else:
            log["files_skipped"].append(f.name)
            continue

        df = pd.DataFrame(payload)
        if "spotify_episode_uri" in df.columns:
            before = len(df)
            df = df[df["spotify_episode_uri"].isna()]
            log["podcast_rows_dropped"] += before - len(df)

        df = df[[c for c in mapping if c in df.columns]].rename(columns=mapping)
        frames.append(df)
        log["files_read"].append(f.name)
        # "extended" wins if the export mixes both, since it is the superset
        log["format"] = "extended" if "extended" in (log["format"], fmt) else fmt

    if not frames:
        sys.exit("Found JSON files, but none matched a Spotify streaming-history "
                 "layout. Point this at the unzipped export folder.")

    return pd.concat(frames, ignore_index=True), log


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().splitlines()[0] +
                 "\n\nUsage: python memory-lane/ingest_history.py <export folder>")

    folder = Path(sys.argv[1]).expanduser()
    if not folder.exists():
        sys.exit(f"{folder} does not exist")

    raw, log = read_export(folder)
    log["rows_raw"] = int(len(raw))

    raw["played_at"] = pd.to_datetime(raw["played_at"], format="mixed",
                                      utc=True, errors="coerce")
    raw = raw.dropna(subset=["played_at"])

    # Track IDs only exist in the extended export. Without them, fall back to
    # artist+title as the identity key -- imperfect (remasters and live versions
    # collapse together) but better than discarding the history.
    if "uri" in raw.columns:
        raw["track_id"] = raw["uri"].astype(str).str.rsplit(":", n=1).str[-1]
        raw.loc[~raw["uri"].astype(str).str.startswith("spotify:track:"),
                "track_id"] = pd.NA
        log["identity_key"] = "spotify_track_id"
    else:
        raw["track_id"] = pd.NA
        log["identity_key"] = "artist_title_fallback"

    unnamed = raw["track_id"].isna()
    raw.loc[unnamed, "track_id"] = (
        "local:" + raw.loc[unnamed, "artist"].fillna("?").str.lower().str.strip()
        + "|" + raw.loc[unnamed, "name"].fillna("?").str.lower().str.strip()
    )
    log["rows_without_spotify_id"] = int(unnamed.sum())

    raw = raw.dropna(subset=["name"])
    log["rows_after_podcast_and_null_drop"] = int(len(raw))

    plays = raw[raw["ms_played"] >= PLAY_FLOOR_MS].copy()
    log["skips_under_30s"] = int(len(raw) - len(plays))
    log["play_floor_ms"] = PLAY_FLOOR_MS

    DATA.mkdir(parents=True, exist_ok=True)
    streams = raw[["played_at", "track_id", "ms_played"]].sort_values("played_at")
    streams.to_csv(DATA / "streams.csv", index=False)

    # A metadata stub. `duration_ms`, `popularity` and any acoustic features
    # have to come from the API (fetch_spotify.py) -- the export has none of
    # them. Duration is approximated by the longest observed play, which is a
    # lower bound and is flagged as such.
    tracks = (
        raw.groupby("track_id")
        .agg(name=("name", "first"), artist=("artist", "first"),
             album=("album", "first") if "album" in raw.columns else ("name", "first"),
             duration_ms=("ms_played", "max"))
        .reset_index()
    )
    tracks["duration_is_estimated"] = True
    out_tracks = DATA / "tracks.csv"
    if out_tracks.exists():
        prior = pd.read_csv(out_tracks)
        keep = [c for c in prior.columns if c not in tracks.columns or c == "track_id"]
        tracks = tracks.merge(prior[keep], on="track_id", how="left")
        log["merged_with_existing_tracks_csv"] = True
    tracks.to_csv(out_tracks, index=False)

    span = (streams["played_at"].max() - streams["played_at"].min()).days
    source = {
        "ingest": "extended_streaming_history",
        "export_format": log["format"],
        "streams": int(len(streams)),
        "plays_over_30s": int(len(plays)),
        "unique_tracks": int(tracks["track_id"].nunique()),
        "first_play": str(streams["played_at"].min()),
        "last_play": str(streams["played_at"].max()),
        "span_days": int(span),
        "span_years": round(span / 365.25, 2),
        "cleaning": log,
        "history_depth": "full_export",
    }
    if log["format"] == "legacy_12_month":
        source["warning"] = (
            "This is the 12-month 'account data' export, not extended streaming "
            "history. A returner label needs a year of dormancy followed by a "
            "return, so it cannot be built from twelve months. Request the "
            "extended export and rerun.")

    (DATA / "source.json").write_text(json.dumps(source, indent=2))

    print(f"format       : {log['format']}")
    print(f"files read   : {len(log['files_read'])}")
    print(f"streams      : {len(streams):,}  ({len(plays):,} over 30s)")
    print(f"tracks       : {tracks['track_id'].nunique():,}")
    print(f"span         : {source['first_play'][:10]} -> "
          f"{source['last_play'][:10]}  ({source['span_years']} years)")
    if "warning" in source:
        print(f"\nWARNING: {source['warning']}")
    print(f"\nwritten      : {DATA}/streams.csv, {DATA}/tracks.csv")
    print("Next: python memory-lane/run_memory_lane.py")


if __name__ == "__main__":
    main()
