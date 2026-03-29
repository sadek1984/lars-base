import sys
import os
from pathlib import Path

# Add project root to sys.path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.LARS.modules.risk_assessment_service import calculate_commodity_summary_metrics
from src.helper.risk_assessment_config import RiskAssessmentConfig

def test_cypermethrin_calculation():
    print("--- Testing Cypermethrin Risk Calculation ---")
    
    # Test data: Cypermethrin in Tomato with Median 0.0550
    residues = [
        {"name": "cypermethrin", "concentration": 0.0550}
    ]
    
    # Run calculation
    # Default for Saudi Adult: BW=53.0, IR for Tomato=0.045
    result = calculate_commodity_summary_metrics(
        residues,
        commodity="Tomato",
        target="adult"
    )
    
    hi_total = result["hi_total"]
    print(f"Calculated HIc: {hi_total:.5f}")
    
    # Expected:
    # IR = 0.045
    # BW = 53.0
    # C = 0.055
    # EDI = (0.055 * 0.045) / 53.0 = 0.000046698...
    # ADI (Cypermethrin) = 0.005
    # HQ = 0.000046698 / 0.005 = 0.0093396... approx 0.00934
    
    expected_hi = 0.0093396
    
    if abs(hi_total - expected_hi) < 1e-6:
        print("✅ SUCCESS: Cypermethrin HQ matches expected result (0.00934)")
    else:
        print(f"❌ FAILURE: Calculated {hi_total:.5f}, expected {expected_hi:.5f}")

if __name__ == "__main__":
    try:
        test_cypermethrin_calculation()
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()
