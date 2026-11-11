from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import Any, Optional
from urllib.parse import quote

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
    raw: JsonObject

    @classmethod
    def from_json(cls, data: JsonObject) -> "ProjectCalculationList":
        return _validate_model(cls, data)


class Calculation(APIModel):
    project_uuid: str
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

    def list_calculations(self, project_uuid: str) -> ProjectCalculationList:
        """Return calculation names linked to a project."""
        data = self._get_json(f"api/{_path(project_uuid)}/")
        return ProjectCalculationList.from_json(data)

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

    def _request_json(self, method: str, path: str) -> JsonObject:
        try:
            response = self._client.request(method, path.lstrip("/"))
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
