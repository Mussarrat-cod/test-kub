
from fastapi import HTTPException, UploadFile
from openapi_server.apis.analyze_api_base import BaseAnalyzeApi
from openapi_server.models.analysis_result import AnalysisResult


def analyze_lines(lines):
    errors_by_service = {}
    lines_processed = 0
    lines_skipped = 0

    for line in lines:
        if not line.strip():
            continue

        parts = line.strip().split(maxsplit=4)

        if len(parts) < 4:
            lines_skipped += 1
            continue

        _, _, level, service = parts[:4]
        lines_processed += 1

        if service not in errors_by_service:
            errors_by_service[service] = 0

        if level.upper() == "ERROR":
            errors_by_service[service] += 1

    errors_by_service = dict(
        sorted(errors_by_service.items(), key=lambda item: (-item[1], item[0]))
    )

    top_offender = next(
        (service for service, count in errors_by_service.items() if count > 0),
        None,
    )

    return {
        "lines_processed": lines_processed,
        "lines_skipped": lines_skipped,
        "errors_by_service": errors_by_service,
        "top_offender": top_offender,
    }


class AnalyzeService(BaseAnalyzeApi):
    async def analyze(self, file: UploadFile) -> AnalysisResult:
        content = await file.read()

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="File is not valid UTF-8 text",
            )

        result = analyze_lines(text.splitlines())
        return AnalysisResult(**result)
