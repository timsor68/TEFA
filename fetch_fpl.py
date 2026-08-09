#!/usr/bin/env python3
"""Fetch the Fantasy Premier League bootstrap-static payload server-side (no browser CORS
restrictions apply here) and save a small wrapped JSON file that TEFA's frontend reads
directly from this repo (same-origin, no proxy needed) instead of proxying FPL's ~1.5-2MB
API response through unreliable free browser CORS relays.

Only the two arrays TEFA actually uses (teams, elements) are kept, dropping the much larger
rest of bootstrap-static (fixtures calendar, game settings, phases, etc.) to keep the
committed file small.
"""
import json
import urllib.request
from datetime import datetime, timezone

FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
OUT_FILE = "fpl-data.json"


def main():
    req = urllib.request.Request(FPL_URL, headers={"User-Agent": "TEFA-sync/1.0 (+https://github.com/timsor68/TEFA)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

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


if __name__ == "__main__":
    main()
