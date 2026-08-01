"""
Pull a real Spotify account into memory-lane/data/ via the Web API.

WHAT YOU GET FROM THE API, AND WHAT YOU DON'T
---------------------------------------------
The Web API is generous about *what* you like and stingy about *when* you liked
it. Top tracks come in three fixed windows (~4 weeks / ~6 months / "several
years", already ranked, no play counts). Recently-played is capped at the last
50 items. Saved tracks carry an `added_at`, which is the only real timestamp
here worth anything.

That is not enough to measure how listening was distributed over years, which
is the measurement this project is built on. For that you want the **Extended
Streaming History** export -- a free GDPR download of every stream you have
ever played, with timestamps and ms_played -- fed through `ingest_history.py`.
The API path works without it and produces a weaker version of the same report;
the difference is documented in docs/METHOD.md.

AUDIO FEATURES: READ THIS BEFORE FILING A BUG
---------------------------------------------
On 27 November 2024 Spotify closed `/v1/audio-features`, `/v1/audio-analysis`,
`/v1/recommendations`, related-artists and 30-second preview URLs to
applications created after that date. Apps that already held extended quota
kept access. So a brand-new developer app WILL get 403 on the danceability /
energy / valence / acousticness fields.

This script therefore treats audio features as optional. It asks for them, and
if the answer is 403 it records that fact, carries on with the metadata that is
still available, and tells you the three ways to fill the gap. The rest of the
pipeline runs either way -- and reports which mode it ran in, because a result
computed without acoustic features is a different result and should not be
allowed to look identical.

SETUP
-----
    1. Create an app at https://developer.spotify.com/dashboard
    2. Add http://127.0.0.1:8888/callback as a Redirect URI
    3. export SPOTIPY_CLIENT_ID=...
       export SPOTIPY_CLIENT_SECRET=...
       export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
    4. python memory-lane/fetch_spotify.py

The first run opens a browser for consent. Scopes requested are read-only here;
playlist writing is a separate, opt-in step in `make_playlist.py`.

Writes: memory-lane/data/tracks.csv, memory-lane/data/streams.csv,
        memory-lane/data/source.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"

# Read-only. Writing a playlist needs playlist-modify-private, which is
# requested separately by make_playlist.py so that merely building the report
# never asks for permission to change the account.
SCOPES = " ".join([
    "user-top-read",
    "user-read-recently-played",
    "user-library-read",
])

AUDIO_FEATURE_COLS = [
    "danceability", "energy", "key", "loudness", "mode", "speechiness",
    "acousticness", "instrumentalness", "liveness", "valence", "tempo",
]

DEPRECATION_NOTE = """
  Spotify returned 403 for /v1/audio-features.

  This is expected for developer apps created after 27 Nov 2024 -- the
  endpoint was closed to new applications on that date. It is not a bug in
  this script and not a problem with your credentials.

  Three ways forward, best first:

    1. Run without it. The pipeline's headline finding is that behavioural
       features carry the prediction and acoustic ones add very little, so
       the acoustic-free run loses less than you would think. It will say
       so explicitly in the report rather than pretending otherwise.

    2. Supply your own. Drop a CSV at memory-lane/data/audio_features.csv
       with a `track_id` column plus any of:
           danceability energy valence acousticness speechiness
           instrumentalness tempo loudness
       Sources: an older app of yours that kept extended quota, a research
       dataset, or an offline extractor such as Essentia or librosa run over
       local audio you already own.

    3. Ask Spotify for extended quota for your app, and use an app that
       predates the cutoff.
