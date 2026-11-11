"""Every request the client sends must exist in openapi.yaml."""

import re
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bauphysik_api import BauphysikClient

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _spec_operations():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    operations = []
    for template, item in spec["paths"].items():
        pattern = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template)) + "$"
        for method in item:
            operations.append((method.upper(), re.compile(pattern), template))
    return operations


def _handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.raw_path.decode().split("?")[0]))
        path = request.url.path
        if path == "/api/projects":
            return httpx.Response(200, json={"projects": []})
        if path == "/api/materials":
            return httpx.Response(200, json={"query": "", "manufacturer": False, "count": 0, "materials": []})
        if path == "/api/search":
            return httpx.Response(200, json={"query": "x", "count": 0, "calculations": []})
        if path.endswith("/din4108-3"):
            return httpx.Response(200, json={"project_uuid": "p-1", "calc_uuid": "c-1", "calc_name": "a",
                                             "module_name": "uwert_glaser_din4108-3", "simple_data": {}})
        if path == "/api/modules":
            return httpx.Response(200, json={"modules": [{"module_name": "fl_din277", "name": "DIN 277"}]})
        if request.method == "POST" and path.startswith("/api/calculations/") and path.endswith("/execute"):
            return httpx.Response(200, json={"calc_uuid": "c-1", "calc_name": "A", "module_name": "fl_din277",
                                             "saved_result": True, "result_data": {}})
        if request.method == "POST" and path.endswith("/execute"):
            return httpx.Response(200, json={"module_name": "fl_din277", "result_data": {}})
        if request.method == "POST" and path.endswith("/calculations"):
            return httpx.Response(201, json={"project_uuid": "p-1", "calc_uuid": "c-2", "calc_name": "P A",
                                             "module_name": "fl_din277", "link_notes": []})
        if request.method == "PUT":
            return httpx.Response(200, json={"calc_uuid": "c-1", "calc_name": "A", "module_name": "fl_din277",
                                             "backup_calc_uuid": "c-3", "backup_calc_name": "A [vorher]",
                                             "link_notes": []})
        if request.method == "POST":
            return httpx.Response(202, json={"id": "job-1", "status": "queued"})
        if path.endswith("/download") or path.endswith("/export-pdf"):
            return httpx.Response(200, content=b"PK\x03\x04")
        if "/export/" in path:
            return httpx.Response(200, json={"id": "job-1", "status": "completed"})
        if path.endswith("/export-json"):
            return httpx.Response(200, json={"project_name": "P", "project_id": 1, "project_uuid": "p-1",
                                             "export_date": "2026-01-01T00:00:00+00:00", "calculations": []})
        if path.endswith("/"):
            return httpx.Response(200, json={"project_uuid": "p-1", "calculation_names": ["a/b"]})
        return httpx.Response(200, json={"project_uuid": "p-1", "calc_uuid": "c-1", "module_name": "m",
                                         "calc_name": "a/b", "calc_name_full": "m:a/b",
                                         "created_at": "2026-01-01T00:00:00", "input_data": {},
                                         "result_data": None})
    return handler


@unittest.skipIf(yaml is None or not SPEC_PATH.is_file(), "openapi.yaml or PyYAML not available")
class OpenAPIContractTests(unittest.TestCase):
    def test_all_client_requests_are_described_in_the_spec(self):
        calls = []
        with BauphysikClient("https://example.test", "t", transport=httpx.MockTransport(_handler(calls))) as client:
            client.list_projects()
            client.list_calculations("p-1")
            client.list_calculations("p-1", module="datenerfassung")
            client.get_calculation_by_uuid("c-1")
            client.get_din4108_3_layers("c-1")
            client.search_materials("holz", manufacturer=True)
            client.search_calculations("Ziegel", module="datenerfassung", project_uuid="p-1")
            client.list_api_modules()
            client.execute_module("fl_din277", input_data={"rooms": []})
            client.execute_module("uwert_glaser_din4108-3", simple_data={"layers": []})
            client.create_calculation("p-1", "fl_din277", "A", input_data={"rooms": []})
            client.update_calculation("c-1", input_data={"rooms": []})
            client.rerun_calculation("c-1", save=True)
            client.get_calculation("p-1", "a/b")
            client.get_calculations_by_uuid("p-1", ["c-1"])
            client.export_project("p-1")
            client.export_project_pdf_zip("p-1")
            client.export_project_bundle("p-1", poll_interval=0)
            client.start_project_export("p-1", "json")
            client.get_export_job("p-1", "job-1")
            client.download_export("p-1", "job-1")

        operations = _spec_operations()
        for method, path in calls:
            with self.subTest(method=method, path=path):
                matches = [t for m, p, t in operations if m == method and p.match(path)]
                self.assertTrue(matches, f"{method} {path} is not described in openapi.yaml")


if __name__ == "__main__":
    unittest.main()
