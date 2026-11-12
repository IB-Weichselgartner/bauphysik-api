# bauphysik.net API

Schnittstellenbeschreibung und Python-Client für die API von
[bauphysik.net](https://bauphysik.net).

Über die API lassen sich die Projekte und Berechnungen eines bauphysik.net-Kontos
lesen, Projektexporte erstellen und für ausgewählte Module Berechnungen rechnen,
anlegen und ändern, zum Beispiel um Ergebnisse von U-Wert-, Feuchteschutz- oder
Wärmebrückenberechnungen in eigene Abläufe zu übernehmen. Gerechnet wird immer auf
dem Server von bauphysik.net.

| Inhalt | Ort |
|---|---|
| OpenAPI-Spezifikation | [`openapi.yaml`](openapi.yaml) |
| Eingabeschemata je Modul | [`schemas/calculation-inputs.json`](schemas/calculation-inputs.json), erzeugt aus den Modellen des Servers |
| Einstieg mit curl-Beispielen | [`docs/einstieg.md`](docs/einstieg.md) |
| Python-Client und Kommandozeile `bauphysik` | [`python/`](python/) |
| Nutzung mit KI-Agenten, Baustein für `AGENTS.md` | [`docs/agenten.md`](docs/agenten.md) |

## Kommandozeile für Skripte und KI-Agenten

Die Kommandozeile `bauphysik` ist für den Aufruf aus Skripten und von KI-Agenten wie
Claude Code, Codex oder OpenCode gebaut:

- **Ausgabe immer JSON** auf stdout, Fehler als JSON auf stderr, immer UTF-8.
- **Feste Exitcodes:** `0` ok, `1` Fehler vom Server (z. B. 409, 429), `2` ungültige
  Eingabe oder fehlendes Token, `3` keine Verbindung.
- **Selbstbeschreibend:** `bauphysik modules list` nennt die Module,
  `bauphysik schema <modul>` das JSON-Schema der Eingabe. Ein Agent braucht keine
  weitere Dokumentation, um eine Berechnung aufzubauen.
- **Prüfung vor dem Senden:** Eingaben werden lokal gegen das Schema geprüft, die
  Fehlermeldung nennt das betroffene Feld.
- **Nichts geht verloren:** `calc create` überschreibt nie (409 mit der vorhandenen
  `calc_uuid`), `calc update` legt vorher eine Sicherung an.
- **Rechnen ohne Speichern:** `calc execute` rechnet eine Variante, ohne sie im Konto
  anzulegen.
- **Keine Rückfragen:** Token und Server kommen aus `BAUPHYSIK_API_TOKEN` und
  `BAUPHYSIK_BASE_URL`, kein Aufruf wartet auf eine Eingabe.

```bash
uv tool install "git+https://github.com/IB-Weichselgartner/bauphysik-api#subdirectory=python"

bauphysik schema uwert_glaser_din4108-3 --simple
bauphysik calc execute uwert_glaser_din4108-3 --input docs/beispiele/aussenwand.json --simple
```

Für Agenten genügt meist ein Abschnitt in der Projektanweisung (`AGENTS.md`,
`CLAUDE.md`). Eine Vorlage mit Befehlsübersicht und Beispiel steht in
[`docs/agenten.md`](docs/agenten.md).

## Zugang

Die API steht Pro-Konten zur Verfügung. Das API-Token wird im Profil auf
bauphysik.net angelegt und als `Authorization: Bearer <token>` mitgeschickt.

## Clients für andere Sprachen

Aus `openapi.yaml` lassen sich Clients für andere Sprachen erzeugen, zum Beispiel
mit dem [OpenAPI Generator](https://openapi-generator.tech/):

```bash
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml -g typescript-fetch -o clients/typescript
```

Erzeugte Clients werden in diesem Repository nicht gepflegt. Hinweise auf Fehler in
der Spezifikation gerne als Issue.

## Lizenz

- `openapi.yaml`, `schemas/` und `docs/`: MIT, siehe [`LICENSE`](LICENSE). Daraus erzeugte
  Clients können frei verwendet werden.
- `python/`: LGPL-3.0-only, siehe [`python/LICENSE`](python/LICENSE).
