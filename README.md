# Kickbase → Google Sheets + Website

Schreibt Gesamt-Tabelle, Spieltagspunkte und Aufstellungen (ein Tab je Spieltag) der Kickbase-Liga in ein Google Sheet.
Läuft per GitHub Actions; Kickbase wird nur abgefragt, wenn laut Anstoßzeiten (OpenLigaDB) gerade gespielt wird.

## Dateien
- `kickbase_fetch.py` – Kickbase abrufen, CSV + Google Sheet schreiben
- `kickoff_gate.py` – prüft Anstoßzeiten (OpenLigaDB, keine Kickbase-Requests)
- `.github/workflows/kickbase.yml` – Zeitplan

## Zeitplan (UTC)
- Fr 18–21, Sa 13–20, So 13–21 Uhr alle 5 min; Di/Mi 16–21 Uhr alle 15 min
- Gate prüft jeweils, ob ein Spiel in [Anstoß −5 min, Anstoß +150 min] liegt → nur dann Kickbase-Abruf
- täglich 06:00 UTC: Nachlauf, falls in den letzten 36 h gespielt wurde (Punktekorrekturen)
- manuell: Actions → „Kickbase -> Google Sheets“ → *Run workflow* (optional Spieltage, z. B. `1 2 3 4`)

## Website
`site/index.html` zeigt die Aufstellungen aller Manager mit Live-Punkten je Spieltag (ältere Spieltage aus den ST-Tabs im Sheet).
Es liest `data.json`, das bei jedem Lauf erzeugt und per GitHub Pages veröffentlicht wird.
Live-Läufe rufen nur Aufstellungen ab (`--lineups-only`); Gesamt/Spieltage im Sheet aktualisiert der tägliche bzw. manuelle Lauf.
Einmalig: Settings → Pages → Source: **GitHub Actions** (bei kostenlosem GitHub-Konto nur für öffentliche Repos).
Eigene Zeile markieren: Link mit `?ich=<Name>` öffnen, z. B. `.../?ich=Christoph` (wird im Browser gemerkt).

## Secrets (Settings → Secrets and variables → Actions)
| Name | Inhalt |
|---|---|
| `KICKBASE_EMAIL` | Kickbase-Login |
| `KICKBASE_PASSWORD` | Kickbase-Passwort |
| `KICKBASE_LEAGUE` | `6924803` |
| `KICKBASE_SHEET` | Sheet-ID |
| `GOOGLE_SERVICE_ACCOUNT` | kompletter Inhalt von `service_account.json` |

## Lokal sofort aktualisieren
`update_lokal.bat` doppelklicken (fragt Kickbase-Login ab, falls nicht als Umgebungsvariable gesetzt).

## Lokal (manuell)
```powershell
$env:KICKBASE_EMAIL="..."; $env:KICKBASE_PASSWORD="..."
python kickbase_fetch.py --league 6924803 --sheet <Sheet-ID>
python kickoff_gate.py      # zeigt nur an, ob gerade abgerufen würde
```
