
import re
from datetime import datetime
from collections import Counter
from typing import Iterable


PRIMARY_SERVICES = [
    "payment-service",
    "order-service",
]

SECONDARY_SERVICES = [
    "billing-service",
    "inventory-service",
]

VALID_LEVELS = {
    "ERROR", "INFO", "WARN", "WARNING",
    "DEBUG", "CRITICAL", "FATAL",
}

if len(PRIMARY_SERVICES) != len(set(PRIMARY_SERVICES)):
    raise ValueError("Duplicate service in PRIMARY_SERVICES")

if len(SECONDARY_SERVICES) != len(set(SECONDARY_SERVICES)):
    raise ValueError("Duplicate service in SECONDARY_SERVICES")

if set(PRIMARY_SERVICES) & set(SECONDARY_SERVICES):
    raise ValueError("Primary and secondary services must not overlap")


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


def analyze_lines(lines: Iterable[str]) -> dict:
    """Count ERROR entries and group services into categories."""

    error_counts = Counter()
    seen_services = set()
    lines_processed = 0
    skipped = 0

    for line in lines:
        if not line.strip():
            continue

        parsed = parse_line(line)

        if parsed is None:
            skipped += 1
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

    secondary = {
        service: error_counts[service]
        for service in sorted(SECONDARY_SERVICES)
    }

    known_services = set(PRIMARY_SERVICES) | set(SECONDARY_SERVICES)

    other_services = {
        service: error_counts[service]
        for service in sorted(seen_services - known_services)
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
            "other_services": other_services,
        },
        "top_offender": top_offender,
    }
