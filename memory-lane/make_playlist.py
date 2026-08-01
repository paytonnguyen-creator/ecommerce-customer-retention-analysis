"""
Turn the shortlist into an actual Spotify playlist.

    Songs I will play to annoy my grandkids in 2046

This is the only script in the project that CHANGES your account, so it does
nothing by default. It prints what it would create and stops. Pass --create to
let it write, and it will still ask for confirmation first.

    python memory-lane/make_playlist.py              # dry run, writes nothing
    python memory-lane/make_playlist.py --create     # asks, then creates

The playlist is created PRIVATE. Pass --public if you want it otherwise; that
flag exists so making a listening history public is a deliberate keystroke
rather than a default.

Simulated track IDs are refused. The demo pipeline invents its catalogue, and
those IDs do not correspond to real recordings -- a playlist built from them
would be 30 tracks of nothing.

Writes: memory-lane/outputs/playlist.json (what was created, for the record)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
LOOKAHEAD_YEARS = 20

SCOPES = "playlist-modify-private playlist-modify-public"

DESCRIPTION = (
    "Scored by a model fitted on the songs I already came back to after a year "
    "of silence, then applied to tracks too new to have proven it. "
    "Behaviour did the predicting; the acoustics barely moved the needle."
)


def load_shortlist() -> pd.DataFrame:
    f = OUT / "core_memory_tracks.csv"
    if not f.exists():
        sys.exit(f"{f} not found. Run: python memory-lane/run_memory_lane.py")
    df = pd.read_csv(f)
    if "track_id" not in df.columns or df.empty:
        sys.exit(f"{f} has no tracks to add.")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true",
                    help="actually create the playlist (default: dry run)")
    ap.add_argument("--public", action="store_true",
                    help="make it public (default: private)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    year = date.today().year + LOOKAHEAD_YEARS
    name = args.name or f"Songs I will play to annoy my grandkids in {year}"

    df = load_shortlist().head(args.limit)
    fake = df["track_id"].astype(str).str.startswith(("sim", "local:"))

    print(f"\n  {name}")
    print(f"  {len(df)} tracks · {'public' if args.public else 'private'}\n")
    for i, r in enumerate(df.itertuples(), 1):
        idx = getattr(r, "memory_lane_index", float("nan"))
        print(f"   {i:2d}. {idx:5.1f}  {getattr(r, 'name', '?')}"
              f"  —  {getattr(r, 'artist', '?')}")

    if fake.any():
        print(f"\n  {fake.sum()} of these are simulated IDs from "
              f"simulate_listener.py and do not exist on Spotify.")
        print("  Run fetch_spotify.py or ingest_history.py against your real "
              "account first.")
        if args.create:
            sys.exit(1)

    if not args.create:
        print("\n  Dry run — nothing was created. Add --create to write it to "
              "your account.")
        return

    answer = input(f"\n  Create this playlist on your Spotify account? [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        sys.exit("  Cancelled.")

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        sys.exit("pip install -r memory-lane/requirements.txt")

    missing = [v for v in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET",
                           "SPOTIPY_REDIRECT_URI") if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)}")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        scope=SCOPES, open_browser=True,
        cache_path=str(HERE / "data" / ".spotify-token-cache")))

    uid = sp.current_user()["id"]
    pl = sp.user_playlist_create(uid, name, public=args.public,
                                 description=DESCRIPTION)
    ids = df["track_id"].dropna().astype(str).tolist()
    for i in range(0, len(ids), 100):
        sp.playlist_add_items(pl["id"], ids[i:i + 100])

    record = {
        "playlist_id": pl["id"],
        "name": name,
        "url": pl.get("external_urls", {}).get("spotify"),
        "public": bool(args.public),
        "tracks": len(ids),
        "created_at": pd.Timestamp.utcnow().isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "playlist.json").write_text(json.dumps(record, indent=2))

    print(f"\n  Created: {record['url']}")
    print(f"  Recorded in {OUT / 'playlist.json'}")


if __name__ == "__main__":
    main()
