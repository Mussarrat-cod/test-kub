import sys
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from openapi_server.apis.analyze_api_base import BaseAnalyzeApi
from openapi_server.models.analysis_result import AnalysisResult

import os

# Find the app folder (support Docker ANALYZER_DIR env var or local relative path)
_analyzer_env = os.environ.get("ANALYZER_DIR", "")
if _analyzer_env:
    app_path = Path(_analyzer_env)
else:
    app_path = Path(__file__).resolve().parents[4] / "app"

# Add the app folder so Python can find analyzer.py
if str(app_path) not in sys.path:
    sys.path.insert(0, str(app_path))


# pyrefly: ignore[missing-import]
from analyzer import analyze_lines


class AnalyzeService(BaseAnalyzeApi):

    def analyze(self, file: UploadFile) -> AnalysisResult:

        # Read the uploaded file synchronously
        content = file.file.read()

        # Convert the file content into text
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="File is not valid UTF-8 text"
            )

        # Split the text into lines and analyze them
        lines = text.splitlines()
        result = analyze_lines(lines)

        # Return the analysis result (including skipped_details if any)
        return AnalysisResult(**result)


router = APIRouter()


@router.post(
    "/analyze",
    responses={
        200: {"model": AnalysisResult, "description": "Analysis result"},
        400: {"description": "File is not valid UTF-8 text"},
        422: {"description": "Validation error (malformed lines skipped or invalid file field)"},
    },
    tags=["Analyze"],
    summary="Analyze a log file",
    response_model_by_alias=True,
)
def analyze(
    file: UploadFile = File(..., description="A .log / .txt file", alias="file"),
) -> AnalysisResult:
    """Upload a log file (multipart/form-data) and get ERROR counts per service."""
    service = AnalyzeService()
    return service.analyze(file)
