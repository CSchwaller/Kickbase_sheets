#!/usr/bin/env python3
"""
Kickbase -> CSV + Google Sheets
-------------------------------
Holt für eine Liga:
  1. gesamt.csv        Gesamt-Tabelle (Platz, Punkte, Ø, Spieltagssiege, Teamwert)
  2. spieltage.csv     Punkte je Manager und Spieltag (aktuelle Saison)
  3. aufstellungen.csv Aufstellung jedes Managers + Punkte der Spieler
                       (aktueller Spieltag, sobald nach Anpfiff aufgedeckt;
                        sonst letzter abgeschlossener)

Nutzung (PowerShell):
    $env:KICKBASE_EMAIL = "..."; $env:KICKBASE_PASSWORD = "..."
    python kickbase_fetch.py --league 6924803
    python kickbase_fetch.py --league 6924803 --days 3 4     # bestimmte Spieltage

    python kickbase_fetch.py --league 6924803 --sheet <Sheet-URL oder -ID>

Ausgabe: ./export/<zeitstempel>/  (+ raw/ mit den Roh-JSONs zum Prüfen)
Mit --sheet zusätzlich nach Google Sheets (braucht: pip install gspread
und service_account.json neben dem Skript). Tabs: "Gesamt", "Spieltage",
"ST <n>" je Spieltag (wird bei jedem Lauf für diesen Spieltag überschrieben).
"""
import argparse
import csv
import getpass
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://api.kickbase.com"
DELAY = 0.4
COMPETITION = 1  # Bundesliga
POS = {1: "TW", 2: "ABW", 3: "MF", 4: "ST"}

s = requests.Session()
s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
RAW: Path = None  # wird in main gesetzt


