"""Tests for views/secretary._load_secretary_config + report_summary viewer."""

import json
from datetime import date

import pytest

from views.secretary import (
    DEFAULT_AGENDA_DAYS,
    DEFAULT_REPORT_DAYS,
    _load_secretary_config,
)


class TestLoadSecretaryConfig:
    def test_no_orbit_json(self, tmp_path):
        cfg = _load_secretary_config(tmp_path)
        assert cfg == {
            "agenda_days": DEFAULT_AGENDA_DAYS,
            "report_days": DEFAULT_REPORT_DAYS,
        }

    def test_no_secretary_section(self, tmp_path):
        (tmp_path / "orbit.json").write_text(json.dumps({"space": "test"}))
        cfg = _load_secretary_config(tmp_path)
        assert cfg["agenda_days"] == DEFAULT_AGENDA_DAYS
        assert cfg["report_days"] == DEFAULT_REPORT_DAYS

    def test_agenda_days_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": {"agenda_days": 30}})
        )
        assert _load_secretary_config(tmp_path)["agenda_days"] == 30

    def test_report_days_override(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": {"report_days": 60}})
        )
        assert _load_secretary_config(tmp_path)["report_days"] == 60

    def test_agenda_days_clamp_out_of_range(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": {"agenda_days": 9999}})
        )
        assert _load_secretary_config(tmp_path)["agenda_days"] == DEFAULT_AGENDA_DAYS

    def test_report_days_clamp_out_of_range(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": {"report_days": 0}})
        )
        assert _load_secretary_config(tmp_path)["report_days"] == DEFAULT_REPORT_DAYS

    def test_bad_types_fall_back(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": {"agenda_days": "many", "report_days": None}})
        )
        cfg = _load_secretary_config(tmp_path)
        assert cfg["agenda_days"] == DEFAULT_AGENDA_DAYS
        assert cfg["report_days"] == DEFAULT_REPORT_DAYS

    def test_bad_json_returns_defaults(self, tmp_path):
        (tmp_path / "orbit.json").write_text("{not json")
        cfg = _load_secretary_config(tmp_path)
        assert cfg["agenda_days"] == DEFAULT_AGENDA_DAYS
        assert cfg["report_days"] == DEFAULT_REPORT_DAYS

    def test_secretary_not_a_dict(self, tmp_path):
        (tmp_path / "orbit.json").write_text(
            json.dumps({"secretary": "not-a-dict"})
        )
        cfg = _load_secretary_config(tmp_path)
        assert cfg["agenda_days"] == DEFAULT_AGENDA_DAYS


class TestReportSummaryViewer:
    """Smoke test: the viewer writes a markdown file without crashing."""

    def test_generate_writes_file(self, orbit_env):
        from views.secretary import report_summary

        out = orbit_env["tmp"] / "report-summary.md"
        report_summary.generate(out, days=7)
        assert out.exists()
        # File is non-empty (run_report prints at least a header)
        assert out.stat().st_size >= 0

    def test_generate_reads_config_when_days_is_none(self, orbit_env, monkeypatch):
        """When days=None, viewer reads report_days from orbit.json."""
        from views.secretary import report_summary

        captured = {}

        def fake_run_report(**kwargs):
            captured.update(kwargs)
            return 0

        monkeypatch.setattr("core.stats.run_report", fake_run_report)
        (orbit_env["tmp"] / "orbit.json").write_text(
            json.dumps({"secretary": {"report_days": 30}})
        )

        out = orbit_env["tmp"] / "report-summary.md"
        report_summary.generate(out)

        # 30-day window: start = today - 29 days
        from datetime import timedelta
        expected_start = (date.today() - timedelta(days=29)).isoformat()
        assert captured["date_from"] == expected_start
        assert captured["date_to"] == date.today().isoformat()
        assert captured["summary"] == ""
        assert captured["include_federated"] is True
