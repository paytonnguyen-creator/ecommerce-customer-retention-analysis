"""
Open-play court simulator: a declared arrival model, and an emergent paddle stack.

THE ONE THING TO UNDERSTAND BEFORE READING ANY RESULT
-----------------------------------------------------
This file contains two very different kinds of statement, and the whole
project's honesty depends on not confusing them.

(1) ASSUMPTIONS. How many people want to play at 6pm on a 72F Tuesday. That
    is written down in `ASSUMPTIONS` below, in the open. It is a hypothesis
    about behaviour, not a measurement. Any later chart showing "demand peaks
    at 65-75F" is *re-reading this dictionary through a regression*. It is
    evidence that the pipeline works, and evidence of nothing else. Every such
    figure in this project is labelled RECOVERED.

(2) CONSEQUENCES. Given those arrivals, eight courts, four players a game,
    and a first-in-first-out rack of paddles -- how long is the line? Nobody
    writes that down. It falls out of the interaction between a random
    arrival process and a finite server pool, and it behaves in ways the
    assumptions do not telegraph: waiting is convex in demand, so the last
    10% of arrivals cause far more than 10% of the pain, and two rotation
    rules with identical game throughput produce very different waits. Those
    results are labelled EMERGENT, and they are what the project is about.

The mechanics being simulated are the real ones:

  - Paddles, not people, hold the place in line. A group of four arriving
    together puts four paddles in the rack; the next four paddles off the
    front play each other regardless of who came with whom.
  - A game is to 11, win by 2 -- call it 12-13 minutes.
  - Under "all four off", the court empties after each game and four new
    paddles come off the stack. Under "winners stay", the winning pair holds
    the court and only two paddles are drawn. Same games per hour either way.
    Very different odds of getting on if you just arrived.
  - People give up. Patience is finite, and it is much shorter before your
    first game than after it -- once you have played, you are socially
    committed and the stack is full of people you now know.
  - People go home. A session is a duration, not a game count, so waiting
    does not extend anyone's evening; it eats it.

COMMON RANDOM NUMBERS: every scenario re-draws its arrivals, game lengths and
patience thresholds from a stream seeded on (park, date) alone -- never on the
scenario. So the same people, wanting the same games, on the same afternoon,
meet different court policies. Differences between scenarios are the policy,
not sampling noise.

Run:    python pickleball/analysis/simulate_courts.py     (~4 minutes)
Reads:  pickleball/data/hourly_weather.csv
Writes: pickleball/data/park_hours.csv       one row per park-hour (baseline)
        pickleball/data/wait_histogram.csv   time-to-first-game, binned, by hour
        pickleball/data/scenarios.csv        per-park-hour, each policy, 2015
        pickleball/data/assumptions.json     the declared behaviour model

Player-level rows are aggregated on the way out rather than written: a million
player-visits is not a git artefact, and every downstream number is either a
sum (kept exactly) or a distribution (kept as a fixed-bin histogram).
"""

from __future__ import annotations

import hashlib
import heapq
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ── The declared behaviour model ─────────────────────────────────────────────
# Everything here is an assumption. It is dumped verbatim to assumptions.json
# so a reader can attack the inputs directly instead of reverse-engineering
# them out of the outputs.
ASSUMPTIONS = {
    "peak_groups_per_hour": 24.0,
    "park_pull": {"Park A": 1.00, "Park B": 0.84, "Park C": 0.70, "Park D": 0.55, "Park E": 0.42},
    "courts_per_park": 8,
    "group_size_probs": {"1": 0.16, "2": 0.44, "3": 0.14, "4": 0.26},
    "temp_peak_f": 71.0,
    "temp_sigma_cold_f": 13.0,
    "temp_sigma_hot_f": 11.0,
    "temp_floor": 0.04,
    "wet_multiplier": 0.10,
    "wind_penalty_per_ms_above_5": 0.07,
    "annual_growth": 0.22,
    "growth_centre_years": 1.5,
    "game_minutes_mean": 12.5,
    "game_minutes_sd": 3.0,
    "game_minutes_clip": [7.0, 25.0],
    "patience_first_game_median_min": 28.0,
    "patience_sigma_log": 0.60,
    "patience_multiplier_after_first_game": 2.2,
    "session_minutes_mean": 85.0,
    "session_minutes_sd": 28.0,
    "min_session_remaining_min": 15.0,
    "_notes": [
        "The temperature curve is the project's central hypothesis, not a finding.",
        "Growth is included so the forecast faces real non-stationarity: the model "
        "trains on 2012-2014 and is scored on a 2015 that is materially busier.",
        "The calendar belongs to the weather record (real Seattle, 2012-2015). It is "
        "not a claim about when pickleball grew.",
    ],
}

