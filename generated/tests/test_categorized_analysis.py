# coding: utf-8
"""
Comprehensive tests for the categorized log analyzer.

Covers:
- Valid lines parsed correctly
- Malformed and blank lines (skipped / ignored correctly)
- Optional message field
- Category assignment: primary, secondary, other_services
- Zero counts for configured services absent from the log
- Alphabetical tie-breaking for top_offender
- Empty log, error-free log
- Multiple ERRORs for the same service
- Non-ERROR levels not counted
- No service appears in multiple categories
- PRIMARY/SECONDARY overlap detection
- HTTP endpoint: valid upload, wrong field, bad UTF-8
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Make app/analyzer.py importable ──────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parents[3] / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# pyrefly: ignore [missing-import]
from analyzer import (  # noqa: E402
    PRIMARY_SERVICES,
    SECONDARY_SERVICES,
    analyze_lines,
    parse_line,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(*lines: str) -> list[str]:
    """Convenience: turn positional string args into a list of log lines."""
    return list(lines)


def _all_services(result: dict) -> set[str]:
    ebs = result["errors_by_service"]
    return (
        set(ebs["primary"])
        | set(ebs["secondary"])
        | set(ebs["other_services"])
    )


PRIMARY_0 = PRIMARY_SERVICES[0]    # "payment-service"
PRIMARY_1 = PRIMARY_SERVICES[1]    # "order-service"
SECONDARY_0 = SECONDARY_SERVICES[0]  # "billing-service"
SECONDARY_1 = SECONDARY_SERVICES[1]  # "inventory-service"


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

    def test_too_few_fields_returns_none(self):
        assert parse_line("2026-09-18 10:23:45 ERROR") is None

    def test_invalid_level_returns_none(self):
        # @@@ is not a valid level
        assert parse_line("2026-09-18 10:24:25 @@@ ghost-service bogus") is None

    def test_invalid_date_returns_none(self):
        assert parse_line("9999-99-99 99:99:99 ERROR svc msg") is None

    def test_traceback_line_returns_none(self):
        assert parse_line("Traceback most recent call last") is None

    def test_message_with_spaces_captured(self):
        result = parse_line("2026-09-18 10:23:45 WARN svc this is a multi word message")
        assert result is not None
        assert result[4] == "this is a multi word message"

    def test_multiple_spaces_between_fields(self):
        # Leading whitespace + multiple spaces between fields
        result = parse_line("  2026-09-18  10:23:45  ERROR  payment-service  msg")
        assert result is not None
        _, _, level, service, _ = result
        assert level == "ERROR"
        assert service == "payment-service"


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
        assert set(ebs.keys()) == {"primary", "secondary", "other_services"}

    def test_all_three_categories_always_present(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
        ))
        ebs = r["errors_by_service"]
        assert "primary" in ebs
        assert "secondary" in ebs
        assert "other_services" in ebs

    def test_configured_services_always_in_output(self):
        # Even with an empty log, all PRIMARY and SECONDARY services appear
        r = analyze_lines([])
        ebs = r["errors_by_service"]
        for svc in PRIMARY_SERVICES:
            assert svc in ebs["primary"]
        for svc in SECONDARY_SERVICES:
            assert svc in ebs["secondary"]

    # ── Category assignment ───────────────────────────────────────────────

    def test_primary_service_error_counted(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} timeout",
        ))
        assert r["errors_by_service"]["primary"][PRIMARY_0] == 1

    def test_secondary_service_error_counted(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {SECONDARY_0} bad state",
        ))
        assert r["errors_by_service"]["secondary"][SECONDARY_0] == 1

    def test_unknown_service_goes_to_other(self):
        r = analyze_lines(_log(
            "2026-01-01 00:00:00 ERROR unknown-svc crash",
        ))
        assert "unknown-svc" in r["errors_by_service"]["other_services"]
        assert r["errors_by_service"]["other_services"]["unknown-svc"] == 1

    def test_primary_service_not_in_other(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
        ))
        assert PRIMARY_0 not in r["errors_by_service"]["other_services"]

    def test_secondary_service_not_in_other(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 ERROR {SECONDARY_0} msg",
        ))
        assert SECONDARY_0 not in r["errors_by_service"]["other_services"]

    def test_no_service_in_multiple_categories(self):
        lines = [
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
            f"2026-01-01 00:00:00 ERROR {SECONDARY_0} msg",
            "2026-01-01 00:00:00 ERROR other-svc msg",
        ]
        r = analyze_lines(lines)
        ebs = r["errors_by_service"]
        all_services = list(ebs["primary"]) + list(ebs["secondary"]) + list(ebs["other_services"])
        assert len(all_services) == len(set(all_services)), "A service appeared in multiple categories"

    # ── Zero counts ───────────────────────────────────────────────────────

    def test_absent_primary_service_has_zero_count(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} all good",
        ))
        # PRIMARY_1 not in log at all → must still appear with count 0
        assert r["errors_by_service"]["primary"][PRIMARY_1] == 0

    def test_absent_secondary_service_has_zero_count(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {SECONDARY_0} all good",
        ))
        assert r["errors_by_service"]["secondary"][SECONDARY_1] == 0

    def test_no_errors_top_offender_is_none(self):
        r = analyze_lines(_log(
            f"2026-01-01 00:00:00 INFO {PRIMARY_0} ok",
            f"2026-01-01 00:00:00 WARN {SECONDARY_0} slow",
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

    def test_top_offender_highest_count(self):
        lines = [
            f"2026-01-01 00:00:00 ERROR {PRIMARY_0} msg",
            f"2026-01-01 00:00:01 ERROR {PRIMARY_0} msg",
            f"2026-01-01 00:00:02 ERROR {SECONDARY_0} msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == PRIMARY_0

    def test_top_offender_from_other_services(self):
        lines = [
            "2026-01-01 00:00:00 ERROR unknown-svc msg",
            "2026-01-01 00:00:01 ERROR unknown-svc msg",
            f"2026-01-01 00:00:02 ERROR {PRIMARY_0} msg",
        ]
        r = analyze_lines(lines)
        assert r["top_offender"] == "unknown-svc"

    def test_top_offender_tie_broken_alphabetically(self):
        # "aaa-service" and "zzz-service" both have 2 errors → "aaa-service" wins
        lines = [
            "2026-01-01 00:00:00 ERROR aaa-service msg",
            "2026-01-01 00:00:01 ERROR aaa-service msg",
            "2026-01-01 00:00:02 ERROR zzz-service msg",
            "2026-01-01 00:00:03 ERROR zzz-service msg",
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
        assert ebs["primary"]["payment-service"] == 2
        assert ebs["secondary"]["billing-service"] == 2
        assert ebs["other_services"]["notification-service"] == 1
        # billing-service and payment-service both have 2 errors.
        # Tie-break: case-insensitive alphabetical → 'b' < 'p' → billing-service wins.
        assert r["top_offender"] == "billing-service"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration overlap tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigOverlap:
    def test_overlap_raises_at_module_level(self):
        """Importing analyzer with overlapping lists must raise ValueError."""
        import types, importlib
        fake_module = types.ModuleType("_test_overlap_analyzer")
        fake_module.__spec__ = None
        with pytest.raises(ValueError, match="overlap"):
            exec(
                """
