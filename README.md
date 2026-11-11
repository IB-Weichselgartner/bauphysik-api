# bauphysik.net API

Schnittstellenbeschreibung und Python-Client für die API von
[bauphysik.net](https://bauphysik.net).

Über die API lassen sich die Projekte und Berechnungen eines bauphysik.net-Kontos
lesen und Projektexporte erstellen, zum Beispiel um Ergebnisse von U-Wert-,
Feuchteschutz- oder Wärmebrückenberechnungen in eigene Abläufe zu übernehmen.

| Inhalt | Ort |
|---|---|
| OpenAPI-Spezifikation | [`openapi.yaml`](openapi.yaml) |
| Einstieg mit curl-Beispielen | [`docs/einstieg.md`](docs/einstieg.md) |
| Python-Client | [`python/`](python/), auf PyPI als `bauphysik-api` |

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

- `openapi.yaml` und `docs/`: MIT, siehe [`LICENSE`](LICENSE). Daraus erzeugte
  Clients können frei verwendet werden.
- `python/`: LGPL-3.0-only, siehe [`python/LICENSE`](python/LICENSE).