HOURLY_SHAPE = {  # relative arrival intensity by hour of day
    "weekday": {6: .18, 7: .34, 8: .55, 9: .78, 10: .72, 11: .55, 12: .44, 13: .34,
                14: .32, 15: .40, 16: .62, 17: .92, 18: 1.00, 19: .74, 20: .40},
    "weekend": {6: .10, 7: .28, 8: .62, 9: .88, 10: 1.00, 11: .96, 12: .82, 13: .70,
                14: .66, 15: .68, 16: .70, 17: .64, 18: .52, 19: .34, 20: .18},
}

COURT_CAPACITY = 4  # players per game
SEED_SALT = "pickleball-bottleneck-v1"
WAIT_BIN_MIN, N_WAIT_BINS = 2, 46  # 2-minute bins, 0-90 min, last bin is overflow

# player state
WAITING, PLAYING, GONE = 0, 1, 2
# event kinds
EV_ARRIVE, EV_FINISH, EV_IMPATIENT = 0, 1, 2


# ── Demand intensity (assumption -> number) ─────────────────────────────────
def temp_factor(t: np.ndarray) -> np.ndarray:
    a = ASSUMPTIONS
    sigma = np.where(t < a["temp_peak_f"], a["temp_sigma_cold_f"], a["temp_sigma_hot_f"])
    bell = np.exp(-(((t - a["temp_peak_f"]) / sigma) ** 2))
    return a["temp_floor"] + (1 - a["temp_floor"]) * bell


def lambda_table(weather: pd.DataFrame) -> pd.DataFrame:
    """Expected groups per hour, per park -- the 'true' demand the sim draws from."""
    a = ASSUMPTIONS
    w = weather[weather["playable"]].copy()

    weekday_shape = np.array([HOURLY_SHAPE["weekday"].get(h, 0.05) for h in range(24)])
    weekend_shape = np.array([HOURLY_SHAPE["weekend"].get(h, 0.05) for h in range(24)])
    hour_idx = w["hour"].to_numpy()
    shape = np.where(w["is_weekend"].to_numpy(), weekend_shape[hour_idx], weekday_shape[hour_idx])

    years = ((w["date"] - pd.Timestamp("2012-01-01")).dt.days / 365.25).to_numpy()
    growth = (1 + a["annual_growth"]) ** (years - a["growth_centre_years"])
    wind_pen = np.clip(
        1 - a["wind_penalty_per_ms_above_5"] * np.clip(w["wind"].to_numpy() - 5, 0, None), 0.25, 1
    )

    base = (
        a["peak_groups_per_hour"]
        * shape
        * temp_factor(w["temp_f"].to_numpy())
        * np.where(w["is_wet"].to_numpy(), a["wet_multiplier"], 1.0)
        * wind_pen
        * growth
    )

    keep = ["date", "hour", "temp_f", "precipitation", "wind", "is_wet", "dow", "is_weekend"]
    frames = []
    for park, pull in a["park_pull"].items():
        f = w[keep].copy()
        f["park"] = park
        f["lam"] = base * pull
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