def get(path, params=None, raw_name=None):
    time.sleep(DELAY)
    r = s.get(BASE + path, params=params, timeout=20)
    if r.status_code == 429:
        sys.exit("Rate-Limit (429) – bitte später erneut versuchen.")
    try:
        body = r.json()
    except ValueError:
        body = {}
    if raw_name:
        (RAW / f"{raw_name}.json").write_text(
            json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    if r.status_code != 200:
        print(f"  ! {path} {params or ''} -> HTTP {r.status_code}")
    return body


def write_csv(path: Path, header, rows):
    # utf-8-sig + ';' damit Excel (DE) die Datei direkt korrekt öffnet
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        w.writerows(rows)
    print(f"  -> {path.name}: {len(rows)} Zeilen")


def pos_map(data):
    """Spieler-ID -> Positionsnummer aus einer Kader-Antwort (best effort)."""
    out = {}

    def walk(d):
        if isinstance(d, dict):
            pid = d.get("pi", d.get("i"))
            if pid is not None and isinstance(d.get("pos"), int):
                out[str(pid)] = d["pos"]
            for v in d.values():
                walk(v)
        elif isinstance(d, list):
            for x in d:
                walk(x)

    walk(data)
    return out


def team_names():
    """tid -> Vereinsname aus der Bundesliga-Tabelle (best effort)."""
    data = get(f"/v4/competitions/{COMPETITION}/table", raw_name="bl_table")
    names = {}

    def walk(d):
        if isinstance(d, dict):
            tid = d.get("tid")
            nm = d.get("tn") or d.get("tnm") or d.get("n")
            if tid is not None and isinstance(nm, str):
                names[str(tid)] = nm
            for v in d.values():
                walk(v)
        elif isinstance(d, list):
            for x in d:
                walk(x)

    walk(data)
    return names


def now_berlin():
    """Aktuelle Zeit in Deutschland (GitHub-Runner laufen in UTC)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # Windows ohne tzdata -> lokale Zeit
        return datetime.now()


def write_sheets(sheet, stand, gesamt_tab, spieltage_tab, day_tabs):
    """Schreibt die Tabellen ins Google Sheet. *_tab = (header, rows)."""
    import gspread

    creds = Path(os.environ.get("GOOGLE_SA_FILE") or Path(__file__).with_name("service_account.json"))
    gc = gspread.service_account(filename=str(creds))
    sh = gc.open_by_url(sheet) if sheet.startswith("http") else gc.open_by_key(sheet)

    def put(title, header, rows, index):
        header = header + ["", f"Stand: {stand}"]
        values = [header] + [list(r) for r in rows]
        ncols = len(header)
        try:
            ws = sh.worksheet(title)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=title, rows=len(values) + 20, cols=ncols + 2, index=index)
        if ws.row_count < len(values) or ws.col_count < ncols:
            ws.resize(rows=max(ws.row_count, len(values) + 20), cols=max(ws.col_count, ncols))
        ws.update(range_name="A1", values=values, value_input_option="USER_ENTERED")
        ws.format("1:1", {"textFormat": {"bold": True}})
        ws.freeze(rows=1)
        print(f"  -> Sheet-Tab '{title}': {len(rows)} Zeilen")

    put("Gesamt", *gesamt_tab, index=0)
    put("Spieltage", *spieltage_tab, index=1)
    for day, (header, rows) in sorted(day_tabs.items()):
        put(f"ST {day}", header, rows, index=2)  # neuester Spieltag vorne

    # leeres Standard-Blatt ("Tabelle1"/"Sheet1") entfernen, falls vorhanden
    for ws in sh.worksheets():
        if ws.title in ("Tabelle1", "Sheet1") and len(sh.worksheets()) > 1:
            sh.del_worksheet(ws)
    print(f"  -> {sh.url}")


def main():
    global RAW
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=os.environ.get("KICKBASE_LEAGUE"),
                    help="leagueId (oder Env KICKBASE_LEAGUE)")
    ap.add_argument("--days", type=int, nargs="*",
                    help="Spieltage für Aufstellungen (Standard: aktueller + letzter abgeschlossener)")
    ap.add_argument("--sheet", help="Google-Sheet-URL oder -ID (optional, sonst Env KICKBASE_SHEET)")
    args = ap.parse_args()
    if not args.league:
        ap.error("--league oder KICKBASE_LEAGUE angeben")
    L = f"/v4/leagues/{args.league}"

    email = os.environ.get("KICKBASE_EMAIL")
    pw = os.environ.get("KICKBASE_PASSWORD")
    if not (email and pw):
        if not sys.stdin.isatty():  # z. B. GitHub Actions ohne Secrets
            sys.exit("KICKBASE_EMAIL / KICKBASE_PASSWORD fehlen.")
        email = email or input("Kickbase E-Mail: ")
        pw = pw or getpass.getpass("Passwort: ")
    args.sheet = args.sheet or os.environ.get("KICKBASE_SHEET")

    out = Path("export") / datetime.now().strftime("%Y%m%d_%H%M%S")
    RAW = out / "raw"
    RAW.mkdir(parents=True, exist_ok=True)

    r = s.post(BASE + "/v4/user/login",
               json={"em": email, "pass": pw, "loy": False, "rep": {}}, timeout=20)
    if r.status_code != 200:
        sys.exit(f"Login fehlgeschlagen: HTTP {r.status_code}")
    s.headers["Authorization"] = f"Bearer {r.json()['tkn']}"
    print("Login OK")

    # --- Spieltage
    md = get(f"/v4/competitions/{COMPETITION}/matchdays", raw_name="matchdays")
    current_day = md.get("day")
    last_done = get(f"{L}/ranking", raw_name="ranking").get("day")
    print(f"Aktueller Spieltag: {current_day}, letzter abgeschlossener: {last_done}")

    # --- Manager
    mgrs = get(f"{L}/settings/managers", raw_name="managers").get("us", [])
    print(f"{len(mgrs)} Manager")
    teams = team_names()

    if args.days:
        days = args.days
    else:
        # Aufstellungen werden erst mit dem ersten Anpfiff aufgedeckt:
        # Stichprobe beim ersten Manager -> leer = noch verdeckt
        probe = get(f"{L}/users/{mgrs[0]['i']}/teamcenter", {"dayNumber": current_day})
        if probe.get("lp"):
            days = [current_day]
            print(f"Spieltag {current_day} ist aufgedeckt -> Live-Aufstellungen")
        else:
            days = [last_done]
            print(f"Spieltag {current_day} noch verdeckt -> Aufstellungen von Spieltag {last_done}")

    gesamt, spieltage, aufst = [], [], []
    season_days = set()
    per_mgr_days = {}
    cache_file = Path("positions_cache.json")
    try:
        positions = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        positions = {}
    lineups = []  # (day, name, uid, u0, players)

    for i, m in enumerate(mgrs, 1):
        uid, name = m["i"], m["n"]
        print(f"[{i}/{len(mgrs)}] {name}")

        # Gesamt
        d = get(f"{L}/managers/{uid}/dashboard", raw_name=f"dashboard_{uid}")
        gesamt.append([d.get("pl"), name, d.get("tp"), d.get("ap"),
                       d.get("mdw"), d.get("hpt"), int(d.get("tv") or 0), uid])

        # Punkte je Spieltag (aktuelle Saison = letzter Eintrag)
        p = get(f"{L}/managers/{uid}/performance", raw_name=f"performance_{uid}")
        seasons = p.get("it") or []
        cur = seasons[-1] if seasons else {}
        pts = {}
        for e in cur.get("it", []):
            if "mdp" in e:
                pts[e["day"]] = e["mdp"]
                season_days.add(e["day"])
        per_mgr_days[uid] = (name, pts)

        # Aufstellungen: Teamcenter -> lp[] (Reihenfolge = Formation, TW zuerst),
        # us[0].mdp = Punkte des Managers am Spieltag, us[0].pl = Spieltagsplatz
        for day in days:
            tc = get(f"{L}/users/{uid}/teamcenter", {"dayNumber": day},
                     raw_name=f"teamcenter_{uid}_tag{day}")
            lineups.append((day, name, uid, (tc.get("us") or [{}])[0], tc.get("lp") or []))

    # --- Positionen: Cache -> BL-Spielerliste -> Vereinsprofile -> Einzelabfrage (max. 40)
    needed = {str(pl.get("i")) for *_, players in lineups for pl in players}
    if needed - set(positions):
        print("Positionen laden (Bundesliga-Spielerliste) ...")
        positions.update(pos_map(get(f"/v4/competitions/{COMPETITION}/players", raw_name="bl_players")))
    if len(needed - set(positions)) > 10:
        print("Positionen laden (Vereinsprofile) ...")
        for tid in teams:
            positions.update(pos_map(get(f"/v4/competitions/{COMPETITION}/teams/{tid}/teamprofile",
                                         raw_name=f"teamprofile_{tid}")))
    missing = needed - set(positions)
    if missing:
        print(f"Positionen für {len(missing)} Spieler nachschlagen ...")
    for pid in sorted(missing)[:40]:
        info = get(f"/v4/competitions/{COMPETITION}/players/{pid}", raw_name=f"player_{pid}")
        if isinstance(info.get("pos"), int):
            positions[pid] = info["pos"]
    cache_file.write_text(json.dumps(positions), encoding="utf-8")

    for day, name, uid, u0, players in lineups:
        if not players:
            aufst.append([day, name, u0.get("pl", ""), u0.get("mdp", ""), "", "",
                          "(noch nicht sichtbar)", "", "", uid])
        for slot, pl in enumerate(players, 1):
            pid = str(pl.get("i", ""))
            tid = str(pl.get("tid", ""))
            aufst.append([day, name, u0.get("pl", ""), u0.get("mdp", ""),
                          slot, POS.get(positions.get(pid), ""), pl.get("n"),
                          teams.get(tid, tid), pl.get("p", 0), uid])

    # --- CSVs
    gesamt.sort(key=lambda x: (x[0] is None or x[0] == 0, x[0] or 0, -(x[2] or 0)))
    write_csv(out / "gesamt.csv",
              ["Platz", "Manager", "Punkte", "Ø Punkte", "Spieltagssiege",
               "Bester Spieltag", "Teamwert", "UserID"], gesamt)

    cols = sorted(season_days)
    for uid, (name, pts) in per_mgr_days.items():
        spieltage.append([name] + [pts.get(c, "") for c in cols]
                         + [sum(v for v in pts.values() if isinstance(v, (int, float)))])
    spieltage.sort(key=lambda r: -r[-1])
    write_csv(out / "spieltage.csv", ["Manager"] + [f"ST {c}" for c in cols] + ["Summe"], spieltage)

    write_csv(out / "aufstellungen.csv",
              ["Spieltag", "Manager", "Spieltagsplatz", "Manager-Punkte", "Slot", "Pos",
               "Spieler", "Verein", "Spieler-Punkte", "UserID"], aufst)

    if args.sheet:
        print("Google Sheets ...")
        g_head = ["Platz", "Manager", "Punkte", "Ø Punkte", "Spieltagssiege",
                  "Bester Spieltag", "Teamwert"]
        s_head = ["Manager"] + [f"ST {c}" for c in cols] + ["Summe"]
        d_head = ["Platz", "Manager", "Manager-Punkte", "Pos", "Spieler", "Verein", "Punkte"]
        day_tabs = {}
        for r in aufst:
            day, name, pl, mdp, slot, pos, spieler, verein, pkt, _ = r
            day_tabs.setdefault(day, []).append((pl if pl != "" else 99, name, slot or 0,
                                                 [pl, name, mdp, pos, spieler, verein, pkt]))
        day_tabs = {d: (d_head, [x[3] for x in sorted(v, key=lambda t: t[:3])])
                    for d, v in day_tabs.items()}
        write_sheets(args.sheet, now_berlin().strftime("%d.%m.%Y %H:%M"),
                     (g_head, [r[:7] for r in gesamt]), (s_head, spieltage), day_tabs)

    print(f"\nFertig: {out.resolve()}")


if __name__ == "__main__":
    main()
