"""Fetch a bauphysik.net project export.

Run from the repository root after installing the package:

    BAUPHYSIK_API_TOKEN=... BAUPHYSIK_PROJECT_UUID=... python examples/project_export.py

On Windows PowerShell:

    $env:BAUPHYSIK_API_TOKEN = "..."
    $env:BAUPHYSIK_PROJECT_UUID = "..."
    python examples/project_export.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bauphysik_api import BauphysikAPIError, BauphysikClient, TransportError


def main() -> int:
    token = os.environ.get("BAUPHYSIK_API_TOKEN")
    project_uuid = os.environ.get("BAUPHYSIK_PROJECT_UUID")
    base_url = os.environ.get("BAUPHYSIK_BASE_URL", "https://bauphysik.net")

    if not token or not project_uuid:
        print(
            "Set BAUPHYSIK_API_TOKEN and BAUPHYSIK_PROJECT_UUID before running this example.",
            file=sys.stderr,
        )
        return 2

    client = BauphysikClient.with_token(token, base_url=base_url)

    try:
        calculations = client.list_calculations(project_uuid)
        print(f"Project {calculations.project_uuid} has {len(calculations.calculation_names)} calculation(s).")

        for name in calculations.calculation_names:
            print(f"- {name}")

        export = client.export_project(project_uuid)
        print()
        print(f"Exported project: {export.project_name}")
        print(f"Export date: {export.export_date}")
        print(f"Calculation objects: {len(export.calculations)}")
    except BauphysikAPIError as exc:
        print(f"API error {exc.status_code}: {exc}", file=sys.stderr)
        return 1
    except TransportError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