# ── The paddle stack (mechanism -> consequence) ─────────────────────────────
def simulate_park_day(hours: np.ndarray, lams: np.ndarray, courts: int, rule: str,
                      seed: int, shift_share: float = 0.0):
    """Discrete-event simulation of one park for one day.

    Returns (per-hour dicts, per-player DataFrame).
    """
    a = ASSUMPTIONS
    rng = np.random.default_rng(seed)
    open_t, close_t = float(hours.min()) * 60.0, (float(hours.max()) + 1) * 60.0

    # --- arrivals -----------------------------------------------------------
    sizes = np.array([1, 2, 3, 4])
    size_p = np.array([a["group_size_probs"][str(s)] for s in sizes])

    groups: list[tuple[float, int]] = []
    for hour, lam in zip(hours, lams):
        n = rng.poisson(lam)
        if n == 0:
            continue
        offs = rng.random(n)
        gsz = rng.choice(sizes, size=n, p=size_p)
        groups.extend(((hour + o) * 60.0, int(g)) for o, g in zip(offs, gsz))
    groups.sort()

    # Demand-shifting policy. This is the product working, so it moves people
    # the way the product would: an arrival in the busiest hour is offered the
    # quietest slot within two hours either side, and takes it `shift_share` of
    # the time. Nudging everyone uniformly earlier just rebuilds the queue
    # ninety minutes sooner -- the direction has to be chosen from the demand
    # curve, not assumed.
    if shift_share > 0 and groups:
        peak_hour = int(hours[int(np.argmax(lams))])
        lam_by_hour = dict(zip(hours.astype(int), lams))
        candidates = [h for h in range(peak_hour - 2, peak_hour + 3) if h in lam_by_hour]
        target = min(candidates, key=lambda h: lam_by_hour[h])
        if target != peak_hour:
            moved = []
            for t, g in groups:
                if int(t // 60) == peak_hour and rng.random() < shift_share:
                    moved.append(((t % 60) / 60.0 * 60 + target * 60.0, g))
                else:
                    moved.append((t, g))
            groups = sorted(moved)

    n_players = sum(g for _, g in groups)
    if n_players == 0:
        return [{"hour": int(h), "arrivals": 0, "mean_first_wait": np.nan,
                 "p90_first_wait": np.nan, "never_played_rate": np.nan,
                 "sum_wait_min": 0.0, "sum_play_min": 0.0, "sum_games": 0,
                 "mean_stack_depth": 0.0, "court_utilisation": 0.0}
                for h in hours], np.zeros((24, N_WAIT_BINS), dtype=np.int32)

    arrive = np.empty(n_players)
    i = 0
    for t, g in groups:
        arrive[i:i + g] = t
        i += g

    patience = np.exp(rng.normal(np.log(a["patience_first_game_median_min"]),
                                 a["patience_sigma_log"], n_players))
    session_end = arrive + np.maximum(
        30.0, rng.normal(a["session_minutes_mean"], a["session_minutes_sd"], n_players)
    )

    since = arrive.copy()          # when the player's current state began
    state = np.zeros(n_players, dtype=np.int8)   # all WAITING once they arrive
    state[:] = GONE                              # not yet arrived
    wait_total = np.zeros(n_players)
    play_total = np.zeros(n_players)
    games = np.zeros(n_players, dtype=np.int32)
    first_wait = np.full(n_players, np.nan)

    events: list[tuple[float, int, int]] = [(arrive[p], EV_ARRIVE, p) for p in range(n_players)]
    heapq.heapify(events)

    stack: deque[int] = deque()    # paddle rack, FIFO (may hold stale ids)
    n_waiting = 0
    on_court: dict[int, list[int]] = {}
    holders: dict[int, list[int]] = {}   # court -> pair staying on (winners-stay)
    free_courts: list[int] = list(range(courts))

    stack_area = np.zeros(24)
    busy_area = np.zeros(24)
    last_t = open_t

    def accrue(now: float) -> None:
        nonlocal last_t
        t0, depth, busy = last_t, n_waiting, courts - len(free_courts)
        while t0 < now:
            h = int(t0 // 60)
            edge = min(now, (h + 1) * 60.0)
            if 0 <= h < 24:
                stack_area[h] += depth * (edge - t0)
                busy_area[h] += busy * (edge - t0)
            t0 = edge
        last_t = now

    def pop_live() -> int:
        while True:
            pid = stack.popleft()
            if state[pid] == WAITING:
                return pid

    def start_games(now: float) -> None:
        """Fill free courts, cheapest-to-fill first, while the stack can supply."""
        nonlocal n_waiting
        while free_courts and n_waiting > 0:
            # Nobody starts a game that cannot finish before the gates close.
            if close_t - now < a["game_minutes_clip"][0]:
                break
            free_courts.sort(key=lambda c: COURT_CAPACITY - len(holders.get(c, [])))
            court = free_courts[0]
            need = COURT_CAPACITY - len(holders.get(court, []))
            if n_waiting < need:
                break
            free_courts.pop(0)
            drawn = [pop_live() for _ in range(need)]
            n_waiting -= need
            for pid in drawn:
                wait_total[pid] += now - since[pid]
                if np.isnan(first_wait[pid]):
                    first_wait[pid] = now - arrive[pid]
            seated = holders.pop(court, []) + drawn
            dur = float(np.clip(rng.normal(a["game_minutes_mean"], a["game_minutes_sd"]),
                                *a["game_minutes_clip"]))
            dur = min(dur, close_t - now)  # last game of the night gets called at close
            for pid in seated:
                state[pid] = PLAYING
                since[pid] = now
            on_court[court] = seated
            heapq.heappush(events, (now + dur, EV_FINISH, court))

    def join_stack(pid: int, now: float) -> None:
        nonlocal n_waiting
        state[pid] = WAITING
        since[pid] = now
        stack.append(pid)
        n_waiting += 1

    def arm_patience(pids: list[int], now: float) -> None:
        """Schedule give-up events only for players who did not get straight on."""
        for pid in pids:
            if state[pid] == WAITING:
                mult = a["patience_multiplier_after_first_game"] if games[pid] else 1.0
                heapq.heappush(events, (now + patience[pid] * mult, EV_IMPATIENT, pid))

    while events:
        now, kind, ref = heapq.heappop(events)
        if now >= close_t:
            break
        accrue(now)

        if kind == EV_ARRIVE:
            join_stack(ref, now)
            start_games(now)
            arm_patience([ref], now)

        elif kind == EV_FINISH:
            court = ref
            seated = on_court.pop(court)
            game_len = now - since[seated[0]]
            for pid in seated:
                games[pid] += 1
                play_total[pid] += game_len

            staying: list[int] = []
            leaving = list(seated)
            if rule == "winners_stay":
                winners = seated[:2]  # the pair holding the court
                leaving = seated[2:]
                for pid in winners:
                    if now < session_end[pid] and close_t - now > a["min_session_remaining_min"]:
                        staying.append(pid)
                        state[pid], since[pid] = PLAYING, now
                    else:
                        state[pid] = GONE

            rejoined = []
            for pid in leaving:
                if now < session_end[pid] and close_t - now > a["min_session_remaining_min"]:
                    join_stack(pid, now)
                    rejoined.append(pid)
                else:
                    state[pid] = GONE

            if staying:
                holders[court] = staying
            free_courts.append(court)
            start_games(now)
            arm_patience(rejoined, now)

        else:  # EV_IMPATIENT
            pid = ref
            if state[pid] == WAITING:
                mult = a["patience_multiplier_after_first_game"] if games[pid] else 1.0
                if now - since[pid] >= patience[pid] * mult - 1e-9:
                    state[pid] = GONE
                    n_waiting -= 1
                    wait_total[pid] += now - since[pid]

    accrue(close_t)
    still_waiting = state == WAITING
    wait_total[still_waiting] += close_t - since[still_waiting]

    pl = pd.DataFrame({
        "arrive_hour": (arrive // 60).astype(int),
        "first_wait": first_wait,
        "wait": wait_total,
        "play": play_total,
        "games": games,
    })
    pl["never_played"] = pl["games"] == 0
    # Someone who never got on waited until they gave up. That is the wait that
    # matters for them, so first_wait is filled with it -- dropping them would
    # make the line look shorter the worse it actually got.
    pl["first_wait"] = pl["first_wait"].fillna(pl["wait"])

    grouped = pl.groupby("arrive_hour")
    stats = pd.DataFrame({
        "arrivals": grouped.size(),
        "mean_first_wait": grouped["first_wait"].mean(),
        "p90_first_wait": grouped["first_wait"].quantile(0.9),
        "never_played_rate": grouped["never_played"].mean(),
        # Exact sums, so the waiting-vs-playing split can be totalled over any
        # slice later without keeping a million player rows on disk.
        "sum_wait_min": grouped["wait"].sum(),
        "sum_play_min": grouped["play"].sum(),
        "sum_games": grouped["games"].sum(),
    })

    # Fixed-bin histogram of time-to-first-game, so the distribution survives
    # aggregation. Bins are 2 minutes wide from 0 to 90, plus an overflow bin.
    hist = np.zeros((24, N_WAIT_BINS), dtype=np.int32)
    for h, sub in pl.groupby("arrive_hour"):
        idx = np.clip((sub["first_wait"].to_numpy() // WAIT_BIN_MIN).astype(int), 0, N_WAIT_BINS - 1)
        np.add.at(hist[int(h)], idx, 1)

    per_hour = []
    for h in hours:
        h = int(h)
        row = {"hour": h, "arrivals": 0, "mean_first_wait": np.nan, "p90_first_wait": np.nan,
               "never_played_rate": np.nan, "sum_wait_min": 0.0, "sum_play_min": 0.0,
               "sum_games": 0,
               "mean_stack_depth": float(stack_area[h] / 60.0),
               "court_utilisation": float(busy_area[h] / (60.0 * courts))}
        if h in stats.index:
            r = stats.loc[h]
            row.update({"arrivals": int(r["arrivals"]),
                        "mean_first_wait": float(r["mean_first_wait"]),
                        "p90_first_wait": float(r["p90_first_wait"]),
                        "never_played_rate": float(r["never_played_rate"]),
                        "sum_wait_min": float(r["sum_wait_min"]),
                        "sum_play_min": float(r["sum_play_min"]),
                        "sum_games": int(r["sum_games"])})
        per_hour.append(row)
    return per_hour, hist


# ── Driver ──────────────────────────────────────────────────────────────────
def day_seed(park: str, date: pd.Timestamp) -> int:
    """Stable across processes and runs -- python's hash() is salted, so not that."""
    key = f"{SEED_SALT}|{park}|{date.date()}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big")


def run(lam: pd.DataFrame, courts: int, rule: str, shift: float, label: str,
        ) -> tuple[pd.DataFrame, np.ndarray]:
    rows = []
    total_hist = np.zeros((24, N_WAIT_BINS), dtype=np.int64)
    t0 = time.time()
    groups = list(lam.groupby(["park", "date"], sort=True))
    for n, ((park, date), day) in enumerate(groups, 1):
        day = day.sort_values("hour")
        per_hour, hist = simulate_park_day(
            day["hour"].to_numpy(), day["lam"].to_numpy(), courts, rule,
            day_seed(park, date), shift,
        )
        for rec in per_hour:
            rec["park"], rec["date"], rec["scenario"] = park, date, label
            rows.append(rec)
        total_hist += hist
        if n % 2000 == 0:
            print(f"  {label}: {n:,}/{len(groups):,} park-days ({time.time() - t0:.0f}s)")

    out = pd.DataFrame(rows).merge(
        lam[["park", "date", "hour", "lam", "temp_f", "precipitation", "wind", "is_wet",
             "dow", "is_weekend"]],
        on=["park", "date", "hour"], how="left",
    )
    return out, total_hist


if __name__ == "__main__":
    weather = pd.read_csv(DATA / "hourly_weather.csv", parse_dates=["date"])
    lam = lambda_table(weather)
    print(f"demand grid: {len(lam):,} park-hours across {lam['park'].nunique()} parks")

    base, hist = run(lam, ASSUMPTIONS["courts_per_park"], "all_off", 0.0, "baseline")
    base.to_csv(DATA / "park_hours.csv", index=False)
    print(f"baseline: {len(base):,} park-hours, {int(base['arrivals'].sum()):,} player-visits, "
          f"mean wait {base['mean_first_wait'].mean():.1f} min")

    pd.DataFrame(
        hist,
        index=pd.Index(range(24), name="hour"),
        columns=[f"{i * WAIT_BIN_MIN}" for i in range(N_WAIT_BINS)],
    ).to_csv(DATA / "wait_histogram.csv")

    # Counterfactuals on the 2015 hold-out year only: same arrivals, same game
    # lengths, same patience -- different court policy.
    test = lam[lam["date"].dt.year == 2015]
    frames = [run(test, ASSUMPTIONS["courts_per_park"], "all_off", 0.0, "baseline")[0]]
    for label, courts, rule, shift in [
        ("two_more_courts", ASSUMPTIONS["courts_per_park"] + 2, "all_off", 0.0),
        ("winners_stay", ASSUMPTIONS["courts_per_park"], "winners_stay", 0.0),
        ("shift_15pct_off_peak", ASSUMPTIONS["courts_per_park"], "all_off", 0.15),
    ]:
        frame, _ = run(test, courts, rule, shift, label)
        frames.append(frame)
        print(f"scenario {label}: mean wait {frame['mean_first_wait'].mean():.1f} min")
    pd.concat(frames, ignore_index=True).to_csv(DATA / "scenarios.csv", index=False)

    (DATA / "assumptions.json").write_text(
        json.dumps({"assumptions": ASSUMPTIONS, "hourly_shape": HOURLY_SHAPE,
                    "wait_bin_minutes": WAIT_BIN_MIN, "wait_bins": N_WAIT_BINS}, indent=2) + "\n"
    )
    print("wrote park_hours.csv, wait_histogram.csv, scenarios.csv, assumptions.json")
