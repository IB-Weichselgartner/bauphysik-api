import json
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bauphysik_api import BauphysikAPIError, BauphysikClient, TransportError


class BauphysikClientTests(unittest.TestCase):
    def test_uuid_lookup_survives_renaming_and_checks_identity(self):
        listings = 0

        def handler(request):
            nonlocal listings
            if request.url.path == '/api/project/':
                listings += 1
                return httpx.Response(200, json={'project_uuid': 'project',
                    'calculation_names': ['old' if listings == 1 else 'renamed']})
            if request.url.path.endswith('/old'):
                return httpx.Response(404, json={'error': 'renamed'})
            return httpx.Response(200, json={'project_uuid': 'project', 'calc_uuid': 'stable-id',
                'module_name': 'uwert_glaser_din4108-3', 'calc_name': 'renamed',
                'calc_name_full': 'uwert_glaser_din4108-3:renamed', 'created_at': '2026-10-19',
                'input_data': {}, 'result_data': {'uwert': .2}})

        with BauphysikClient('https://example.test', 'secret', transport=httpx.MockTransport(handler)) as client:
            found = client.get_calculations_by_uuid('project', ['stable-id'])
        self.assertEqual(list(found), ['stable-id'])
        self.assertEqual(found['stable-id'].calc_name, 'renamed')
        self.assertEqual(listings, 2)

    def test_missing_uuid_never_substitutes_matching_name(self):
        def handler(request):
            return httpx.Response(200, json={'project_uuid': 'project', 'calculation_names': []})
        with BauphysikClient('https://example.test', 'secret', transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(BauphysikAPIError):
                client.get_calculations_by_uuid('project', ['missing'])

    def test_list_projects_returns_the_entries_untouched(self):
        calls = []
        projects = [
            {"uuid": "project-123", "name": "Demo", "project_id": 48},
            {"uuid": "project-456", "name": "Zweites Projekt", "project_id": 49},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"projects": projects})

        client = BauphysikClient(
            "https://example.test",
            "secret-token",
            transport=httpx.MockTransport(handler),
        )

        result = client.list_projects()

        # Callers select a project by uuid/project_id, so the dicts must pass
        # through unchanged.
        self.assertEqual(result, projects)
        self.assertEqual(str(calls[0].url), "https://example.test/api/projects")
        self.assertEqual(calls[0].headers["Authorization"], "Bearer secret-token")

    def test_list_projects_without_any_project_returns_an_empty_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        client = BauphysikClient(
            "https://example.test", "secret-token", transport=httpx.MockTransport(handler)
        )

        self.assertEqual(client.list_projects(), [])

    def test_list_projects_rejects_a_non_list_payload(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"projects": {"uuid": "project-123"}})

        client = BauphysikClient(
            "https://example.test", "secret-token", transport=httpx.MockTransport(handler)
        )

        with self.assertRaisesRegex(TransportError, "not a list"):
            client.list_projects()

    def test_base_url_with_path_and_port_keeps_the_api_prefix(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"projects": []})

        client = BauphysikClient(
            "http://localhost:8001/",
            "secret-token",
            transport=httpx.MockTransport(handler),
        )

        client.list_projects()

        self.assertEqual(str(calls[0].url), "http://localhost:8001/api/projects")

    def test_list_calculations_sends_bearer_token_and_parses_names(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200,
                json={
                    "project_uuid": "project-123",
                    "calculation_names": ["DIN 277", "U-Wert"],
                },
            )

        client = BauphysikClient(
            "https://example.test",
            "secret-token",
            timeout=5,
            transport=httpx.MockTransport(handler),
        )

        result = client.list_calculations("project-123")

        self.assertEqual(result.project_uuid, "project-123")
        self.assertEqual(result.calculation_names, ["DIN 277", "U-Wert"])
        request = calls[0]
        self.assertEqual(str(request.url), "https://example.test/api/project-123/")
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")
        self.assertEqual(request.headers["Accept"], "application/json")

    def test_get_calculation_quotes_calc_name_path_segment(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200,
                json={
                    "project_uuid": "project-123",
                    "calc_uuid": "calc-123",
                    "module_name": "din277",
                    "calc_name_full": "Project:DIN 277 / Room A",
                    "calc_name": "DIN 277 / Room A",
                    "created_at": "2026-04-08T12:00:00",
                    "input_data": {"a": 1},
                    "result_data": {"b": 2},
                },
            )

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        result = client.get_calculation("project-123", "DIN 277 / Room A")

        self.assertEqual(result.module_name, "din277")
        self.assertEqual(result.input_data, {"a": 1})
        self.assertEqual(
            str(calls[0].url),
            "https://example.test/api/project-123/DIN%20277%20%2F%20Room%20A",
        )

    def test_export_project_parses_project_export(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "project_name": "Demo",
                    "project_id": 42,
                    "project_uuid": "project-123",
                    "export_date": "2026-04-08T12:00:00",
                    "calculations": [{"module_name": "din277"}],
                },
            )

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        result = client.export_project("project-123")

        self.assertEqual(result.project_id, 42)
        self.assertEqual(result.calculations, [{"module_name": "din277"}])

    def test_export_project_pdf_zip_returns_raw_archive_bytes(self):
        calls = []
        archive = b"PK\x03\x04example-zip"

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200,
                content=archive,
                headers={"Content-Type": "application/zip"},
            )

        client = BauphysikClient(
            "https://example.test",
            "secret-token",
            transport=httpx.MockTransport(handler),
        )

        result = client.export_project_pdf_zip("project/123")

        self.assertEqual(result, archive)
        self.assertEqual(
            str(calls[0].url),
            "https://example.test/api/project/project%2F123/export-pdf",
        )
        self.assertEqual(calls[0].headers["Authorization"], "Bearer secret-token")
        self.assertEqual(calls[0].headers["Accept"], "application/zip")

    def test_export_project_bundle_polls_the_job_and_downloads_once(self):
        calls = []
        archive = b"PK\x03\x04bundle"
        states = iter(["running", "completed"])

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            path = request.url.path
            if request.method == "POST":
                return httpx.Response(202, json={"id": "job-1", "status": "queued"})
            if path.endswith("/download"):
                return httpx.Response(200, content=archive, headers={"Content-Type": "application/zip"})
            return httpx.Response(200, json={"id": "job-1", "status": next(states)})

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        result = client.export_project_bundle("p-1", poll_interval=0)

        self.assertEqual(result, archive)
        self.assertEqual(
            calls,
            [
                ("POST", "/api/project/p-1/export"),
                ("GET", "/api/project/p-1/export/job-1"),
                ("GET", "/api/project/p-1/export/job-1"),
                ("GET", "/api/project/p-1/export/job-1/download"),
            ],
        )

    def test_export_project_falls_back_to_a_json_job_when_too_large(self):
        calls = []
        document = {
            "project_name": "Gross",
            "project_id": 7,
            "project_uuid": "p-1",
            "export_date": "2026-10-07T12:00:00+00:00",
            "calculations": [{"module_name": "m", "calc_name": "a"}],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path, request.url.query.decode()))
            if request.url.path.endswith("/export-json"):
                return httpx.Response(409, json={"error": "zu gross"})
            if request.method == "POST":
                return httpx.Response(202, json={"id": "job-1", "status": "queued"})
            if request.url.path.endswith("/download"):
                return httpx.Response(200, content=json.dumps(document).encode())
            return httpx.Response(200, json={"id": "job-1", "status": "completed"})

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        export = client.export_project("p-1", poll_interval=0)

        self.assertEqual(export.project_name, "Gross")
        self.assertEqual(export.calculations, document["calculations"])
        self.assertIn(("POST", "/api/project/p-1/export", "format=json"), calls)

    def test_export_project_bundle_reports_a_failed_job(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(202, json={"id": "job-1", "status": "queued"})
            return httpx.Response(200, json={"id": "job-1", "status": "failed", "message": "Export fehlgeschlagen: boom"})

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        with self.assertRaises(BauphysikAPIError) as raised:
            client.export_project_bundle("p-1", poll_interval=0)
        self.assertIn("boom", str(raised.exception))

    def test_export_project_bundle_passes_limit_errors_through(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "Exportlimit erreicht"})

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        with self.assertRaises(BauphysikAPIError) as raised:
            client.export_project_bundle("p-1", poll_interval=0)
        self.assertEqual(raised.exception.status_code, 429)

    def test_export_project_bundle_falls_back_on_servers_without_jobs(self):
        archive = b"PK\x03\x04sync"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(405, text="<html>Method Not Allowed</html>")
            return httpx.Response(200, content=archive, headers={"Content-Type": "application/zip"})

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        self.assertEqual(client.export_project_bundle("p-1", poll_interval=0), archive)

    def test_api_error_uses_error_message_from_response_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": "Invalid or revoked token"},
            )

        client = BauphysikClient("https://example.test", "bad-token", transport=httpx.MockTransport(handler))

        with self.assertRaises(BauphysikAPIError) as raised:
            client.list_calculations("project-123")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(str(raised.exception), "Invalid or revoked token")
        self.assertEqual(raised.exception.response_body, {"error": "Invalid or revoked token"})

    def test_transport_error_wraps_url_errors(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down", request=request)

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        with self.assertRaisesRegex(TransportError, "network down"):
            client.list_calculations("project-123")

    def test_invalid_response_shape_raises_transport_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"project_uuid": 123, "calculation_names": ["DIN 277"]},
            )

        client = BauphysikClient("https://example.test", "secret-token", transport=httpx.MockTransport(handler))

        with self.assertRaisesRegex(TransportError, "Invalid API response"):
            client.list_calculations("project-123")


if __name__ == "__main__":
    unittest.main()


