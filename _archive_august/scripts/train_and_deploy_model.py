# src/scripts/train_and_deploy_model.py
"""
Script to train the pesticide classification model and prepare it for deployment
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))
from models import PesticideClassificationModel
from models.PesticideClassificationModel import SingleDatasetClassificationSystem

def train_and_save_model(dataset_path: str, output_dir: str = "trained_models"):
    """
    Train the pesticide classification model and save for deployment
    
    Args:
        dataset_path: Path to your Excel dataset
        output_dir: Directory to save trained models
    """
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the classification system
        logger.info("Initializing classification system...")
        system = PesticideClassificationModel(dataset_path)
        
        system = SingleDatasetClassificationSystem(dataset_path="/Users/a12/mini-rag/src/data/dataset.xlsx")


        # Train the models
        logger.info("Starting model training...")
        result = system.run_complete_training(verbose_training=True)

    
        if not result:
            logger.error("Model training failed!")
            return False
        
        training_results, patterns = result
        
        # Save the trained system
        logger.info(f"Saving trained models to {output_dir}...")
        system.save_system(output_dir)
        
        # Test the prediction system
        logger.info("Testing prediction system...")
        system.test_prediction_system()
        
        logger.info("Model training and deployment setup completed successfully!")
        
        # Print summary
        print("\n" + "="*60)
        print("MODEL TRAINING SUMMARY")
        print("="*60)
        print(f"✅ Models trained and saved to: {output_dir}")
        print(f"✅ Total samples processed: {len(training_results['processed_data'])}")
        
        if 'validation_results' in training_results:
            print("✅ Validation Results:")
            for metric, value in training_results['validation_results'].items():
                print(f"   - {metric}: {value:.4f}")
        
        if 'test_results' in training_results:
            print("✅ Test Results:")
            for metric, value in training_results['test_results'].items():
                print(f"   - {metric}: {value:.4f}")
        
        print(f"✅ Ready for deployment!")
        print("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main training script"""
    
    # Update this path to your dataset
    dataset_path = "/Users/a12/mini-rag/src/data/dataset.xlsx"  # CHANGE THIS
    output_dir = "single_dataset_system"
    
    if not Path(dataset_path).exists():
        print(f"Dataset not found: {dataset_path}")
        print("Please update the dataset_path variable in this script")
        return
    
    success = train_and_save_model(dataset_path, output_dir)
    
    if success:
        print("\n🎉 Model training completed successfully!")
        print(f"Models saved to: {output_dir}")
        print("You can now start the FastAPI server with the prediction endpoints")
    else:
        print("\n❌ Model training failed. Check the logs above.")

if __name__ == "__main__":
    main()