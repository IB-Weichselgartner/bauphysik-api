from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from ._version import __version__


JsonObject = dict[str, Any]


class BauphysikAPIError(Exception):
    """Raised when the bauphysik.net API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class TransportError(Exception):
    """Raised when a request cannot be sent or decoded."""


class APIModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ProjectCalculationList(APIModel):
    project_uuid: str
    calculation_names: list[str]
    # Empty on servers before 11.11.2026, which only return names.
    calculations: list[JsonObject] = []
    raw: JsonObject

    @classmethod
    def from_json(cls, data: JsonObject) -> "ProjectCalculationList":
        return _validate_model(cls, data)


class Calculation(APIModel):
    project_uuid: Optional[str]
    calc_uuid: str
    module_name: str
    calc_name: str
    calc_name_full: str
    created_at: str
    input_data: Any
    result_data: Any
    raw: JsonObject

    @classmethod
    def from_json(cls, data: JsonObject) -> "Calculation":
        return _validate_model(cls, data)


class ProjectExport(APIModel):
    project_name: str
    project_id: int
    project_uuid: str
    export_date: str
    calculations: list[JsonObject]
    raw: JsonObject

    @classmethod
    def from_json(cls, data: JsonObject) -> "ProjectExport":
        return _validate_model(cls, data)


class BauphysikClient:
    """Client for bearer-token authenticated bauphysik.net API endpoints."""

    def __init__(
        self,
        base_url: str = "https://bauphysik.net",
        token: Optional[str] = None,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty.")
        if http_client is not None and transport is not None:
            raise ValueError("Pass either http_client or transport, not both.")
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout
        if http_client is not None:
            self._client = http_client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
                transport=transport,
            )
            self._owns_client = True

    @classmethod
    def with_token(
        cls,
        token: str,
        *,
        base_url: str = "https://bauphysik.net",
        timeout: float = 30.0,
    ) -> "BauphysikClient":
        return cls(base_url=base_url, token=token, timeout=timeout)

    def list_projects(self) -> list[JsonObject]:
        """Return the projects accessible to the authenticated token as a list
        of dicts with at least ``uuid`` and ``name``."""
        data = self._get_json("api/projects")
        projects = data.get("projects", [])
        if not isinstance(projects, list):
            raise TransportError("Invalid API response: 'projects' is not a list.")
        return projects

    def list_calculations(self, project_uuid: str, module: Optional[str] = None) -> ProjectCalculationList:
        """Return the calculations linked to a project, optionally of one module only."""
        data = self._get_json(f"api/{_path(project_uuid)}/" + _query(module=module))
        return ProjectCalculationList.from_json(data)

    def get_calculation_by_uuid(self, calc_uuid: str) -> Calculation:
        """Return one calculation by its stable id."""
        return Calculation.from_json(self._get_json(f"api/calculations/{_path(calc_uuid)}"))

    def get_din4108_3_layers(self, calc_uuid: str) -> JsonObject:
        """Return a DIN 4108-3 calculation as a simple layer list (``simple_data``)."""
        return self._get_json(f"api/calculations/{_path(calc_uuid)}/din4108-3")

    def search_materials(self, query: str = "", *, manufacturer: bool = False, limit: int = 50) -> list[JsonObject]:
        """Search the generic material catalog, or manufacturer data sheet values with ``manufacturer=True``."""
        data = self._get_json("api/materials" + _query(q=query or None, manufacturer="1" if manufacturer else None, limit=limit))
        return _list_of(data, "materials")

    def list_api_modules(self) -> list[JsonObject]:
        """Modules that can be calculated, created and updated through the API."""
        return _list_of(self._get_json("api/modules"), "modules")

    def execute_module(
        self,
        module_name: str,
        *,
        input_data: Optional[JsonObject] = None,
        simple_data: Optional[JsonObject] = None,
    ) -> JsonObject:
        """Calculate on the server without saving. ``simple_data`` only for ``uwert_glaser_din4108-3``."""
        return self._request_json(
            "POST", f"api/modules/{_path(module_name)}/execute", json=_input_body(input_data, simple_data)
        )

    def create_calculation(
        self,
        project_uuid: str,
        module_name: str,
        calc_name: str,
        *,
        input_data: Optional[JsonObject] = None,
        simple_data: Optional[JsonObject] = None,
    ) -> JsonObject:
        """Create a calculation in a project. Never overwrites: an existing name raises
        :class:`BauphysikAPIError` with status 409 and ``existing_calc_uuid`` in ``response_body``."""
        body = {"module_name": module_name, "calc_name": calc_name, **_input_body(input_data, simple_data)}
        return self._request_json("POST", f"api/projects/{_path(project_uuid)}/calculations", json=body)

    def update_calculation(
        self,
        calc_uuid: str,
        *,
        input_data: Optional[JsonObject] = None,
        simple_data: Optional[JsonObject] = None,
    ) -> JsonObject:
        """Replace the input of a calculation. The server keeps the previous state as a
        calculation of its own (``backup_calc_uuid``)."""
        return self._request_json(
            "PUT", f"api/calculations/{_path(calc_uuid)}", json=_input_body(input_data, simple_data)
        )

    def search_calculations(
        self, query: str, *, module: Optional[str] = None, project_uuid: Optional[str] = None, limit: int = 10
    ) -> list[JsonObject]:
        """Full-text search over the accessible calculations, for example for a layer structure."""
        data = self._get_json("api/search" + _query(q=query, module=module, project_uuid=project_uuid, limit=limit))
        return _list_of(data, "calculations")

    def get_calculation(self, project_uuid: str, calc_name: str) -> Calculation:
        """Return input and result JSON for one calculation in a project."""
        data = self._get_json(f"api/{_path(project_uuid)}/{_path(calc_name)}")
        return Calculation.from_json(data)

    def get_calculations_by_uuid(self, project_uuid: str, calc_uuids: list[str]) -> dict[str, Calculation]:
        """Resolve stable IDs through the server's name-based read endpoint.

        Retry discovery once if a calculation is renamed while being read.
        Never substitute a different calculation with a matching name.
        """
        wanted = set(calc_uuids)
        found: dict[str, Calculation] = {}
        if not wanted:
            return found
        for calc_uuid in sorted(wanted):
            try:
                calculation = self.get_calculation_by_uuid(calc_uuid)
            except (BauphysikAPIError, TransportError):
                continue  # older server or not found: resolved through the name list below
            if calculation.project_uuid == project_uuid and calculation.calc_uuid == calc_uuid:
                found[calc_uuid] = calculation
        if set(found) == wanted:
            return found
        for _ in range(2):
            for name in self.list_calculations(project_uuid).calculation_names:
                try:
                    calculation = self.get_calculation(project_uuid, name)
                except BauphysikAPIError as exc:
                    if exc.status_code == 404:
                        continue
                    raise
                if calculation.project_uuid != project_uuid:
                    raise TransportError("Calculation belongs to a different project.")
                if calculation.calc_uuid in wanted:
                    found[calculation.calc_uuid] = calculation
                if set(found) == wanted:
                    return found
        raise BauphysikAPIError(f"Calculation UUIDs not found: {sorted(wanted - set(found))}", status_code=404)

    def export_project(
        self,
        project_uuid: str,
        *,
        poll_interval: float = 2.0,
        max_wait: float = 1800.0,
    ) -> ProjectExport:
        """Return the full project JSON export.

        Small projects come back synchronously. When the server rejects the
        synchronous run as too large (409), the same document is produced by a
        background job and fetched once it is ready.
        """
        try:
            data = self._get_json(f"api/project/{_path(project_uuid)}/export-json")
        except BauphysikAPIError as exc:
            if exc.status_code != 409:
                raise
            raw = self._run_export_job(project_uuid, "json", poll_interval=poll_interval, max_wait=max_wait)
            try:
                data = json.loads(raw)
            except (JSONDecodeError, UnicodeDecodeError) as decode_exc:
                raise TransportError("Invalid API response: export job did not return JSON.") from decode_exc
        return ProjectExport.from_json(data)

    def export_project_pdf_zip(self, project_uuid: str) -> bytes:
        """Return a ZIP archive (raw bytes) with one JSON and one PDF per
        calculation linked to the project.

        Synchronous; the server answers 409 for projects above its sync limit.
        Prefer :meth:`export_project_bundle`, which works for every size.
        """
        return self._get_bytes(f"api/project/{_path(project_uuid)}/export-pdf")

    def start_project_export(self, project_uuid: str, output_format: str = "zip") -> JsonObject:
        """Queue a background export; returns the job (``id``, ``status``,
        ``status_url``). ``output_format="json"`` produces the export-json
        document instead of the ZIP. An export already running for the project
        is returned instead of starting a second one."""
        path = f"api/project/{_path(project_uuid)}/export"
        if output_format != "zip":
            path += f"?format={quote(output_format, safe='')}"
        return self._request_json("POST", path)

    def get_export_job(self, project_uuid: str, job_id: str) -> JsonObject:
        return self._get_json(f"api/project/{_path(project_uuid)}/export/{_path(job_id)}")

    def download_export(self, project_uuid: str, job_id: str) -> bytes:
        """Download a finished export. The server deletes the ZIP afterwards."""
        return self._get_bytes(f"api/project/{_path(project_uuid)}/export/{_path(job_id)}/download")

    def export_project_bundle(
        self,
        project_uuid: str,
        *,
        poll_interval: float = 2.0,
        max_wait: float = 1800.0,
    ) -> bytes:
        """Run a background export, wait for it and return the ZIP bytes.

        Same ZIP layout as :meth:`export_project_pdf_zip`. Servers without the
        background endpoint fall back to the synchronous export.
        """
        try:
            job = self.start_project_export(project_uuid)
        except BauphysikAPIError as exc:
            if exc.status_code in (404, 405) and _error_message(exc.response_body) is None:
                return self.export_project_pdf_zip(project_uuid)
            raise
        except TransportError:
            # An older server answers the unknown POST route with an HTML 404/405.
            return self.export_project_pdf_zip(project_uuid)
        return self._wait_and_download(project_uuid, job, poll_interval=poll_interval, max_wait=max_wait)

    def _run_export_job(
        self, project_uuid: str, output_format: str, *, poll_interval: float, max_wait: float
    ) -> bytes:
        job = self.start_project_export(project_uuid, output_format)
        return self._wait_and_download(project_uuid, job, poll_interval=poll_interval, max_wait=max_wait)

    def _wait_and_download(
        self, project_uuid: str, job: JsonObject, *, poll_interval: float, max_wait: float
    ) -> bytes:
        deadline = time.monotonic() + max_wait
        while job.get("status") in ("queued", "running"):
            if time.monotonic() > deadline:
                raise TransportError(
                    f"bauphysik.net export {job.get('id')} did not finish within {max_wait:.0f} s."
                )
            time.sleep(poll_interval)
            job = self.get_export_job(project_uuid, job["id"])

        if job.get("status") != "completed":
            raise BauphysikAPIError(
                job.get("message") or f"bauphysik.net export ended with status {job.get('status')}.",
                status_code=200,
                response_body=job,
            )
        return self.download_export(project_uuid, job["id"])

    def request_json(self, path: str) -> JsonObject:
        """Send a GET request to a custom API path and return the decoded JSON object."""
        return self._get_json(path.lstrip("/"))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BauphysikClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _get_json(self, path: str) -> JsonObject:
        return self._request_json("GET", path)

    def _request_json(self, method: str, path: str, *, json: Optional[JsonObject] = None) -> JsonObject:
        try:
            response = self._client.request(method, path.lstrip("/"), json=json)
        except httpx.RequestError as exc:
            raise TransportError(f"Could not send bauphysik.net API request: {exc}") from exc

        payload = _decode_json(response)
        if not isinstance(payload, dict):
            raise TransportError("Invalid API response: expected a JSON object.")
        if response.is_error:
            message = _error_message(payload) or f"bauphysik.net API returned HTTP {response.status_code}."
            raise BauphysikAPIError(message, status_code=response.status_code, response_body=payload)
        return payload

    def _get_bytes(self, path: str) -> bytes:
        try:
            response = self._client.get(
                path.lstrip("/"),
                headers={"Accept": "application/zip"},
            )
        except httpx.RequestError as exc:
            raise TransportError(f"Could not send bauphysik.net API request: {exc}") from exc

        if response.is_error:
            payload = None
            try:
                payload = response.json()
            except JSONDecodeError:
                pass
            message = _error_message(payload) or f"bauphysik.net API returned HTTP {response.status_code}."
            raise BauphysikAPIError(message, status_code=response.status_code, response_body=payload)
        return response.content

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"bauphysik-api-python/{__version__}",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


def _path(value: str) -> str:
    if not value:
        raise ValueError("Path values must not be empty.")
    return quote(value, safe="")


def _query(**params: Any) -> str:
    present = {key: value for key, value in params.items() if value not in (None, "")}
    return "?" + urlencode(present) if present else ""


def _input_body(input_data: Optional[JsonObject], simple_data: Optional[JsonObject]) -> JsonObject:
    if (input_data is None) == (simple_data is None):
        raise ValueError("Pass exactly one of input_data or simple_data.")
    return {"input_data": input_data} if input_data is not None else {"simple_data": simple_data}


def _list_of(data: JsonObject, key: str) -> list[JsonObject]:
    items = data.get(key, [])
    if not isinstance(items, list):
        raise TransportError(f"Invalid API response: '{key}' is not a list.")
    return items


def _decode_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except JSONDecodeError as exc:
        raise TransportError("Invalid API response: response body is not valid JSON.") from exc


def _error_message(payload: Any) -> Optional[str]:
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return None


def _validate_model(model_type: type[APIModel], data: JsonObject) -> APIModel:
    try:
        return model_type.model_validate({**data, "raw": data})
    except ValidationError as exc:
        message = exc.errors(include_url=False)[0]["msg"] if exc.errors() else "Invalid API response."
        raise TransportError(f"Invalid API response: {message}") from exc
