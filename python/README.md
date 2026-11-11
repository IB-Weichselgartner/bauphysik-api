# bauphysik-api (Python)

Python-Client für die API von [bauphysik.net](https://bauphysik.net). Der Client
liest Projekte und Berechnungen eines Kontos und erstellt Projektexporte als JSON
oder als ZIP mit PDF-Berichten.

Die vollständige Beschreibung der Schnittstelle steht in
[`openapi.yaml`](https://github.com/IB-Weichselgartner/bauphysik-api/blob/main/openapi.yaml).

## Installation

```bash
pip install "bauphysik-api @ git+https://github.com/IB-Weichselgartner/bauphysik-api#subdirectory=python"
```

Für reproduzierbare Installationen einen Commit oder ein Tag anhängen, zum Beispiel
`...bauphysik-api@<commit>#subdirectory=python`.

Benötigt Python 3.10 oder neuer.

## API-Token

Das Token wird im Profil auf bauphysik.net angelegt und setzt ein aktives Pro-
oder Administratorkonto voraus. Es wird nur einmal beim Anlegen angezeigt. Pro
Konto sind höchstens drei aktive Tokens möglich.

Das Token nicht in den Quelltext schreiben, sondern zum Beispiel über eine
Umgebungsvariable übergeben.

## Beispiel

```python
import os

from bauphysik_api import BauphysikClient

with BauphysikClient.with_token(os.environ["BAUPHYSIK_API_TOKEN"]) as client:
    for project in client.list_projects():
        print(project["uuid"], project["name"])

    project_uuid = os.environ["BAUPHYSIK_PROJECT_UUID"]

    names = client.list_calculations(project_uuid).calculation_names
    calculation = client.get_calculation(project_uuid, names[0])
    print(calculation.module_name, calculation.result_data)

    # Gesamtes Projekt als JSON. Größere Projekte laufen automatisch als
    # Hintergrund-Export.
    export = client.export_project(project_uuid)

    # ZIP mit einem PDF-Bericht und einer JSON-Datei je Berechnung.
    with open("export.zip", "wb") as fh:
        fh.write(client.export_project_bundle(project_uuid))
```

Ein lauffähiges Skript liegt unter
[`examples/project_export.py`](examples/project_export.py):

```bash
BAUPHYSIK_API_TOKEN=... BAUPHYSIK_PROJECT_UUID=... python examples/project_export.py
```

In PowerShell:

```powershell
$env:BAUPHYSIK_API_TOKEN = "..."
$env:BAUPHYSIK_PROJECT_UUID = "..."
python examples/project_export.py
```

## Methoden

| Methode | Endpunkt | Rückgabe |
|---|---|---|
| `list_projects()` | `GET /api/projects` | Liste von Dicts mit `uuid`, `name`, `project_id` |
| `list_calculations(project_uuid, module=None)` | `GET /api/{project_uuid}/` | `ProjectCalculationList` mit `calculations` (`calc_uuid`, `calc_name`, `module_name`, `created_at`) |
| `get_calculation_by_uuid(calc_uuid)` | `GET /api/calculations/{calc_uuid}` | `Calculation` |
| `get_calculation(project_uuid, calc_name)` | `GET /api/{project_uuid}/{calc_name}` | `Calculation` |
| `get_calculations_by_uuid(project_uuid, calc_uuids)` | über die vorigen, auch mit älteren Servern | `dict[calc_uuid, Calculation]` |
| `get_din4108_3_layers(calc_uuid)` | `GET /api/calculations/{calc_uuid}/din4108-3` | `dict` mit `simple_data` |
| `search_materials(query, manufacturer=False)` | `GET /api/materials` | Liste von Materialien, mit `manufacturer=True` Werte aus Herstellerdatenblättern |
| `search_calculations(query, module=None, project_uuid=None)` | `GET /api/search` | Liste passender Berechnungen |
| `list_api_modules()` | `GET /api/modules` | Module, die über die API gerechnet, angelegt und geändert werden können |
| `execute_module(module, input_data=… \| simple_data=…)` | `POST /api/modules/{module}/execute` | Ergebnis, nichts wird gespeichert |
| `create_calculation(project_uuid, module, calc_name, input_data=… \| simple_data=…)` | `POST /api/projects/{project_uuid}/calculations` | neue Berechnung; ein vorhandener Name ergibt `409` mit `existing_calc_uuid` |
| `update_calculation(calc_uuid, input_data=… \| simple_data=…)` | `PUT /api/calculations/{calc_uuid}` | geänderte Berechnung, der vorherige Stand bleibt als eigene Berechnung (`backup_calc_uuid`) |

`simple_data` ist der vereinfachte Schichtaufbau für `uwert_glaser_din4108-3`. Die
Eingabeschemata je Modul stehen in
[`schemas/calculation-inputs.json`](https://github.com/IB-Weichselgartner/bauphysik-api/blob/main/schemas/calculation-inputs.json).
Rechnen, Anlegen und Ändern zählen in das Rechenbudget des Kontos.
| `export_project(project_uuid)` | `export-json`, bei Bedarf Hintergrund-Export | `ProjectExport` |
| `export_project_bundle(project_uuid)` | Hintergrund-Export als ZIP | `bytes` |
| `export_project_pdf_zip(project_uuid)` | `GET .../export-pdf`, nur kleine Projekte | `bytes` |
| `start_project_export`, `get_export_job`, `download_export` | einzelne Schritte des Hintergrund-Exports | `dict` bzw. `bytes` |

Die Rückgabeobjekte sind unveränderliche Pydantic-Modelle. Die ursprüngliche
JSON-Antwort steht jeweils in `.raw`.

Berechnungsnamen können von Nutzern geändert werden. Wer eine Berechnung dauerhaft
referenzieren will, speichert `calc_uuid` und löst sie mit
`get_calculations_by_uuid()` wieder auf. Eine fehlende UUID führt zu einem Fehler,
es wird nie eine gleichnamige andere Berechnung zurückgegeben.

## Fehlerbehandlung

```python
from bauphysik_api import BauphysikAPIError, TransportError

try:
    export = client.export_project(project_uuid)
except BauphysikAPIError as exc:
    print(exc.status_code, exc)       # z. B. 401, 404, 429
    print(exc.response_body)
except TransportError as exc:
    print(f"Netzwerk- oder Formatfehler: {exc}")
```

`BauphysikAPIError` steht für Fehlerantworten der API, etwa ein ungültiges Token,
fehlende Berechtigung oder ein erreichtes Limit. `TransportError` steht für
Netzwerkfehler und Antworten, die nicht dem erwarteten Format entsprechen.

## Entwicklung

```bash
pip install -e . pytest
python -m pytest
```

Ein anderer Server, zum Beispiel eine lokale Instanz, wird über `base_url`
angesprochen: `BauphysikClient.with_token(token, base_url="http://localhost:8000")`.

## Lizenz

LGPL-3.0-only, siehe [`LICENSE`](LICENSE) und [`COPYING`](COPYING).
