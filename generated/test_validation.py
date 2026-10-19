import sys
from pathlib import Path
from pydantic import ValidationError

# Ensure src is on Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openapi_server.models.analysis_result import AnalysisResult
from openapi_server.models.health_response import HealthResponse


def test_strict_validation():
    print("=" * 60)
    print("RUNNING STRICT JSON VALIDATION TESTS")
    print("=" * 60)

    # -------------------------------------------------------------
    # 1. VALID TEST: All required fields present, no extra fields
    # -------------------------------------------------------------
    print("\n[TEST 1] Testing valid JSON payload...")
    valid_data = {
        "lines_processed": 5,
        "lines_skipped": 0,
        "errors_by_service": {"payment-service": 2, "billing-service": 1},
        "top_offender": "payment-service",
    }
    result = AnalysisResult.model_validate(valid_data)
    print("  [PASS] Valid payload accepted:")
    print("         ", result.to_dict())

    # -------------------------------------------------------------
    # 2. EXTRA VARIABLE TEST: Should fail with extra_forbidden
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing payload with an EXTRA variable ('unwanted_var')...")
    data_with_extra = {
        **valid_data,
        "unwanted_var": "I should not be here!",
    }
    try:
        AnalysisResult.model_validate(data_with_extra)
        print("  [FAIL] Extra variable was unexpectedly allowed!")
    except ValidationError as e:
        print("  [PASS] Extra variable was blocked with validation error:")
        for err in e.errors():
            print(f"         Field: '{err['loc'][0]}' -> {err['msg']} (type: {err['type']})")

    # -------------------------------------------------------------
    # 3. MISSING VARIABLE TEST: Should fail with missing
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing payload with a MISSING variable (missing 'top_offender')...")
    data_with_missing = {
        "lines_processed": 5,
        "lines_skipped": 0,
        "errors_by_service": {"payment-service": 2},
        # 'top_offender' omitted
    }
    try:
        AnalysisResult.model_validate(data_with_missing)
        print("  [FAIL] Missing variable was unexpectedly allowed!")
    except ValidationError as e:
        print("  [PASS] Missing variable was blocked with validation error:")
        for err in e.errors():
            print(f"         Field: '{err['loc'][0]}' -> {err['msg']} (type: {err['type']})")

    # -------------------------------------------------------------
    # 4. HEALTH RESPONSE EXTRA VARIABLE TEST
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing HealthResponse with an EXTRA variable...")
    try:
        HealthResponse.model_validate({"status": "ok", "extra_metric": 42})
        print("  [FAIL] Extra variable in HealthResponse was unexpectedly allowed!")
    except ValidationError as e:
        print("  [PASS] Extra variable in HealthResponse was blocked:")
        for err in e.errors():
            print(f"         Field: '{err['loc'][0]}' -> {err['msg']} (type: {err['type']})")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    test_strict_validation()
