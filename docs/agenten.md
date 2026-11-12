# bauphysik.net mit KI-Agenten

Die Kommandozeile `bauphysik` lässt sich direkt von Coding-Agenten wie Claude Code,
Codex oder OpenCode aufrufen. Diese Seite enthält einen Baustein für die
Projektanweisung des Agenten und ein durchgerechnetes Beispiel.

## Einrichten

```bash
uv tool install "git+https://github.com/IB-Weichselgartner/bauphysik-api#subdirectory=python"
export BAUPHYSIK_API_TOKEN=...   # Token aus dem Profil auf bauphysik.net (Pro-Konto)
```

Das Token gehört in die Umgebung des Agenten, nicht in die Projektanweisung und
nicht in Dateien, die der Agent liest oder eincheckt.

## Baustein für AGENTS.md oder CLAUDE.md

```markdown
## bauphysik.net

Für bauphysik.net das CLI `bauphysik` verwenden, keine eigenen HTTP-Aufrufe.

- Ausgabe ist JSON auf stdout, Fehler als JSON auf stderr. Exitcodes: 0 ok,
  1 Fehler vom Server, 2 ungültige Eingabe oder fehlendes Token,
  3 keine Verbindung.
- Vor jeder Eingabe die Felder mit `bauphysik schema <modul>` nachsehen
  (`--simple` für Schichtaufbauten nach DIN 4108-3). Keine Felder erfinden.
- Eingaben als JSON-Datei ablegen und mit `--input <datei>` übergeben.
- Varianten mit `bauphysik calc execute` rechnen, das speichert nichts.
- `bauphysik calc create` überschreibt nie. Bei Exitcode 1 mit `"status": 409`
  existiert der Name schon: einen neuen Namen wählen oder bewusst
  `bauphysik calc update <calc_uuid>` verwenden (legt vorher eine Sicherung an).
- Materialien mit `bauphysik materials search "<Begriff>"` suchen und den Namen
  genau so übernehmen.
```

## Befehle

| Befehl | Zweck |
|---|---|
| `bauphysik projects list` | Projekte des Kontos, auch aus Teams |
| `bauphysik calc list <project_uuid> [--module M]` | Berechnungen eines Projekts |
| `bauphysik calc show <calc_uuid> [--layers]` | Eingabe und Ergebnis einer Berechnung |
| `bauphysik calc search "<Text>" [--project P]` | Volltextsuche im Inhalt der Berechnungen |
| `bauphysik modules list` | Module, die über die API rechnen und anlegen |
| `bauphysik schema <modul> [--simple]` | JSON-Schema der Eingabe |
| `bauphysik materials search "<Begriff>" [--hersteller]` | Materialkatalog, mit `--hersteller` Herstellerwerte |
| `bauphysik calc execute <modul> --input <datei> [--simple]` | Rechnen ohne Speichern |
| `bauphysik calc create <project_uuid> <modul> <name> --input <datei> [--simple]` | Berechnung anlegen |
| `bauphysik calc update <calc_uuid> --input <datei> [--simple]` | Ändern, mit Sicherung der alten Fassung |
| `bauphysik calc rerun <calc_uuid> [--save]` | Gespeicherte Berechnung neu rechnen |
| `bauphysik export <project_uuid>` | Projektexport |

`bauphysik <befehl> --help` nennt alle Optionen.

## Beispiel: U-Wert einer Außenwand

Schema ansehen und Materialien suchen:

```bash
bauphysik schema uwert_glaser_din4108-3 --simple
bauphysik materials search "EPS"
```

Eingabe [`beispiele/aussenwand.json`](beispiele/aussenwand.json):

```json
{
  "ziel_u_kategorie": "aussenwand",
  "layers": [
    {"name": "Innenputz", "thickness_m": 0.015, "material": "Kalk-Gipsputz"},
    {"name": "Mauerwerk", "thickness_m": 0.30, "material": "Vollziegel 1.4"},
    {"name": "Dämmung", "thickness_m": 0.14, "material": "EPS 035"},
    {"name": "Außenputz", "thickness_m": 0.01, "material": "Kalkzementputz"}
  ]
}
```

Rechnen, ohne zu speichern, und danach anlegen:

```bash
bauphysik calc execute uwert_glaser_din4108-3 --input aussenwand.json --simple
bauphysik calc create <project_uuid> uwert_glaser_din4108-3 "AW Bestand gedämmt" \
  --input aussenwand.json --simple
```

`result_data` enthält unter anderem `R_total` in m²K/W. Der U-Wert ist dessen
Kehrwert, hier rund 0,22 W/(m²K).

## Grenzen

- Gerechnet wird auf dem Server, für jede Berechnung gilt das Rechenbudget des
  Kontos. Bei Überschreitung antwortet der Server mit 429.
- Über die API rechnen und anlegen lassen sich nur die Module aus
  `bauphysik modules list`. Andere Module sind nur lesbar.
- Der Agent arbeitet mit den Rechten des Tokens. Für Versuche ein eigenes
  Testprojekt verwenden.
