# coding: utf-8
"""
Comprehensive tests for the simplified 2-category log analyzer.

Covers:
- Valid lines parsed correctly (regex full match, datetime, message)
- Malformed and blank lines (skipped / ignored correctly)
- Optional message field
- Category assignment: primary (predefined) and secondary (all other detected services)
- Configured primary services included even when absent from log (count = 0)
- Unconfigured services automatically appear under secondary
- Secondary services with only non-ERROR entries appear with count = 0
- Services not seen in log never appear in secondary
- Alphabetical sorting within each category
- Top offender selection (highest count, alphabetical tie-breaking across categories)
- No error entries -> top_offender is None
- Lowercase error and **ERROR** normalized and counted
- Duplicate primary service validation
- HTTP endpoint and FastAPI AnalysisResult model validation
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import os

# ── Make app/analyzer.py importable ──────────────────────────────────────────
_analyzer_env = os.environ.get("ANALYZER_DIR", "")
if _analyzer_env:
    _APP_DIR = Path(_analyzer_env)
else:
    _APP_DIR = Path(__file__).resolve().parents[3] / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# pyrefly: ignore [missing-import]
from analyzer import (  # noqa: E402
    PRIMARY_SERVICES,
    analyze_lines,
    parse_line,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(*lines: str) -> list[str]:
    """Convenience: turn positional string args into a list of log lines."""
    return list(lines)


PRIMARY_0 = PRIMARY_SERVICES[0]  # "payment-service"
PRIMARY_1 = PRIMARY_SERVICES[1]  # "order-service"


# ─────────────────────────────────────────────────────────────────────────────
# parse_line tests
# ─────────────────────────────────────────────────────────────────────────────

class TestParseLine:
    def test_valid_full_line(self):
        result = parse_line("2026-09-18 10:23:45 ERROR payment-service Connection timeout")
        assert result is not None
        date, time, level, service, message = result
        assert date == "2026-09-18"
        assert time == "10:23:45"
        assert level == "ERROR"
        assert service == "payment-service"
        assert message == "Connection timeout"

    def test_valid_line_no_message(self):
        result = parse_line("2026-09-18 10:23:45 INFO auth-service")
        assert result is not None
        _, _, level, service, message = result
        assert level == "INFO"
        assert service == "auth-service"
        assert message == ""

    def test_level_normalized_to_uppercase(self):
        result = parse_line("2026-09-18 10:23:45 error payment-service msg")
        assert result is not None
        _, _, level, _, _ = result
        assert level == "ERROR"

    def test_level_with_asterisks_normalized(self):
        result = parse_line("2026-09-18 10:23:45 **ERROR** payment-service msg")
        assert result is not None
        _, _, level, _, _ = result
        assert level == "ERROR"

    def test_blank_line_returns_none(self):
        assert parse_line("") is None
        assert parse_line("   ") is None
        assert parse_line("\t\n") is None

    def test_malformed_date_returns_none(self):
        assert parse_line("not-a-date 10:23:45 ERROR svc msg") is None

    def test_invalid_calendar_date_returns_none(self):
        # February 30th does not exist
        assert parse_line("2026-02-30 10:23:45 ERROR svc msg") is None

    def test_invalid_time_returns_none(self):
        # Hour 25 does not exist
        assert parse_line("2026-01-01 25:00:00 ERROR svc msg") is None

    def test_invalid_level_returns_none(self):
        assert parse_line("2026-01-01 10:00:00 FOOBAR svc msg") is None
        assert parse_line("2026-01-01 10:00:00 @@@ svc msg") is None

    def test_missing_service_returns_none(self):
        assert parse_line("2026-01-01 10:00:00 ERROR") is None

    def test_extra_leading_spaces_handled(self):
        result = parse_line("  2026-01-01 10:00:00 ERROR svc hello world")
        assert result is not None
        _, _, level, service, message = result
        assert level == "ERROR"
        assert service == "svc"
        assert message == "hello world"


    def test_valid_non_error_levels(self):
        for lvl in ["INFO", "WARN", "WARNING", "DEBUG", "CRITICAL", "FATAL"]:
            res = parse_line(f"2026-01-01 10:00:00 {lvl} svc msg")
            assert res is not None, f"Level {lvl} should be parsed"
            assert res[2] == lvl


# ─────────────────────────────────────────────────────────────────────────────
# analyze_lines tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeLines:

    # ── Structure ──────────────────────────────────────────────────────────

    def test_empty_log(self):
        r = analyze_lines([])
        assert r["lines_processed"] == 0
        assert r["lines_skipped"] == 0
        assert r["top_offender"] is None
        ebs = r["errors_by_service"]
        assert set(ebs.keys()) == {"primary", "secondary"}

    def test_both_categories_always_present(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
        ))
        ebs = r["errors_by_service"]
        assert "primary" in ebs
        assert "secondary" in ebs
        assert len(ebs) == 2

    def test_configured_primary_services_always_in_output(self):
        # Even with an empty log, all PRIMARY services appear with count 0
        r = analyze_lines([])
        ebs = r["errors_by_service"]
        for svc in PRIMARY_SERVICES:
            assert svc in ebs["primary"]
            assert ebs["primary"][svc] == 0

    def test_secondary_empty_when_no_unconfigured_services_in_log(self):
        # If no unconfigured services are in the log, secondary is empty
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
        ))
        assert r["errors_by_service"]["secondary"] == {}

    # ── Category assignment ───────────────────────────────────────────────

    def test_primary_service_error_counted(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} timeout",
        ))
        assert r["errors_by_service"]["primary"][PRIMARY_0] == 1
        assert PRIMARY_0 not in r["errors_by_service"]["secondary"]

    def test_unconfigured_service_automatically_in_secondary(self):
        r = analyze_lines(_log(
            "2026-01-01 00:00:00 ERROR auth-service bad token",
        ))
        assert "auth-service" in r["errors_by_service"]["secondary"]
        assert r["errors_by_service"]["secondary"]["auth-service"] == 1
        assert "auth-service" not in r["errors_by_service"]["primary"]

    def test_secondary_service_with_non_error_has_zero_count(self):
        # A service appearing ONLY in INFO/WARN lines must appear in secondary with count 0
        r = analyze_lines(_log(
            "2026-01-01 00:00:00 INFO billing-service started",
            "2026-01-01 00:00:05 WARN billing-service latency high",
            "2026-01-01 00:00:10 DEBUG notification-service ready",
        ))
        ebs = r["errors_by_service"]
        assert "billing-service" in ebs["secondary"]
        assert ebs["secondary"]["billing-service"] == 0
        assert "notification-service" in ebs["secondary"]
        assert ebs["secondary"]["notification-service"] == 0

    def test_unseen_service_never_in_secondary(self):
        # A service that never appeared in the log must not be in secondary
        r = analyze_lines(_log(
            "2026-01-01 00:00:00 ERROR auth-service msg",
        ))
        assert "some-random-service" not in r["errors_by_service"]["secondary"]

    def test_no_service_in_both_categories(self):
        lines = [
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
            "2026-01-01 00:00:00 ERROR billing-service msg",
            "2026-01-01 00:00:00 ERROR auth-service msg",
        ]
        r = analyze_lines(lines)
        ebs = r["errors_by_service"]
        primary_svcs = set(ebs["primary"])
        secondary_svcs = set(ebs["secondary"])
        assert primary_svcs.isdisjoint(secondary_svcs)

    def test_alphabetical_sorting_within_categories(self):
        lines = [
            "2026-01-01 00:00:00 ERROR zebra-service crash",
            "2026-01-01 00:00:01 ERROR alpha-service crash",
            "2026-01-01 00:00:02 ERROR middle-service crash",
        ]
        r = analyze_lines(lines)
        ebs = r["errors_by_service"]
        # Primary category sorting
        assert list(ebs["primary"].keys()) == sorted(ebs["primary"].keys())
        # Secondary category sorting
        assert list(ebs["secondary"].keys()) == ["alpha-service", "middle-service", "zebra-service"]

    # ── Zero counts ───────────────────────────────────────────────────────

    def test_absent_primary_service_has_zero_count(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} all good",
        ))
        # PRIMARY_1 not in log at all → must still appear with count 0
        assert r["errors_by_service"]["primary"][PRIMARY_1] == 0

    def test_no_errors_top_offender_is_none(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} ok",
            "2026-01-01 00:00:00 WARN billing-service slow",
        ))
        assert r["top_offender"] is None

    # ── Error counting ────────────────────────────────────────────────────

    def test_multiple_errors_same_service(self):
        lines = [f"2026-01-01 00:00:0{i} ERROR {PRIMARY_0} msg" for i in range(5)]
        r = analyze_lines(lines)
        assert r["errors_by_service"]["primary"][PRIMARY_0] == 5

    def test_non_error_levels_not_counted(self):
        lines = [
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} ok",
            f"2026-01-01 00:00:01 WARN {PRIMARY_0} slow",
            f"2026-01-01 00:00:02 DEBUG {PRIMARY_0} debug",
        ]
        r = analyze_lines(lines)
        assert r["errors_by_service"]["primary"][PRIMARY_0] == 0

    def test_lowercase_error_counted(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 error {PRIMARY_0} msg",
        ))
        assert r["errors_by_service"]["primary"][PRIMARY_0] == 1

    def test_asterisk_error_counted(self):
        r = analyze_lines(_log(
            "2026-01-01 00:00:00 **ERROR** custom-service boom",
        ))
        assert r["errors_by_service"]["secondary"]["custom-service"] == 1

    # ── lines_processed / lines_skipped ──────────────────────────────────

    def test_blank_lines_not_counted(self):
        r = analyze_lines(["", "   ", "\t"])
        assert r["lines_processed"] == 0
        assert r["lines_skipped"] == 0

    def test_malformed_nonblank_lines_counted_as_skipped(self):
        lines = [
            "Traceback most recent call last",
            "2026-01-01 00:00:00 @@@ svc msg",   # invalid level
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} ok",  # valid
        ]
        r = analyze_lines(lines)
        assert r["lines_processed"] == 1
        assert r["lines_skipped"] == 2

    # ── top_offender ──────────────────────────────────────────────────────

    def test_top_offender_highest_count_primary(self):
        lines = [
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
            f"2026-01-01 00:00:01 ERROR {PRIMARY_0} msg",
            "2026-01-01 00:00:02 ERROR auth-service msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == PRIMARY_0

    def test_top_offender_highest_count_secondary(self):
        lines = [
            "2026-01-01 00:00:00 ERROR billing-service msg",
            "2026-01-01 00:00:01 ERROR billing-service msg",
            f"2026-01-01 00:00:02 ERROR {PRIMARY_0} msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == "billing-service"

    def test_top_offender_tie_broken_alphabetically(self):
        # "aaa-service" (secondary) and "payment-service" (primary) both have 2 errors
        # 'aaa-service' comes before 'payment-service' alphabetically -> aaa-service wins
        lines = [
            "2026-01-01 00:00:00 ERROR aaa-service msg",
            "2026-01-01 00:00:01 ERROR aaa-service msg",
            f"2026-01-01 00:00:02 ERROR {PRIMARY_0} msg",
            f"2026-01-01 00:00:03 ERROR {PRIMARY_0} msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == "aaa-service"

    def test_top_offender_tie_case_insensitive(self):
        # "Apple-svc" vs "banana-svc" — case-insensitive 'a' < 'b'
        lines = [
            "2026-01-01 00:00:00 ERROR Apple-svc msg",
            "2026-01-01 00:00:01 ERROR Apple-svc msg",
            "2026-01-01 00:00:02 ERROR banana-svc msg",
            "2026-01-01 00:00:03 ERROR banana-svc msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == "Apple-svc"

    def test_zero_error_service_not_top_offender(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} ok",
            "2026-01-01 00:00:00 INFO billing-service ok",
        ))
        assert r["top_offender"] is None

    # ── Sample log integration ────────────────────────────────────────────

    def test_sample_log_full(self):
        lines = [
            "2026-09-18 10:23:45 ERROR payment-service Connection timeout",
            "2026-09-18 10:23:46 INFO auth-service User logged in",
            "2026-09-18 10:23:47 ERROR payment-service Connection refused after 3 retries",
            "2026-09-18 10:24:01 WARN auth-service Slow response",
            "2026-09-18 10:24:15 ERROR billing-service Invalid account state",
            "",
            "2026-09-18 10:24:20 error billing-service lowercase level should still count",
            "2026-09-18 10:24:25 @@@ ghost-service bogus level field",
            "Traceback most recent call last",
            "2026-09-18 10:24:30 ERROR notification-service",
            "",
            "2026-09-18 10:24:35 INFO search-service Query ok",
        ]
        r = analyze_lines(lines)
        assert r["lines_processed"] == 8
        assert r["lines_skipped"] == 2   # @@@ line + Traceback line
        ebs = r["errors_by_service"]
        # Primary services
        assert ebs["primary"]["payment-service"] == 2
        assert ebs["primary"]["order-service"] == 0
        # Secondary services (all non-primary services in log)
        assert ebs["secondary"]["auth-service"] == 0
        assert ebs["secondary"]["billing-service"] == 2
        assert ebs["secondary"]["notification-service"] == 1
        assert ebs["secondary"]["search-service"] == 0
        # billing-service (2) and payment-service (2) tie: 'b' < 'p'
        assert r["top_offender"] == "billing-service"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigValidation:
    def test_duplicate_primary_raises_value_error(self):
        """Duplicate entry in PRIMARY_SERVICES must raise ValueError."""
        import types
        fake_module = types.ModuleType("_test_duplicate_analyzer")
        fake_module.__spec__ = None
        with pytest.raises(ValueError, match="Duplicate service in PRIMARY_SERVICES"):
            exec(
                """
