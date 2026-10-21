import sys
from pathlib import Path

from fastapi import HTTPException, UploadFile
from openapi_server.apis.analyze_api_base import BaseAnalyzeApi
from openapi_server.models.analysis_result import AnalysisResult

# Find the app folder
app_path = Path(__file__).resolve().parents[4] / "app"

# Add the app folder so Python can find analyzer.py
if str(app_path) not in sys.path:
    sys.path.insert(0, str(app_path))


# pyrefly: ignore[missing-import]
from analyzer import analyze_lines


class AnalyzeService(BaseAnalyzeApi):

    async def analyze(self, file: UploadFile) -> AnalysisResult:

        # Read the uploaded file
        content = await file.read()

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
