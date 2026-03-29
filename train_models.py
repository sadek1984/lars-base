# train_models.py
"""
Script to train and save all pesticide classification models
Run this before starting the API server
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from models.PesticideClassificationModel import SingleDatasetClassificationSystem

def main():
    """Train and save all models"""
    
    print("=" * 70)
    print("PESTICIDE CLASSIFICATION MODEL TRAINING")
    print("=" * 70)
    
    # Update this path to your actual dataset location
    dataset_path = "src/data/dataset.xlsx"
    
    # Check if dataset exists
    if not Path(dataset_path).exists():
        print(f"❌ ERROR: Dataset not found at: {dataset_path}")
        print("\n📝 Please update the dataset_path in train_models.py")
        
        # Try to find the dataset in common locations
        possible_paths = [
            "data/dataset.xlsx",
            "src/data/dataset.xlsx",
            "/app/data/dataset.xlsx",
            "./dataset.xlsx"
        ]
        
        print("\n🔍 Looking for dataset in common locations...")
        for path in possible_paths:
            if Path(path).exists():
                print(f"✅ Found dataset at: {path}")
                dataset_path = path
                break
        else:
            print("\n❌ Could not find dataset automatically.")
            print("Please provide the correct path:")
            dataset_path = input("Dataset path: ").strip()
            
            if not Path(dataset_path).exists():
                print(f"❌ File not found: {dataset_path}")
                return False
    
    print(f"\n📁 Using dataset: {dataset_path}")
    
    try:
        # Initialize the training system
        print("\n🔧 Initializing training system...")
        system = SingleDatasetClassificationSystem(dataset_path)
        
        # Run training
        print("\n🚀 Starting model training...\n")
        result = system.run_complete_training(verbose_training=False)
        
        if result:
            training_results, patterns = result
            
            # Save the trained system
            print("\n💾 Saving trained models...")
            system.save_system(output_dir="single_dataset_system")
            
            print("\n" + "=" * 70)
            print("✅ SUCCESS! Models trained and saved successfully!")
            print("=" * 70)
            print(f"\n📊 Training Summary:")
            print(f"   • Total samples: {len(training_results['processed_data']):,}")
            print(f"   • Validation accuracy: {training_results['validation_results'].get('compliance_accuracy', 0):.2%}")
            print(f"   • Test accuracy: {training_results['test_results'].get('compliance_accuracy', 0):.2%}")
            print(f"\n📂 Models saved to: single_dataset_system/trained_models/")
            print(f"\n🎯 Next step: Start your API server")
            print(f"   Run: uvicorn main:app --reload")
            
            return True
        else:
            print("\n❌ Training failed!")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR during training: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)