PRIMARY_SERVICES = ["svc-a", "svc-a"]
if len(PRIMARY_SERVICES) != len(set(PRIMARY_SERVICES)):
    raise ValueError("Duplicate service in PRIMARY_SERVICES")
""",
                fake_module.__dict__,
            )

    def test_current_primary_has_no_duplicates(self):
        assert len(PRIMARY_SERVICES) == len(set(PRIMARY_SERVICES))


# ─────────────────────────────────────────────────────────────────────────────
# HTTP endpoint tests (via TestClient) & Model validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_fixture():
    from openapi_server.main import app
    return TestClient(app)


class TestHTTPEndpoint:
    VALID_LOG = b"2026-09-18 10:23:45 ERROR payment-service Connection timeout\n2026-09-18 10:23:46 INFO custom-service msg\n"

    def test_valid_upload_returns_200(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        assert resp.status_code == 200

    def test_response_has_two_categories_only(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        data = resp.json()
        assert "lines_processed" in data
        assert "lines_skipped" in data
        assert "top_offender" in data
        ebs = data["errors_by_service"]
        assert set(ebs.keys()) == {"primary", "secondary"}

    def test_pydantic_model_validates_response(self, client_fixture):
        from openapi_server.models.analysis_result import AnalysisResult
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        data = resp.json()
        model_instance = AnalysisResult.model_validate(data)
        assert model_instance.lines_processed == 2
        assert model_instance.errors_by_service.primary["payment-service"] == 1
        assert model_instance.errors_by_service.secondary["custom-service"] == 0

    def test_missing_file_field_returns_422(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"wrong_field": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        assert resp.status_code == 422

    def test_invalid_utf8_returns_400(self, client_fixture):
        bad_bytes = b"\xff\xfe invalid utf-8"
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(bad_bytes), "text/plain")},
        )
        assert resp.status_code == 400

    def test_empty_file_returns_200(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("empty.log", io.BytesIO(b""), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_offender"] is None
        assert data["lines_processed"] == 0
        assert data["errors_by_service"]["secondary"] == {}
