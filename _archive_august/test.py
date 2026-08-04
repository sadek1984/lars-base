# test_imports.py
import sys
import os
from pathlib import Path

def test_imports():
    """Test all the imports that were failing"""
    
    print("Testing imports...")
    
    # Test 1: Check directories exist
    dirs_to_check = ['services', 'models', 'routes']
    for dir_name in dirs_to_check:
        if Path(dir_name).exists():
            print(f"✅ Directory {dir_name}/ exists")
        else:
            print(f"❌ Directory {dir_name}/ missing")
    
    # Test 2: Check files exist
    files_to_check = [
        'services/__init__.py',
        'services/pesticide_prediction_service.py',
        'models/__init__.py',
        'models/pesticide_prediction_models.py',
        'routes/__init__.py',
        'routes/prediction.py'
    ]
    
    for file_path in files_to_check:
        if Path(file_path).exists():
            print(f"✅ File {file_path} exists")
        else:
            print(f"❌ File {file_path} missing")
    
    # Test 3: Try imports
    try:
        from services.pesticide_prediction_service import PesticidePredictionService
        print("✅ PesticidePredictionService imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import PesticidePredictionService: {e}")
    
    try:
        from models.pesticide_prediction_models import (
            PesticideSampleInput, 
            BatchPredictionInput,
            PredictionResult,
            BatchPredictionResult,
            ModelStatus
        )
        print("✅ Pesticide models imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import pesticide models: {e}")
    
    try:
        from routes.prediction import prediction_router
        print("✅ Prediction router imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import prediction router: {e}")
    
    # Test 4: Test service initialization
    try:
        service = PesticidePredictionService()
        status = service.get_model_status()
        print(f"✅ Service initialization successful: {status['model_loaded']}")
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")

if __name__ == "__main__":
    test_imports()