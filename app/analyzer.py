"""Part 1 - The analyzer.

Pure Python, no web code. Takes log lines, returns ERROR counts per service.
Keeping this separate from the server means you can unit-test it on its own.

Line format:  DATE TIME LEVEL service-name message...
Example:      2026-09-18 10:23:45 ERROR payment-service Connection timeout
"""

from collections import Counter
from typing import Iterable


def parse_line(line: str):
    """Split one log line into its parts.

    maxsplit=4 gives exactly 5 pieces: date, time, level, service, message.
    The message may contain spaces, so we stop splitting after 4 cuts.
    Returns None for blank/malformed lines instead of crashing.
    """
    parts = line.strip().split(maxsplit=4)
    if len(parts) < 4:  # message is optional, the first 4 fields are required
        return None
    date, time, level, service = parts[:4]
    message = parts[4] if len(parts) == 5 else ""
    return date, time, level, service, message


def analyze_lines(lines: Iterable[str]) -> dict:
    """Count ERROR lines per service.

    Every service seen in the file is included (even with 0 errors),
    which is why auth-service shows 0 in the example output.
    """
    error_counts: Counter = Counter()
    seen_services: set = set()
    lines_processed = 0
    skipped = 0

    for line in lines:
        if not line.strip():  # ignore blank lines completely
            continue
        parsed = parse_line(line)
        if parsed is None:
            skipped += 1
            continue

        _, _, level, service, _ = parsed
        lines_processed += 1
        seen_services.add(service)
        if level.upper() == "ERROR":
            error_counts[service] += 1

    # Build the result: errors per service, highest first.
    # Sorting by (-count, name) makes ties deterministic (alphabetical).
    ordered = sorted(seen_services, key=lambda s: (-error_counts[s], s))
    errors_by_service = {s: error_counts[s] for s in ordered}

    # Top offender = service with the most errors. None if there were no errors.
    top_offender = ordered[0] if ordered and error_counts[ordered[0]] > 0 else None

    return {
        "lines_processed": lines_processed,
        "lines_skipped": skipped,
        "errors_by_service": errors_by_service,
        "top_offender": top_offender,
    }
