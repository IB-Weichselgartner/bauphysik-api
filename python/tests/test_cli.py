"""Kommandozeile ``bauphysik``."""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bauphysik_api import BauphysikClient, cli  # noqa: E402

REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "calculation-inputs.json"

WALL = {
    "ziel_u_kategorie": "aussenwand",
    "layers": [{"name": "Ziegel", "thickness_m": 0.365, "material": "Vollziegel"}],
}


def run(argv, handler, capsys):
    calls = []

    def recording(request):
        calls.append(request)
        return handler(request)

    client = BauphysikClient("https://example.test", "t", transport=httpx.MockTransport(recording))
    code = cli.main(argv, client=client)
    out, err = capsys.readouterr()
    return code, (json.loads(out) if out else None), (json.loads(err) if err else None), calls


def test_package_schemas_match_the_repository_copy():
    if not REPO_SCHEMAS.is_file():
        pytest.skip("not in the repository")
    assert cli.load_schemas() == json.loads(REPO_SCHEMAS.read_text(encoding="utf-8"))


def test_schema_works_offline_and_resolves_references(capsys):
    assert cli.main(["schema", "uwert_glaser_din4108-3", "--simple"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["$schema"].endswith("2020-12/schema")
    assert "layers" in schema["properties"]
    assert all("#/components/" not in ref for ref in _refs(schema))


def _refs(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "$ref":
                yield v
            else:
                yield from _refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _refs(v)


def test_unknown_module_is_a_usage_error(capsys):
    assert cli.main(["schema", "wb_din10211"]) == cli.EXIT_USAGE
    assert "nicht verfügbar" in json.loads(capsys.readouterr().err)["error"]


def test_invalid_input_is_refused_before_any_request(tmp_path, capsys):
    broken = tmp_path / "wand.json"
    broken.write_text(json.dumps({**WALL, "layers": [{"name": "Ziegel", "thickness_m": -1, "material": "X"}]}))

    code, out, err, calls = run(
        ["calc", "execute", "uwert_glaser_din4108-3", "--input", str(broken), "--simple"],
        lambda r: httpx.Response(500), capsys,
    )

    assert code == cli.EXIT_USAGE and calls == []
    assert any("thickness_m" in d["loc"] for d in err["details"])


def test_create_sends_validated_simple_data(tmp_path, capsys):
    wall = tmp_path / "wand.json"
    wall.write_text(json.dumps(WALL), encoding="utf-8")

    def handler(request):
        return httpx.Response(201, json={"project_uuid": "p-1", "calc_uuid": "c-1", "calc_name": "Haus AW",
                                         "module_name": "uwert_glaser_din4108-3", "link_notes": []})

    code, out, _err, calls = run(
        ["calc", "create", "p-1", "uwert_glaser_din4108-3", "AW", "--input", str(wall), "--simple"], handler, capsys
    )

    assert code == 0 and out["calc_uuid"] == "c-1"
    assert calls[0].method == "POST" and calls[0].url.path == "/api/projects/p-1/calculations"
    assert json.loads(calls[0].content) == {"module_name": "uwert_glaser_din4108-3", "calc_name": "AW",
                                            "simple_data": WALL}


def test_existing_name_reports_409_with_the_existing_uuid(tmp_path, capsys):
    data = tmp_path / "de.json"
    data.write_text("{}", encoding="utf-8")

    code, _out, err, _calls = run(
        ["calc", "create", "p-1", "datenerfassung", "E", "--input", str(data)],
        lambda r: httpx.Response(409, json={"error": "exists", "existing_calc_uuid": "c-9"}), capsys,
    )

    assert code == cli.EXIT_API and err["status"] == 409 and err["existing_calc_uuid"] == "c-9"


def test_materials_search_with_hersteller(capsys):
    def handler(request):
        assert request.url.params["manufacturer"] == "1"
        return httpx.Response(200, json={"query": "steico", "manufacturer": True, "count": 1,
                                         "materials": [{"manufacturer": "STEICO", "name": "STEICO base"}]})

    code, out, _err, _calls = run(["materials", "search", "steico", "--hersteller"], handler, capsys)

    assert code == 0 and out["hersteller"] is True and out["materials"][0]["manufacturer"] == "STEICO"


def test_older_server_without_the_endpoint(capsys):
    code, _out, err, _calls = run(
        ["modules", "list"], lambda r: httpx.Response(404, text="<html>Not Found</html>"), capsys
    )

    assert code == cli.EXIT_API and "kennt diesen Befehl noch nicht" in err["error"]


def test_redirect_of_an_older_server_means_unknown_command(capsys):
    code, _out, err, _calls = run(
        ["materials", "search", "fichte"],
        lambda r: httpx.Response(308, headers={"Location": "/api/materials/"}, text="Redirecting"), capsys,
    )

    assert code == cli.EXIT_API and "kennt diesen Befehl noch nicht" in err["error"]


def test_calc_list_on_an_older_server_shows_the_names(capsys):
    code, out, _err, _calls = run(
        ["calc", "list", "p-1"],
        lambda r: httpx.Response(200, json={"project_uuid": "p-1", "calculation_names": ["Erfassung"]}), capsys,
    )

    assert code == 0 and out["calculation_names"] == ["Erfassung"] and "älter" in out["hinweis"]


def test_update_validates_against_the_stored_module(tmp_path, capsys):
    data = tmp_path / "de.json"
    data.write_text(json.dumps({"unbekanntes_feld": "x"}), encoding="utf-8")

    def handler(request):
        return httpx.Response(200, json={"project_uuid": "p-1", "calc_uuid": "c-1", "module_name": "datenerfassung",
                                         "calc_name": "E", "calc_name_full": "datenerfassung:E",
                                         "created_at": None, "input_data": {}, "result_data": None})

    code, _out, err, calls = run(["calc", "update", "c-1", "--input", str(data)], handler, capsys)

    assert code == cli.EXIT_USAGE and [c.method for c in calls] == ["GET"]
    assert "unbekanntes_feld" in json.dumps(err, ensure_ascii=False)


def test_export_refuses_to_overwrite(tmp_path, capsys):
    target = tmp_path / "export.zip"
    target.write_bytes(b"alt")

    code, _out, err, calls = run(["export", "p-1", "--out", str(target)], lambda r: httpx.Response(500), capsys)

    assert code == cli.EXIT_USAGE and calls == [] and target.read_bytes() == b"alt"


def test_missing_token_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("BAUPHYSIK_API_TOKEN", raising=False)
    assert cli.main(["projects", "list"]) == cli.EXIT_USAGE
    assert "BAUPHYSIK_API_TOKEN" in json.loads(capsys.readouterr().err)["error"]
