
import re
from datetime import datetime
from collections import Counter
from typing import Iterable


PRIMARY_SERVICES = [
    "payment-service",
    "order-service",
]

VALID_LEVELS = {
    "ERROR", "INFO", "WARN", "WARNING",
    "DEBUG", "CRITICAL", "FATAL",
}

if len(PRIMARY_SERVICES) != len(set(PRIMARY_SERVICES)):
    raise ValueError("Duplicate service in PRIMARY_SERVICES")



LOG_PATTERN = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+"
    r"(\d{2}:\d{2}:\d{2})\s+"
    r"(\S+)\s+"
    r"(\S+)"
    r"(?:\s+(.*))?\s*$"
)


def parse_line(line: str):
    """Parse a log line, allowing levels such as ERROR and **ERROR**."""

    match = LOG_PATTERN.fullmatch(line)

    if not match:
        return None

    date, time, raw_level, service, message = match.groups()

    # Validate that the date and time are real values.
    try:
        datetime.strptime(
            f"{date} {time}", "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return None

    # Normalize **ERROR**, error, and ERROR to ERROR.
    level = raw_level.strip("*").upper()

    if level not in VALID_LEVELS:
        return None

    return date, time, level, service, message or ""


def diagnose_line(line: str) -> str:
    """Diagnose why a line failed parsing (identifying missing fields, extra fields, or invalid values)."""
    parts = line.strip().split()
    if not parts:
        return "Empty line"

    # 1. Date
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
        return f"Missing or invalid date field (got '{parts[0]}', expected 'YYYY-MM-DD')"

    if len(parts) == 1:
        return "Missing fields: time, level, and service"

    # 2. Time
    if not re.match(r"^\d{2}:\d{2}:\d{2}$", parts[1]):
        return f"Missing or invalid time field (got '{parts[1]}', expected 'HH:MM:SS')"

    try:
        datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        return f"Invalid calendar date/time '{parts[0]} {parts[1]}': {e}"

    if len(parts) == 2:
        return "Missing fields: log level and service"

    # 3. Level
    raw_level = parts[2].strip("*").upper()
    if raw_level not in VALID_LEVELS:
        return f"Invalid log level '{parts[2]}' (valid: {', '.join(sorted(VALID_LEVELS))})"

    if len(parts) == 3:
        return "Missing field: service name"

    # If it matched the 4 required parts but failed regex
    match = LOG_PATTERN.fullmatch(line)
    if not match:
        return "Malformed line structure / unrecognized tokens"

    return "Unknown parsing failure"


def analyze_lines(lines: Iterable[str]) -> dict:
    """Count ERROR entries and group services into categories."""

    error_counts = Counter()
    seen_services = set()
    lines_processed = 0
    skipped = 0
    line_errors = []

    for line_idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        parsed = parse_line(line)

        if parsed is None:
            skipped += 1
            reason = diagnose_line(line)
            line_errors.append({
                "line": line_idx,
                "content": line.strip()[:120],
                "error": reason,
            })
            continue

        _, _, level, service, _ = parsed

        lines_processed += 1
        seen_services.add(service)

        if level == "ERROR":
            error_counts[service] += 1

    primary = {
        service: error_counts[service]
        for service in sorted(PRIMARY_SERVICES)
    }

    primary_set = set(PRIMARY_SERVICES)
    secondary = {
        service: error_counts[service]
        for service in sorted(seen_services - primary_set)
    }

    # Highest count wins; alphabetical order breaks ties.
    offenders = [
        service
        for service, count in error_counts.items()
        if count > 0
    ]

    top_offender = (
        min(
            offenders,
            key=lambda service: (
                -error_counts[service],
                service.casefold(),
                service,
            ),
        )
        if offenders
        else None
    )

    return {
        "lines_processed": lines_processed,
        "lines_skipped": skipped,
        "errors_by_service": {
            "primary": primary,
            "secondary": secondary,
        },
        "top_offender": top_offender,
        "skipped_details": line_errors if skipped > 0 else None,
    }