"""


def _client():
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        sys.exit("pip install -r memory-lane/requirements.txt")

    missing = [v for v in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET",
                           "SPOTIPY_REDIRECT_URI") if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)}\n"
                 f"See the setup notes at the top of this file.")

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(scope=SCOPES, open_browser=True,
                                  cache_path=str(DATA / ".spotify-token-cache")),
        requests_timeout=30, retries=3,
    )


def _paged(fn, limit=50, cap=2000, **kw):
    """Walk a paginated endpoint, stopping at `cap` items."""
    out, offset = [], 0
    while offset < cap:
        page = fn(limit=limit, offset=offset, **kw)
        items = page.get("items", [])
        out.extend(items)
        if len(items) < limit:
            break
        offset += limit
        time.sleep(0.1)
    return out


def collect_tracks(sp) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Top tracks (3 windows) + saved tracks + recently played."""
    rows, streams, log = {}, [], {}

    def note(track, **extra):
        if not track or not track.get("id"):
            return
        r = rows.setdefault(track["id"], {
            "track_id": track["id"],
            "name": track.get("name"),
            "artist": ", ".join(a["name"] for a in track.get("artists", [])),
            "album": (track.get("album") or {}).get("name"),
            "release_date": (track.get("album") or {}).get("release_date"),
            "duration_ms": track.get("duration_ms"),
            "popularity": track.get("popularity"),
            "explicit": track.get("explicit"),
        })
        r.update({k: v for k, v in extra.items() if v is not None})

    for term in ("short_term", "medium_term", "long_term"):
        items = _paged(sp.current_user_top_tracks, limit=50, cap=200,
                       time_range=term)
        for rank, t in enumerate(items, 1):
            note(t, **{f"top_rank_{term}": rank})
        log[f"top_{term}"] = len(items)

    saved = _paged(sp.current_user_saved_tracks, limit=50, cap=2000)
    for s in saved:
        note(s.get("track"), added_at=s.get("added_at"))
    log["saved"] = len(saved)

    # Capped at 50 by the API. Kept because it is the only true play-by-play
    # the Web API offers -- and it is exactly why the streaming-history export
    # is the recommended path instead.
    recent = sp.current_user_recently_played(limit=50).get("items", [])
    for r in recent:
        note(r.get("track"))
        if r.get("track", {}).get("id"):
            streams.append({
                "played_at": r["played_at"],
                "track_id": r["track"]["id"],
                "ms_played": r["track"].get("duration_ms"),  # not reported; assumed full
                "ms_played_is_assumed": True,
            })
    log["recently_played"] = len(recent)

    return pd.DataFrame(rows.values()), pd.DataFrame(streams), log


def attach_audio_features(sp, tracks: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Try for audio features; degrade gracefully and loudly if they are gone."""
    ids = tracks["track_id"].dropna().tolist()
    feats, blocked = [], False

    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            got = sp.audio_features(batch)
        except Exception as e:  # spotipy raises SpotifyException on 403
            if "403" in str(e) or "404" in str(e):
                blocked = True
                break
            raise
        feats.extend([f for f in (got or []) if f])
        time.sleep(0.1)

    if blocked or not feats:
        print(DEPRECATION_NOTE)
        local = DATA / "audio_features.csv"
        if local.exists():
            side = pd.read_csv(local)
            merged = tracks.merge(side, on="track_id", how="left")
            have = [c for c in AUDIO_FEATURE_COLS if c in side.columns]
            print(f"  Using {local} instead: {len(side):,} rows, "
                  f"features {', '.join(have)}")
            return merged, {"audio_features": "user_supplied_csv",
                            "audio_feature_columns": have,
                            "audio_feature_coverage": float(
                                merged[have[0]].notna().mean()) if have else 0.0}
        return tracks, {"audio_features": "unavailable",
                        "audio_feature_columns": [],
                        "audio_feature_coverage": 0.0,
                        "reason": "403 from /v1/audio-features (endpoint closed "
                                  "to apps created after 2024-11-27)"}

    af = pd.DataFrame(feats)[["id"] + AUDIO_FEATURE_COLS].rename(
        columns={"id": "track_id"})
    merged = tracks.merge(af, on="track_id", how="left")
    return merged, {"audio_features": "spotify_api",
                    "audio_feature_columns": AUDIO_FEATURE_COLS,
                    "audio_feature_coverage": float(
                        merged["energy"].notna().mean())}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    sp = _client()
    me = sp.current_user()
    print(f"Authenticated as {me.get('display_name')} ({me.get('id')})")

    tracks, streams, log = collect_tracks(sp)
    tracks, af_log = attach_audio_features(sp, tracks)

    tracks.to_csv(DATA / "tracks.csv", index=False)
    if len(streams):
        streams.to_csv(DATA / "streams.csv", index=False)

    source = {
        "ingest": "spotify_web_api",
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "unique_tracks": int(len(tracks)),
        "counts": log,
        **af_log,
        "history_depth": "api_only",
        "warning": ("The Web API exposes only the last 50 plays. Per-track "
                    "play counts and listening dates are therefore estimated "
                    "from top-track ranks, not measured. Run ingest_history.py "
                    "on a Extended Streaming History export for real ones."),
    }
    (DATA / "source.json").write_text(json.dumps(source, indent=2))

    print(f"\ntracks       : {len(tracks):,}")
    print(f"streams      : {len(streams):,} (API cap is 50)")
    print(f"audio feats  : {source['audio_features']} "
          f"({source['audio_feature_coverage']:.0%} coverage)")
    print(f"written      : {DATA}/tracks.csv, {DATA}/source.json")
    print("\nNext: python memory-lane/run_memory_lane.py")


if __name__ == "__main__":
    main()
