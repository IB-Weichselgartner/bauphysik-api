"""Kommandozeile ``bauphysik`` für die bauphysik.net-API.

Jede Ausgabe ist JSON auf stdout, Fehler stehen als JSON auf stderr. Gerechnet
wird immer auf dem Server von bauphysik.net, das CLI enthält keinen Rechenkern.

Zugang über Umgebungsvariablen:

- ``BAUPHYSIK_API_TOKEN``: API-Token aus dem Profil (Pro-Konto). Alternativ
  ``--token-file``. Den Token nie als Argument übergeben.
- ``BAUPHYSIK_BASE_URL``: Server, Standard ``https://bauphysik.net``.

Rückgabewerte: 0 erfolgreich, 1 Fehlerantwort der API, 2 ungültiger Aufruf oder
ungültige Eingabe (vor dem Senden geprüft), 3 Netzwerk- oder Formatfehler.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from importlib import resources
from pathlib import Path
from typing import Any, Optional

from ._version import __version__
from .client import BauphysikAPIError, BauphysikClient, TransportError

DEFAULT_BASE_URL = "https://bauphysik.net"
SCHEMA_FILE = "calculation-inputs.json"
DIN4108_3 = "uwert_glaser_din4108-3"

EXIT_API, EXIT_USAGE, EXIT_TRANSPORT = 1, 2, 3


class UsageError(Exception):
    """Invalid call or input, detected before anything is sent."""

    def __init__(self, message: str, details: Optional[list] = None) -> None:
        super().__init__(message)
        self.details = details


# ---------------------------------------------------------------------------
# Schemas shipped with the package (same file as schemas/ in the repository)
# ---------------------------------------------------------------------------

def load_schemas() -> dict[str, Any]:
    text = resources.files("bauphysik_api").joinpath(SCHEMA_FILE).read_text(encoding="utf-8")
    return json.loads(text)


def input_schema(module_name: str, simple: bool = False, document: Optional[dict] = None) -> dict[str, Any]:
    """Standalone JSON Schema (draft 2020-12) for one module input."""
    document = document or load_schemas()
    refs = document["x-modules"].get(module_name)
    if refs is None:
        raise UsageError(f"Modul '{module_name}' ist über die API nicht verfügbar.",
                         [{"available_modules": sorted(document["x-modules"])}])
    field = "simple_data" if simple else "input_data"
    if field not in refs:
        raise UsageError(f"--simple gibt es nur für {DIN4108_3}.")
    components = document["components"]["schemas"]

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: (v.replace("#/components/schemas/", "#/$defs/") if k == "$ref" else rewrite(v))
                    for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        return value

    root = rewrite(copy.deepcopy(components[refs[field]]))
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **root,
            "$defs": {name: rewrite(schema) for name, schema in components.items()}}


def validate_input(module_name: str, data: Any, simple: bool = False) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - dependency of the package
        return
    validator = Draft202012Validator(input_schema(module_name, simple))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise UsageError(
            "Eingabe passt nicht zum Schema des Moduls.",
            [{"loc": ".".join(str(p) for p in e.absolute_path) or "(Wurzel)", "msg": e.message} for e in errors[:20]],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_input(path: str) -> Any:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"Eingabedatei nicht lesbar: {exc.strerror or exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"Eingabedatei ist kein gültiges JSON (Zeile {exc.lineno}, Spalte {exc.colno}).") from exc


def _token(args: argparse.Namespace) -> str:
    if args.token_file:
        try:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise UsageError(f"Tokendatei nicht lesbar: {exc.strerror or exc}") from exc
    else:
        token = os.environ.get("BAUPHYSIK_API_TOKEN", "").strip()
    if not token:
        raise UsageError("Kein API-Token: BAUPHYSIK_API_TOKEN setzen oder --token-file angeben.")
    return token


def _input_kwargs(args: argparse.Namespace, module_name: str) -> dict[str, Any]:
    data = _read_input(args.input)
    validate_input(module_name, data, simple=args.simple)
    return {"simple_data": data} if args.simple else {"input_data": data}


def _dump(value: Any) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _fail(message: str, code: int, **extra: Any) -> int:
    sys.stderr.write(json.dumps({"error": message, **extra}, ensure_ascii=False, indent=2) + "\n")
    return code


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_projects_list(client: BauphysikClient, args) -> Any:
    return {"projects": client.list_projects()}


def cmd_calc_list(client: BauphysikClient, args) -> Any:
    listing = client.list_calculations(args.project, module=args.module)
    if not listing.calculations and listing.calculation_names:
        # Older server: names only, no calc_uuid and no module filter.
        return {"project_uuid": listing.project_uuid, "calculation_names": listing.calculation_names,
                "hinweis": "Der Server ist älter als dieses CLI und liefert nur Namen, ohne calc_uuid und Modulfilter."}
    return {"project_uuid": listing.project_uuid, "calculations": listing.calculations}


def cmd_calc_show(client: BauphysikClient, args) -> Any:
    if args.layers:
        return client.get_din4108_3_layers(args.calc)
    return client.get_calculation_by_uuid(args.calc).raw


def cmd_calc_search(client: BauphysikClient, args) -> Any:
    found = client.search_calculations(args.query, module=args.module, project_uuid=args.project, limit=args.limit)
    return {"query": args.query, "count": len(found), "calculations": found}


def cmd_calc_execute(client: BauphysikClient, args) -> Any:
    return client.execute_module(args.module, **_input_kwargs(args, args.module))


def cmd_calc_rerun(client: BauphysikClient, args) -> Any:
    return client.rerun_calculation(args.calc, save=args.save)


def cmd_calc_create(client: BauphysikClient, args) -> Any:
    return client.create_calculation(args.project, args.module, args.name, **_input_kwargs(args, args.module))


def cmd_calc_update(client: BauphysikClient, args) -> Any:
    module_name = client.get_calculation_by_uuid(args.calc).module_name
    return client.update_calculation(args.calc, **_input_kwargs(args, module_name))


def cmd_materials_search(client: BauphysikClient, args) -> Any:
    found = client.search_materials(args.query or "", manufacturer=args.hersteller, limit=args.limit)
    return {"query": args.query or "", "hersteller": args.hersteller, "count": len(found), "materials": found}


def cmd_modules_list(client: BauphysikClient, args) -> Any:
    return {"modules": client.list_api_modules()}


def cmd_schema(_client, args) -> Any:
    return input_schema(args.module, simple=args.simple)


def cmd_export(client: BauphysikClient, args) -> Any:
    target = Path(args.out)
    if target.exists() and not args.overwrite:
        raise UsageError(f"{target} existiert schon, --overwrite zum Ersetzen.")
    if args.format == "json":
        data = (json.dumps(client.export_project(args.project).raw, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    else:
        data = client.export_project_bundle(args.project)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"file": str(target), "bytes": len(data), "format": args.format}


OFFLINE_COMMANDS = {cmd_schema}
# Without a JSON body: the server does not know the endpoint (older version).
UNKNOWN_ENDPOINT_STATUS = (301, 302, 307, 308, 404, 405)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bauphysik",
        description="bauphysik.net-API von der Kommandozeile. Ausgabe als JSON. Token aus BAUPHYSIK_API_TOKEN.",
    )
    parser.add_argument("--version", action="version", version=f"bauphysik {__version__}")
    parser.add_argument("--base-url", default=None,
                        help=f"Server (Standard: BAUPHYSIK_BASE_URL oder {DEFAULT_BASE_URL})")
    parser.add_argument("--token-file", default=None, help="Datei mit dem API-Token statt BAUPHYSIK_API_TOKEN")
    groups = parser.add_subparsers(dest="group", required=True, metavar="<bereich>")

    def command(sub, name, func, help_text):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    def with_input(p):
        p.add_argument("--input", required=True, help="JSON-Datei mit den Eingaben, - für stdin")
        p.add_argument("--simple", action="store_true",
                       help=f"Eingabe ist der vereinfachte Schichtaufbau (nur {DIN4108_3})")

    projects = groups.add_parser("projects", help="Projekte").add_subparsers(required=True, metavar="<befehl>")
    command(projects, "list", cmd_projects_list, "Projekte, auf die der Token Zugriff hat.")

    calc = groups.add_parser("calc", help="Berechnungen").add_subparsers(required=True, metavar="<befehl>")
    p = command(calc, "list", cmd_calc_list, "Berechnungen eines Projekts mit calc_uuid, Modul und Datum.")
    p.add_argument("project", help="project_uuid")
    p.add_argument("--module", help="nur dieses Modul, z. B. datenerfassung")
    p = command(calc, "show", cmd_calc_show, "Eine Berechnung mit Eingaben und Ergebnis.")
    p.add_argument("calc", help="calc_uuid")
    p.add_argument("--layers", action="store_true", help=f"Schichtaufbau vereinfacht (nur {DIN4108_3})")
    p = command(calc, "search", cmd_calc_search, "Volltextsuche in den zugänglichen Berechnungen.")
    p.add_argument("query")
    p.add_argument("--module")
    p.add_argument("--project", help="nur in diesem Projekt (project_uuid)")
    p.add_argument("--limit", type=int, default=10)
    p = command(calc, "execute", cmd_calc_execute, "Auf dem Server rechnen, ohne zu speichern.")
    p.add_argument("module")
    with_input(p)
    p = command(calc, "rerun", cmd_calc_rerun,
                "Gespeicherte Berechnung mit ihren gespeicherten Eingaben neu rechnen, mit --save das Ergebnis speichern.")
    p.add_argument("calc", help="calc_uuid")
    p.add_argument("--save", action="store_true", help="Ergebnis in der Berechnung speichern")
    p = command(calc, "create", cmd_calc_create,
                "Berechnung im Projekt anlegen. Überschreibt nie, ein vorhandener Name ergibt HTTP 409.")
    p.add_argument("project", help="project_uuid")
    p.add_argument("module")
    p.add_argument("name", help="Name der Berechnung")
    with_input(p)
    p = command(calc, "update", cmd_calc_update,
                "Eingaben ersetzen. Der bisherige Stand bleibt als eigene Berechnung erhalten.")
    p.add_argument("calc", help="calc_uuid")
    with_input(p)

    materials = groups.add_parser("materials", help="Materialkatalog").add_subparsers(required=True, metavar="<befehl>")
    p = command(materials, "search", cmd_materials_search,
                "Materialien suchen. Standard ist der generische Katalog, --hersteller sucht Herstellerwerte.")
    p.add_argument("query", nargs="?")
    p.add_argument("--hersteller", "--manufacturer", dest="hersteller", action="store_true",
                   help="Werte aus Herstellerdatenblättern statt des generischen Katalogs")
    p.add_argument("--limit", type=int, default=50)

    modules = groups.add_parser("modules", help="Module").add_subparsers(required=True, metavar="<befehl>")
    command(modules, "list", cmd_modules_list, "Module, die über die API gerechnet, angelegt und geändert werden können.")

    p = command(groups, "schema", cmd_schema, "JSON-Schema der Eingaben eines Moduls (ohne Netz).")
    p.add_argument("module")
    p.add_argument("--simple", action="store_true", help=f"Schema des vereinfachten Schichtaufbaus ({DIN4108_3})")

    p = command(groups, "export", cmd_export, "Projekt exportieren, als ZIP mit PDF-Berichten oder als JSON.")
    p.add_argument("project", help="project_uuid")
    p.add_argument("--out", required=True, help="Zieldatei")
    p.add_argument("--format", choices=("zip", "json"), default="zip")
    p.add_argument("--overwrite", action="store_true")
    return parser


def _utf8_streams() -> None:
    """JSON immer als UTF-8 ausgeben. Unter Windows ist stdout bei Umleitung sonst cp1252, und Zeichen wie λ
    brechen den Aufruf ab, genau dann, wenn ein Skript oder Agent die Ausgabe liest."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: Optional[list[str]] = None, *, client: Optional[BauphysikClient] = None) -> int:
    _utf8_streams()
    args = build_parser().parse_args(argv)
    try:
        if args.func in OFFLINE_COMMANDS:
            _dump(args.func(None, args))
            return 0
        own_client = client is None
        if own_client:
            base_url = args.base_url or os.environ.get("BAUPHYSIK_BASE_URL") or DEFAULT_BASE_URL
            client = BauphysikClient.with_token(_token(args), base_url=base_url)
        try:
            _dump(args.func(client, args))
        finally:
            if own_client:
                client.close()
        return 0
    except UsageError as exc:
        return _fail(str(exc), EXIT_USAGE, **({"details": exc.details} if exc.details else {}))
    except BauphysikAPIError as exc:
        if exc.status_code in UNKNOWN_ENDPOINT_STATUS and exc.response_body is None:
            return _fail("Der Server kennt diesen Befehl noch nicht. Er ist vermutlich älter als dieses CLI.",
                         EXIT_API, status=exc.status_code)
        body = exc.response_body if isinstance(exc.response_body, dict) else {}
        extra = {k: v for k, v in body.items() if k != "error"}
        return _fail(str(exc), EXIT_API, status=exc.status_code, **extra)
    except TransportError as exc:
        return _fail(str(exc), EXIT_TRANSPORT)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