PRIMARY_SERVICES = ["svc-a"]
SECONDARY_SERVICES = ["svc-a"]
if set(PRIMARY_SERVICES) & set(SECONDARY_SERVICES):
    raise ValueError("Primary and secondary services must not overlap")
""",
                fake_module.__dict__,
            )

    def test_no_overlap_in_actual_config(self):
        assert set(PRIMARY_SERVICES).isdisjoint(set(SECONDARY_SERVICES))


# ─────────────────────────────────────────────────────────────────────────────
# HTTP endpoint tests (via TestClient)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_fixture():
    from openapi_server.main import app
    return TestClient(app)


class TestHTTPEndpoint:
    VALID_LOG = b"2026-09-18 10:23:45 ERROR payment-service Connection timeout\n"

    def test_valid_upload_returns_200(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        assert resp.status_code == 200

    def test_response_has_required_structure(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        data = resp.json()
        assert "lines_processed" in data
        assert "lines_skipped" in data
        assert "top_offender" in data
        ebs = data["errors_by_service"]
        assert "primary" in ebs
        assert "secondary" in ebs
        assert "other_services" in ebs

    def test_primary_service_error_in_response(self, client_fixture):
        resp = client_fixture.post(
            "/analyze",
            files={"file": ("test.log", io.BytesIO(self.VALID_LOG), "text/plain")},
        )
        data = resp.json()
        assert data["errors_by_service"]["primary"]["payment-service"] == 1

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
