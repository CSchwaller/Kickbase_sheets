#!/usr/bin/env python3
"""
Kickoff-Gate: entscheidet anhand der Bundesliga-Anstoßzeiten (OpenLigaDB),
ob sich ein Kickbase-Abruf gerade lohnt. Fragt Kickbase selbst NICHT an.

    python kickoff_gate.py            # Modus "live"
    python kickoff_gate.py --daily    # Modus "daily"

live:  läuft, wenn ein Spiel in [Anstoß - 5 min, Anstoß + 150 min] liegt
       (deckt Spiel + Nachspielzeit + Punkte-Nachlauf ab)
daily: läuft, wenn in den letzten 36 h ein Spiel angepfiffen wurde
       (fängt nachträgliche Punktekorrekturen von Kickbase ab)

Ergebnis: run=true|false in $GITHUB_OUTPUT (lokal nur Ausgabe).
Ist OpenLigaDB nicht erreichbar, wird sicherheitshalber run=true gesetzt.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

LEAGUE = "bl1"
BEFORE = timedelta(minutes=5)
AFTER = timedelta(minutes=150)
DAILY_LOOKBACK = timedelta(hours=36)


def season_for(now: datetime) -> int:
    # Saison 2026/27 heißt bei OpenLigaDB "2026"
    return now.year if now.month >= 7 else now.year - 1


def kickoffs(season: int):
    url = f"https://api.openligadb.de/getmatchdata/{LEAGUE}/{season}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    out = []
    for m in r.json():
        ts = m.get("matchDateTimeUTC")
        if ts:
            out.append((datetime.fromisoformat(ts.replace("Z", "+00:00")),
                        m["group"]["groupOrderID"],
                        f'{m["team1"]["shortName"]} - {m["team2"]["shortName"]}'))
    return sorted(out)


def decide(now: datetime, daily: bool):
    games = kickoffs(season_for(now))
    if daily:
        recent = [g for g in games if now - DAILY_LOOKBACK <= g[0] <= now]
        if recent:
            return True, f"daily: {len(recent)} Spiele in den letzten 36 h (ST {recent[-1][1]})"
        return False, "daily: keine Spiele in den letzten 36 h"
    live = [g for g in games if g[0] - BEFORE <= now <= g[0] + AFTER]
    if live:
        return True, "live: " + ", ".join(f"ST {d} {name}" for _, d, name in live)
    nxt = next((g for g in games if g[0] > now), None)
    hint = f" – nächster Anstoß {nxt[0]:%d.%m. %H:%M} UTC (ST {nxt[1]})" if nxt else ""
    return False, "kein Spiel im Zeitfenster" + hint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    if os.environ.get("FORCE_RUN") == "true":
        run, why = True, "manuell erzwungen"
    else:
        try:
            run, why = decide(now, args.daily)
        except Exception as e:  # OpenLigaDB down -> lieber einmal zu viel abrufen
            run, why = True, f"OpenLigaDB-Fehler ({e}) – laufe sicherheitshalber"

    print(f"{now:%Y-%m-%d %H:%M} UTC -> run={str(run).lower()} ({why})")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"run={str(run).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
