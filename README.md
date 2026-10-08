# Kickbase → Google Sheets

Schreibt Gesamt-Tabelle, Spieltagspunkte und Aufstellungen (ein Tab je Spieltag) der Kickbase-Liga in ein Google Sheet.
Läuft per GitHub Actions; Kickbase wird nur abgefragt, wenn laut Anstoßzeiten (OpenLigaDB) gerade gespielt wird.

## Dateien
- `kickbase_fetch.py` – Kickbase abrufen, CSV + Google Sheet schreiben
- `kickoff_gate.py` – prüft Anstoßzeiten (OpenLigaDB, keine Kickbase-Requests)
- `.github/workflows/kickbase.yml` – Zeitplan

## Zeitplan
- Di, Mi, Fr, Sa, So, 11–22 Uhr UTC alle 15 min: Gate prüft, ob ein Spiel in [Anstoß −5 min, Anstoß +150 min] liegt → nur dann Kickbase-Abruf
- täglich 06:00 UTC: Nachlauf, falls in den letzten 36 h gespielt wurde (Punktekorrekturen)
- manuell: Actions → „Kickbase -> Google Sheets“ → *Run workflow* (optional Spieltage, z. B. `1 2 3 4`)

## Secrets (Settings → Secrets and variables → Actions)
| Name | Inhalt |
|---|---|
| `KICKBASE_EMAIL` | Kickbase-Login |
| `KICKBASE_PASSWORD` | Kickbase-Passwort |
| `KICKBASE_LEAGUE` | `6924803` |
| `KICKBASE_SHEET` | Sheet-ID |
| `GOOGLE_SERVICE_ACCOUNT` | kompletter Inhalt von `service_account.json` |

## Lokal
```powershell
$env:KICKBASE_EMAIL="..."; $env:KICKBASE_PASSWORD="..."
python kickbase_fetch.py --league 6924803 --sheet <Sheet-ID>
python kickoff_gate.py      # zeigt nur an, ob gerade abgerufen würde
```
