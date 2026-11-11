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
