import os
import sys
from pathlib import Path

# Resolve app/analyzer.py.
# Structure: genyal/generated/src/openapi_server/impl/analyze_service.py
#   parents[0] = impl
#   parents[1] = openapi_server
#   parents[2] = src
#   parents[3] = generated
#   parents[4] = genyal   <-- app/ lives here
# An ANALYZER_DIR env var overrides this for Docker or custom setups.
_ANALYZER_DIR_ENV = os.environ.get("ANALYZER_DIR", "")
if _ANALYZER_DIR_ENV:
    _APP_DIR = Path(_ANALYZER_DIR_ENV)
else:
    _APP_DIR = Path(__file__).resolve().parents[4] / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from fastapi import HTTPException, UploadFile
from openapi_server.apis.analyze_api_base import BaseAnalyzeApi
from openapi_server.models.analysis_result import AnalysisResult

# Import the shared analyzer (app/analyzer.py).
# PRIMARY_SERVICES and SECONDARY_SERVICES are defined there.
# pyrefly: ignore [missing-import]
from analyzer import analyze_lines  # noqa: E402


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
