#!/usr/bin/env python3
"""
Lokaler Taktgeber für Kickbase -> Google Sheet + Website.

Ersetzt GitHub Actions + cron-job.org: Kickbase wird nur noch von DIESEM Rechner
(deutsche IP) abgefragt. Danach wird data.json auf den Branch "data" gepusht,
die Website liest sie von dort.

    python local_runner.py              # Dauerschleife, alle 5 min
    python local_runner.py --once       # ein Durchlauf (Gate entscheidet)
    python local_runner.py --once --force   # ein Durchlauf, Gate ignorieren (live)
    python local_runner.py --once --full    # ein kompletter Lauf (Gesamt + Spieltage)

Zugangsdaten stehen in .env neben diesem Skript (NICHT einchecken):
    KICKBASE_EMAIL=...
    KICKBASE_PASSWORD=...
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import kickoff_gate

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data_out"          # eigenes Git-Repo, Branch "data"
REMOTE = "https://github.com/CSchwaller/Kickbase_sheets.git"
BRANCH = "data"
INTERVAL = 300                        # Sekunden
KEEP_EXPORTS = 12                     # export/-Ordner, die behalten werden

DEFAULTS = {
    "KICKBASE_LEAGUE": "6924803",
    "KICKBASE_SHEET": "1xyeA2gvEAq1F1FCoiqU8nNLFF1VorY3fc9t6gfVA5q0",
}


def log(msg):
    print(f"[{datetime.now():%d.%m. %H:%M:%S}] {msg}", flush=True)


def load_env():
    env = os.environ.copy()
    f = HERE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k, v in DEFAULTS.items():
        env.setdefault(k, v)
    if "GOOGLE_SA_FILE" not in env and not (HERE / "service_account.json").exists():
        env["GOOGLE_SA_FILE"] = str(Path.home() / "OneDrive" / "Desktop" / "service_account.json")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def git(*args, check=True):
    cmd = ["git", "-c", "user.name=kickbase-runner", "-c", "user.email=runner@localhost", *args]
    return subprocess.run(cmd, cwd=DATA_DIR, capture_output=True, text=True, check=check)


def publish():
    """data.json als einzigen Commit auf den Branch 'data' pushen (History bleibt klein)."""
    DATA_DIR.mkdir(exist_ok=True)
    if not (DATA_DIR / ".git").exists():
        git("init", "-b", BRANCH)
        git("remote", "add", "origin", REMOTE)
    git("add", "data.json")
    has_commit = git("rev-parse", "--verify", "HEAD", check=False).returncode == 0
    msg = f"data {datetime.now():%Y-%m-%d %H:%M}"
    if has_commit:
        git("commit", "--amend", "--allow-empty", "-m", msg)
    else:
        git("commit", "--allow-empty", "-m", msg)
    r = git("push", "--force", "origin", BRANCH, check=False)
    if r.returncode != 0:
        raise RuntimeError("git push fehlgeschlagen: " + (r.stderr or r.stdout).strip())


def cleanup_exports():
    d = HERE / "export"
    if d.exists():
        for old in sorted(p for p in d.iterdir() if p.is_dir())[:-KEEP_EXPORTS]:
            shutil.rmtree(old, ignore_errors=True)


def run_fetch(mode, env):
    cmd = [sys.executable, str(HERE / "kickbase_fetch.py"), "--site", str(DATA_DIR)]
    if mode == "live":
        cmd.append("--lineups-only")
    log(f"Kickbase-Abruf ({mode}) ...")
    r = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
    if r.returncode != 0:
        raise RuntimeError(f"kickbase_fetch.py Exit {r.returncode}\n{tail}\n{(r.stderr or '')[-500:]}")
    log("Abruf OK")
    publish()
    log("data.json gepusht")
    cleanup_exports()


def decide_mode(now, last_full_date):
    """live = Spiel läuft; full = täglicher Nachlauf (ab 06:00 UTC, einmal pro Tag); sonst None."""
    if now.hour >= 6 and last_full_date != now.date():
        try:
            if kickoff_gate.decide(now, daily=True)[0]:
                return "full"
        except Exception as e:
            log(f"Gate (daily) Fehler: {e}")
    try:
        run, why = kickoff_gate.decide(now, daily=False)
    except Exception as e:
        run, why = True, f"OpenLigaDB-Fehler ({e}) – laufe sicherheitshalber"
    log(f"Gate: {why}")
    return "live" if run else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true", help="Gate ignorieren (live)")
    ap.add_argument("--full", action="store_true", help="kompletter Lauf")
    args = ap.parse_args()

    env = load_env()
    if not (env.get("KICKBASE_EMAIL") and env.get("KICKBASE_PASSWORD")):
        sys.exit("KICKBASE_EMAIL / KICKBASE_PASSWORD fehlen (.env anlegen).")

    last_full = None
    while True:
        now = datetime.now(timezone.utc)
        mode = "full" if args.full else ("live" if args.force else decide_mode(now, last_full))
        if mode:
            try:
                run_fetch(mode, env)
                if mode == "full":
                    last_full = now.date()
            except Exception as e:
                log(f"FEHLER: {e}")
        if args.once:
            return
        # auf das nächste 5-Minuten-Raster warten
        t = time.time()
        time.sleep(INTERVAL - (t % INTERVAL) + 2)


if __name__ == "__main__":
    main()
