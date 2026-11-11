# Einstieg

Diese Seite zeigt den typischen Ablauf mit curl. Die vollständige Beschreibung
aller Endpunkte, Felder und Fehlercodes steht in [`openapi.yaml`](../openapi.yaml).

## 1. Token anlegen

Im Profil auf bauphysik.net unter „API-Tokens“ eine Bezeichnung eingeben, zum
Beispiel „Büro-Server“, und das Token anlegen. Das Token wird nur einmal angezeigt
und sollte sofort sicher abgelegt werden. Pro Konto sind höchstens drei aktive
Tokens möglich. Nicht mehr benötigte Tokens lassen sich dort widerrufen.

Die API setzt ein aktives Pro- oder Administratorkonto voraus. Endet der
Pro-Zugang, werden die Tokens ungültig.

```bash
export BAUPHYSIK_API_TOKEN="..."
```

## 2. Projekte abrufen

```bash
curl -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" \
  https://bauphysik.net/api/projects
```

```json
{
  "projects": [
    {"uuid": "3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11", "name": "Einfamilienhaus Musterstraße 1", "project_id": 4812}
  ]
}
```

Das Token sieht dieselben Projekte wie das Konto: eigene Projekte und, bei
aktivierten Teamfunktionen, die Projekte der Pro-Mitglieder desselben Teams.

## 3. Berechnungen eines Projekts

```bash
curl -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" \
  https://bauphysik.net/api/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/
```

```json
{
  "project_uuid": "3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11",
  "calculation_names": ["Außenwand Bestand", "Dach Sanierung"]
}
```

Eine einzelne Berechnung wird über ihren Namen abgerufen. Der Name wird als ein
Pfadsegment URL-kodiert, auch ein `/` im Namen (`%2F`):

```bash
curl -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" \
  "https://bauphysik.net/api/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/Au%C3%9Fenwand%20Bestand"
```

Die Antwort enthält `input_data` und `result_data`. Deren Aufbau hängt vom
Berechnungsmodul ab (`module_name`). `result_data` ist `null`, wenn zu der
Berechnung kein Ergebnis gespeichert ist.

Berechnungsnamen können in bauphysik.net geändert werden. Für eine dauerhafte
Zuordnung `calc_uuid` speichern.

## 4. Projektexport

Ein Export führt alle Berechnungen des Projekts neu aus.

**Kleine Projekte** liefern das Ergebnis direkt:

```bash
# JSON mit Eingaben und Ergebnissen aller Berechnungen
curl -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" \
  https://bauphysik.net/api/project/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/export-json

# ZIP mit PDF-Bericht und JSON je Berechnung
curl -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" -o export.zip \
  https://bauphysik.net/api/project/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/export-pdf
```

**Größere Projekte** werden mit `409` abgewiesen und laufen als Hintergrund-Export:

```bash
# Export starten (ZIP; für JSON ?format=json anhängen)
curl -X POST -H "Authorization: Bearer $BAUPHYSIK_API_TOKEN" \
  https://bauphysik.net/api/project/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/export
```

```json
{
  "id": "8d2c...",
  "status": "queued",
  "status_url": "/api/project/3f1c9a52-7d1e-4f0b-9c55-2a8e0d6b4c11/export/8d2c...",
  "download_url": null,
  "created": true
}
```

`status_url` im Abstand von einigen Sekunden abfragen, bis `status` den Wert
`completed` hat. Anschließend die Datei einmal über `download_url` laden. Nach dem
Download wird sie gelöscht, spätestens am Ende des Tages, frühestens aber 60
Minuten nach Fertigstellung.

Der Python-Client übernimmt diesen Ablauf in `export_project()` und
`export_project_bundle()`.

## Limits

Die Werte gelten derzeit und können sich ändern.

| Limit | Wert |
|---|---|
| Anfragen je Konto | 120 pro Minute, 3000 pro Stunde |
| Fehlgeschlagene Anmeldungen je IP-Adresse | 20 pro Minute, 200 pro Stunde |
| Synchroner Export | bis 25 Recheneinheiten |
| Exportbudget je Konto | 1500 Recheneinheiten pro Stunde |
| Projektgröße für Exporte | bis 1000 Recheneinheiten |
| Gleichzeitige Hintergrund-Exporte je Konto | 1 |

Jede Berechnung kostet mindestens eine Recheneinheit. Bei Überschreitung antwortet
die API mit `429`, bei Anfragelimits mit dem Header `Retry-After` in Sekunden.

## Fehler

Fehlerantworten sind JSON-Objekte mit dem Feld `error`. Einige Meldungen sind auf
Deutsch.

| Status | Bedeutung |
|---|---|
| `401` | Token fehlt, ist ungültig, widerrufen oder das Konto hat keinen Pro-Zugang |
| `404` | Projekt, Berechnung oder Exportauftrag nicht gefunden oder kein Zugriff |
| `409` | Projekt zu groß für den synchronen Export, oder Download nicht bereit bzw. bereits erfolgt |
| `422` | Projekt zu groß für einen Export |
| `429` | Anfragelimit, Exportbudget oder laufender Export |
