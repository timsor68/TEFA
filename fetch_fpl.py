#!/usr/bin/env python3
"""Fetch FPL bootstrap-static (teams + elements) and, for players who've featured this
season, each player's past-season history (element-summary's history_past) — all server-side,
so TEFA's frontend never needs to call FPL's API from the browser (which FPL blocks via CORS)
or rely on flaky public CORS relays for anything, including the season-history popup.

Writes two small files:
  fpl-data.json    — teams + elements (unchanged from before)
  fpl-history.json — { fetched_at, players: { <player_id>: [ {season_name, total_points,
                        minutes, goals_scored, assists, start_cost, end_cost}, ... ] } } for
                        players with minutes > 0 or total_points > 0 this season. Players with
                        neither are skipped — they're overwhelmingly players who haven't
                        featured, so their history is rarely looked up, and skipping keeps this
                        file and the sync time down.
"""
import json
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
SUMMARY_URL = "https://fantasy.premierleague.com/api/element-summary/{}/"
OUT_FILE = "fpl-data.json"
HISTORY_FILE = "fpl-history.json"
HEADERS = {"User-Agent": "TEFA-sync/1.0 (+https://github.com/timsor68/TEFA)"}
MAX_WORKERS = 8
RETRIES = 2


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_player_history(player_id):
    """Returns (player_id, slimmed history_past list) or (player_id, None) on repeated failure."""
    for attempt in range(RETRIES + 1):
        try:
            d = fetch_json(SUMMARY_URL.format(player_id))
            past = d.get("history_past", [])
            # Keep only the fields the frontend actually renders, to keep the file small.
            slim = [
                {
                    "season_name": h.get("season_name"),
                    "total_points": h.get("total_points"),
                    "minutes": h.get("minutes"),
                    "goals_scored": h.get("goals_scored"),
                    "assists": h.get("assists"),
                    "start_cost": h.get("start_cost"),
                    "end_cost": h.get("end_cost"),
                }
                for h in past
            ]
            return player_id, slim
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if attempt == RETRIES:
                print(f"  warning: giving up on player {player_id} after {RETRIES + 1} tries: {e}")
                return player_id, None
            time.sleep(0.5 * (attempt + 1))


def main():
    data = fetch_json(FPL_URL, timeout=30)

    teams = data.get("teams", [])
    elements = data.get("elements", [])
    if not teams or not elements:
        raise SystemExit(f"FPL response looks empty/malformed: {len(teams)} teams, {len(elements)} elements")

    wrapped = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "teams": teams,
        "elements": elements,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {OUT_FILE}: {len(elements)} players, {len(teams)} teams")

    # Only fetch history for players who've actually featured (or scored points) this season —
    # cuts an all-~700-player run down considerably and skips lookups almost nobody clicks on.
    active_ids = [
        e["id"] for e in elements
        if (e.get("minutes") or 0) > 0 or (e.get("total_points") or 0) > 0
    ]
    print(f"Fetching season history for {len(active_ids)} active players (of {len(elements)} total)…")

    history = {}
    failures = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_player_history, pid): pid for pid in active_ids}
        for i, fut in enumerate(as_completed(futures), 1):
            pid, past = fut.result()
            if past is None:
                failures += 1
            elif past:  # skip players with no past-season data at all — nothing to store
                history[str(pid)] = past
            if i % 100 == 0:
                print(f"  …{i}/{len(active_ids)}")

    history_wrapped = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "players": history,
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_wrapped, f, ensure_ascii=False, separators=(",", ":"))
    print(
        f"Wrote {HISTORY_FILE}: {len(history)} players with history"
        + (f" ({failures} failed fetches, skipped)" if failures else "")
    )


if __name__ == "__main__":
    main()
