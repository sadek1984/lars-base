# src/services/pesticide_prediction_service.py

import logging
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class PesticidePredictionService:
    """
    Production-ready service for pesticide classification predictions using trained ML models
    """
    
    def __init__(self, model_path: str = None):
        self.logger = logging.getLogger(__name__)
        self.classifier = None
        self.model_loaded = False
        self.model_path = model_path or "single_dataset_system/trained_models"
        self.model_version = "1.0.0"
        
        # Pesticide group health risk profiles
        self.group_risk_profiles = {
            'pyrethroid': {'neurotoxicity': 'medium', 'skin_irritation': 'high', 'persistence': 'medium'},
            'organophosphorus': {'neurotoxicity': 'high', 'cholinesterase': 'high', 'persistence': 'low'},
            'chitin_synthesis_inhibitor': {'toxicity': 'low', 'endocrine': 'medium', 'persistence': 'high'},
            'mite_control': {'neurotoxicity': 'medium', 'dermal': 'medium', 'persistence': 'medium'},
            'phenylpyrazole': {'neurotoxicity': 'high', 'bioaccumulation': 'high', 'persistence': 'high'}
        }
        
        # Try to load models (don't fail if not available)
        self._load_models()
        
        # Log the service mode
        if self.model_loaded:
            self.logger.info("✅ PesticidePredictionService initialized with ML models")
        else:
            self.logger.warning("⚠️  PesticidePredictionService initialized with rule-based fallback")
            self.logger.warning(f"   Models not found at: {self.model_path}")
            self.logger.warning(f"   Run 'python train_models.py' to train models")
    


    def _load_models(self):
        """Load trained ML models with backward compatibility"""
        try:
            model_dir = Path(self.model_path)
            
            if not model_dir.exists():
                self.logger.warning(f"Model directory not found: {model_dir}")
                return False
            
            self.logger.info(f"🔄 Loading trained models from: {model_dir}")
            
            from models.PesticideClassificationModel import PesticideClassificationModel
            
            # Initialize classifier
            self.classifier = PesticideClassificationModel(dataset_path="dummy")
            
            import joblib
            
            # Load preprocessing components
            self.classifier.scaler = joblib.load(model_dir / "scaler.pkl")
            
            # Load scaler_no_reading (NEW - with backward compatibility)
            scaler_no_reading_path = model_dir / "scaler_no_reading.pkl"
            if scaler_no_reading_path.exists():
                self.classifier.scaler_no_reading = joblib.load(scaler_no_reading_path)
                self.logger.info("  ✅ Scaler (no reading) loaded")
            else:
                # Fallback: use same scaler (old models)
                self.classifier.scaler_no_reading = self.classifier.scaler
                self.logger.warning("  ⚠️  Using fallback scaler (models need retraining for optimal performance)")
            
            self.classifier.group_label_encoder = joblib.load(model_dir / "group_label_encoder.pkl")
            self.classifier.onehot_encoders = joblib.load(model_dir / "onehot_encoders.pkl")
            
            # Load statistical baseline (NEW - with backward compatibility)
            baseline_path = model_dir / "statistical_baseline.pkl"
            if baseline_path.exists():
                self.classifier.statistical_baseline = joblib.load(baseline_path)
                self.logger.info(f"  ✅ Statistical baseline loaded ({len(self.classifier.statistical_baseline)} combinations)")
            else:
                self.classifier.statistical_baseline = {}
                self.logger.warning("  ⚠️  No statistical baseline found (using ML-only validation)")
            
            self.logger.info("  ✅ Scalers and encoders loaded")
            
            # Load feature imputers (with backward compatibility)
            imputer_path = model_dir / "feature_imputer.pkl"
            if imputer_path.exists():
                self.classifier.feature_imputer = joblib.load(imputer_path)
                self.logger.info("  ✅ Feature imputer loaded")
            
            imputer_no_reading_path = model_dir / "feature_imputer_no_reading.pkl"
            if imputer_no_reading_path.exists():
                self.classifier.feature_imputer_no_reading = joblib.load(imputer_no_reading_path)
                self.logger.info("  ✅ Feature imputer (no reading) loaded")
            else:
                # Fallback to main imputer
                if hasattr(self.classifier, 'feature_imputer'):
                    self.classifier.feature_imputer_no_reading = self.classifier.feature_imputer
            
            # Load sklearn models
            self.classifier.compliance_model = joblib.load(model_dir / "compliance_model.pkl")
            self.logger.info("  ✅ Compliance model loaded (RandomForest)")
            
            self.classifier.concentration_predictor = joblib.load(model_dir / "concentration_predictor.pkl")
            self.logger.info("  ✅ Concentration predictor loaded (GradientBoosting)")
            
            # Check if this is old model (with data leakage) or new model
            if not scaler_no_reading_path.exists():
                self.logger.warning("  ⚠️  OLD MODEL DETECTED - has data leakage in concentration predictor")
                self.logger.warning("  ⚠️  Retrain models for hybrid validation approach")
            else:
                self.logger.info("  ✅ NEW MODEL - TRUE predictor without data leakage")
            
            # Load TensorFlow models
            try:
                import tensorflow as tf
                
                group_model_path = model_dir / "group_classifier.keras"
                if group_model_path.exists():
                    self.classifier.group_classifier = tf.keras.models.load_model(str(group_model_path))
                    self.logger.info("  ✅ Group classifier loaded (Keras NN)")
                else:
                    pkl_path = model_dir / "group_classifier.pkl"
                    if pkl_path.exists():
                        self.classifier.group_classifier = joblib.load(pkl_path)
                        self.logger.info("  ✅ Group classifier loaded (RandomForest)")
                
                risk_model_path = model_dir / "risk_classifier.keras"
                if risk_model_path.exists():
                    self.classifier.risk_classifier = tf.keras.models.load_model(str(risk_model_path))
                    self.logger.info("  ✅ Risk classifier loaded (Keras NN)")
                    
            except Exception as tf_error:
                self.logger.warning(f"  ⚠️  TensorFlow models not loaded: {tf_error}")
            
            self.model_loaded = True
            
            # Final status
            if scaler_no_reading_path.exists() and baseline_path.exists():
                self.logger.info("✅ All models loaded successfully!")
                self.logger.info("🎯 Model 3: TRUE prediction (no reading in features)")
                self.logger.info("📊 Validation: Hybrid (Statistical 3-sigma + ML)")
            else:
                self.logger.info("✅ Models loaded (LEGACY MODE)")
                self.logger.info("⚠️  Using old concentration model with data leakage")
                self.logger.info("💡 Recommendation: Retrain models for optimal performance")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load models: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.model_loaded = False
            return False
        
    def get_model_status(self) -> Dict[str, Any]:
        """Get current model status"""
        if self.classifier and self.model_loaded:
            return {
                "model_loaded": True,
                "model_path": str(self.model_path),
                "components_loaded": {
                    'scaler': hasattr(self.classifier, 'scaler') and self.classifier.scaler is not None,
                    'encoders': hasattr(self.classifier, 'onehot_encoders') and bool(self.classifier.onehot_encoders),
                    'compliance_model': hasattr(self.classifier, 'compliance_model') and self.classifier.compliance_model is not None,
                    'group_classifier': hasattr(self.classifier, 'group_classifier') and self.classifier.group_classifier is not None,
                    'concentration_predictor': hasattr(self.classifier, 'concentration_predictor') and self.classifier.concentration_predictor is not None,
                    'risk_classifier': hasattr(self.classifier, 'risk_classifier') and self.classifier.risk_classifier is not None,
                },
                "timestamp": datetime.now().isoformat(),
                "prediction_mode": "ML Models"
            }
        else:
            return {
                "model_loaded": False,
                "model_path": str(self.model_path),
                "components_loaded": {},
                "timestamp": datetime.now().isoformat(),
                "prediction_mode": "Rule-based (Fallback)"
            }
    
    def predict_sample_compliance(
        self, 
        vegetable: str, 
        pesticide_name: str,
        pesticide_group: str,
        reading: float, 
        limits: float, 
        sample_code: str = None,
        collection_date: str = None  # ⬅️ NEW parameter
    ) -> Dict[str, Any]:
        """
        Predict compliance with season-aware validation
        """
        try:
            # Auto-derive group if not provided
            if not pesticide_group:
                if hasattr(self.classifier, 'classify_pesticide_group'):
                    pesticide_group = self.classifier.classify_pesticide_group(pesticide_name)
                else:
                    pesticide_group = 'other'
            
            # Validate inputs
            validation_result = self._validate_inputs(
                vegetable, pesticide_name, pesticide_group, reading, limits
            )
            
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': validation_result['error'],
                    'timestamp': datetime.now().isoformat()
                }
            
            # Calculate metrics
            exceedance_ratio = reading / limits if limits > 0 else float('inf')
            
            # Try ML prediction with season
            if self.model_loaded and self.classifier:
                self.logger.info(f"🤖 Using ML models for prediction")
                ml_prediction = self._ml_based_prediction(
                    vegetable, pesticide_name, pesticide_group, 
                    reading, limits, exceedance_ratio,
                    collection_date=collection_date  # ⬅️ Pass date
                )
                
                if 'error' not in ml_prediction:
                    ml_prediction['sample_info']['pesticide_name'] = pesticide_name
                    ml_prediction['sample_info']['pesticide_group'] = pesticide_group
                    ml_prediction['sample_info']['collection_date'] = collection_date
                    ml_prediction['sample_info']['sample_code'] = sample_code or f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    ml_prediction['model_version'] = self.model_version
                    ml_prediction['prediction_mode'] = "ML Models"
                    ml_prediction['timestamp'] = datetime.now().isoformat()
                    ml_prediction['success'] = True
                    
                    # Add recommendations
                    ml_prediction['recommendations'] = self._generate_recommendations(
                        ml_prediction, vegetable, pesticide_group, exceedance_ratio
                    )
                    
                    # Check for group mismatch warnings
                    if 'predictions' in ml_prediction and 'group_classification' in ml_prediction['predictions']:
                        group_pred = ml_prediction['predictions']['group_classification']
                        if not group_pred.get('matches_input', True):
                            if 'warnings' not in ml_prediction:
                                ml_prediction['warnings'] = []
                            ml_prediction['warnings'].append(
                                f"⚠️ Group mismatch: Model predicts {group_pred.get('predicted_group')} "
                                f"but input was {pesticide_group}. Verify pesticide identification."
                            )
                    
                    return ml_prediction
                else:
                    self.logger.warning(f"ML prediction failed: {ml_prediction['error']}, falling back to rule-based")
            
            # Fallback to rule-based prediction
            self.logger.info(f"📊 Using rule-based prediction (fallback)")
            return self._rule_based_prediction(
                vegetable, pesticide_name, pesticide_group, 
                reading, limits, exceedance_ratio, sample_code, collection_date
            )
            
        except Exception as e:
            self.logger.error(f"Prediction failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    # Update the key from 'concentration_prediction' to 'reading_validation'
    def _ml_based_prediction(
    self, 
    vegetable: str,
    pesticide_name: str,
    pesticide_group: str, 
    reading: float, 
    limits: float,
    exceedance_ratio: float,
    collection_date: str = None  # ⬅️ NEW parameter
    ) -> Dict[str, Any]:
        """Make prediction using trained ML models with season awareness"""
        try:
            # Use the classifier's prediction method with date
            prediction_result = self.classifier.predict_comprehensive_analysis(
                vegetable=vegetable,
                pesticide_name=pesticide_name,      # ⬅️ Pass specific pesticide
                pesticide_group=pesticide_group,
                reading=reading,
                limits=limits,
                collection_date=collection_date      # ⬅️ Pass date for season
            )
            
            if 'error' in prediction_result:
                return prediction_result
            
            # Format the response
            formatted_result = {
                'sample_info': {
                    'vegetable': vegetable,
                    'pesticide_name': pesticide_name,
                    'pesticide_group': pesticide_group,
                    'reading': reading,
                    'limits': limits,
                    'exceedance_ratio': round(exceedance_ratio, 3),
                    'collection_date': collection_date
                },
                'predictions': {
                    'compliance': prediction_result.get('compliance', {}),
                    'group_classification': prediction_result.get('pesticide_group_classification', {}),
                    'reading_validation': prediction_result.get('reading_validation', {}),
                    'risk': prediction_result.get('risk_classification', {})
                },
                'model_summary': prediction_result.get('model_summary', {}),
                'risk_assessment': {
                    'risk_level': prediction_result.get('risk_classification', {}).get('predicted_risk_level', 'Unknown'),
                    'risk_description': self._get_risk_description(exceedance_ratio),
                    'exceedance_factor': round(exceedance_ratio, 2),
                    'pesticide_group_risk': self.group_risk_profiles.get(pesticide_group, {})
                }
            }
            
            return formatted_result
            
        except Exception as e:
            self.logger.error(f"ML prediction error: {e}")
            return {'error': str(e)}

    
    def _rule_based_prediction(
    self,
    vegetable: str,
    pesticide_name: str,
    pesticide_group: str,
    reading: float,
    limits: float,
    exceedance_ratio: float,
    sample_code: str = None,
    collection_date: str = None  # ⬅️ NEW parameter
) -> Dict[str, Any]:
        """Fallback rule-based prediction"""
        
        is_compliant = reading <= limits
        compliance_probability = max(0.0, min(1.0, 1.0 - (exceedance_ratio - 1.0)))
        
        result = {
            "success": True,
            "sample_info": {
                "sample_code": sample_code or f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "vegetable": vegetable,
                "pesticide_name": pesticide_name,
                "pesticide_group": pesticide_group,
                "reading": reading,
                "limits": limits,
                "exceedance_ratio": round(exceedance_ratio, 3),
                "collection_date": collection_date
            },
            "predictions": {
                "compliance": {
                    "prediction": "Compliant" if is_compliant else "Non-Compliant",
                    "probability_compliant": round(compliance_probability, 3),
                    "confidence": 0.70
                }
            },
            "risk_assessment": {
                'risk_level': self._calculate_risk_level(exceedance_ratio),
                'risk_description': self._get_risk_description(exceedance_ratio),
                'exceedance_factor': round(exceedance_ratio, 2),
                'pesticide_group_risk': self.group_risk_profiles.get(pesticide_group, {})
            },
            "recommendations": self._generate_recommendations_simple(
                is_compliant, exceedance_ratio, vegetable, pesticide_group
            ),
            "timestamp": datetime.now().isoformat(),
            "model_version": self.model_version,
            "prediction_mode": "Rule-based (Fallback)"
        }
        
        return result
        
    def _calculate_risk_level(self, exceedance_ratio: float) -> str:
        """Calculate risk level from exceedance ratio"""
        if exceedance_ratio <= 1.0:
            return 'Low'
        elif exceedance_ratio <= 2.0:
            return 'Medium'
        elif exceedance_ratio <= 5.0:
            return 'High'
        else:
            return 'Critical'
    
    def _get_risk_description(self, exceedance_ratio: float) -> str:
        """Get risk description"""
        risk_level = self._calculate_risk_level(exceedance_ratio)
        descriptions = {
            'Low': 'Within acceptable limits',
            'Medium': 'Slightly above limits',
            'High': 'Significantly above limits',
            'Critical': 'Critically above limits'
        }
        return descriptions.get(risk_level, 'Unknown risk level')
    
    def _generate_recommendations(
        self, 
        ml_prediction: Dict, 
        vegetable: str, 
        pesticide_group: str,
        exceedance_ratio: float
    ) -> List[str]:
        """Generate recommendations based on ML predictions"""
        
        if hasattr(self.classifier, 'generate_recommendations'):
            return self.classifier.generate_recommendations(
                ml_prediction, vegetable, pesticide_group
            )
        else:
            return self._generate_recommendations_simple(
                ml_prediction['predictions'].get('compliance', {}).get('prediction') == 'Compliant',
                exceedance_ratio,
                vegetable,
                pesticide_group
            )
    
    def _generate_recommendations_simple(
        self, 
        is_compliant: bool, 
        exceedance_ratio: float, 
        vegetable: str, 
        pesticide_group: str
    ) -> List[str]:
        """Generate simple rule-based recommendations"""
        
        recommendations = []
        
        if not is_compliant:
            recommendations.append("Sample does not meet compliance standards")
            recommendations.append("Consider retesting or investigating source")
        
        if exceedance_ratio > 5.0:
            recommendations.append("Critical contamination level - investigate source immediately")
            recommendations.append("Implement enhanced cleaning protocols")
        elif exceedance_ratio > 2.0:
            recommendations.append("Elevated pesticide levels detected - monitor closely")
        
        if 'pepper' in vegetable.lower():
            recommendations.append("Peppers show high contamination rates - enhance washing protocols")
        elif any(term in vegetable.lower() for term in ['lettuce', 'spinach', 'leafy']):
            recommendations.append("Leafy greens require special attention - difficult to decontaminate")
        
        if pesticide_group in self.group_risk_profiles:
            group_risks = self.group_risk_profiles[pesticide_group]
            for risk_type, level in group_risks.items():
                if level == 'high':
                    recommendations.append(f"Monitor for {risk_type} effects due to {pesticide_group} exposure")
        
        return recommendations if recommendations else ["Sample appears normal - continue regular monitoring"]
    
    # src/services/pesticide_prediction_service.py

    def predict_batch_samples(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Predict compliance for multiple samples with season awareness
        """
        try:
            results = []
            successful = 0
            failed = 0
            failures = []
            
            for i, sample in enumerate(samples):
                result = self.predict_sample_compliance(
                    vegetable=sample.get('vegetable'),
                    pesticide_name=sample.get('pesticide_name'),
                    pesticide_group=sample.get('pesticide_group'),
                    reading=sample.get('reading'),
                    limits=sample.get('limits'),
                    sample_code=sample.get('sample_code'),
                    collection_date=sample.get('collection_date')  # ⬅️ Pass date
                )
                
                results.append(result)
                
                if result.get('success'):
                    successful += 1
                else:
                    failed += 1
                    failures.append({'index': i, 'error': result.get('error')})
            
            return {
                "success": True,
                "total_samples": len(samples),
                "successful_predictions": successful,
                "failed_predictions": failed,
                "results": results,
                "failures": failures,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Batch prediction failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _validate_inputs(
        self, 
        vegetable: str, 
        pesticide_name: str,        # ⬅️ Add this parameter
        pesticide_group: str, 
        reading: float, 
        limits: float
    ) -> Dict[str, Any]:
        """Validate input parameters"""
        
        if not vegetable or not isinstance(vegetable, str):
            return {'valid': False, 'error': 'Invalid vegetable parameter'}
        
        # Validate pesticide name
        if not pesticide_name or not isinstance(pesticide_name, str):
            return {'valid': False, 'error': 'Invalid pesticide_name parameter'}
        
        if not pesticide_group or not isinstance(pesticide_group, str):
            return {'valid': False, 'error': 'Invalid pesticide_group parameter'}
        
        try:
            reading = float(reading)
            limits = float(limits)
        except (ValueError, TypeError):
            return {'valid': False, 'error': 'Reading and limits must be numeric'}
        
        if reading < 0 or limits <= 0:
            return {'valid': False, 'error': 'Reading must be non-negative and limits must be positive'}
        
        return {'valid': True}
    
    @staticmethod
    def train_and_save_models(dataset_path: str, output_dir: str = "single_dataset_system"):
        """
        Static method to train models (can be called at startup)
        Similar to load_and_train_models() in time_series
        """
        try:
            logger.info("=" * 80)
            logger.info("🚀 STARTING PESTICIDE CLASSIFICATION MODEL TRAINING")
            logger.info("=" * 80)
            
            dataset_path = Path(dataset_path)
            
            if not dataset_path.exists():
                logger.error(f"❌ Dataset not found: {dataset_path}")
                # Try common locations
                possible_paths = [
                    "/app/data/dataset.xlsx",
                    "/app/src/data/dataset.xlsx",
                    "src/data/dataset.xlsx",
                    "data/dataset.xlsx"
                ]
                
                for path in possible_paths:
                    if Path(path).exists():
                        logger.info(f"✅ Found dataset at: {path}")
                        dataset_path = Path(path)
                        break
                else:
                    logger.error("❌ Could not find dataset in any common location")
                    return False
            
            logger.info(f"📁 Using dataset: {dataset_path}")
            
            # Import here to avoid circular imports
            from models.PesticideClassificationModel import SingleDatasetClassificationSystem
            
            # Initialize training system
            logger.info("🔧 Initializing training system...")
            system = SingleDatasetClassificationSystem(str(dataset_path))
            
            # Run training
            logger.info("🚀 Starting model training...")
            result = system.run_complete_training(verbose_training=False)
            
            if result:
                training_results, patterns = result
                
                # Save models
                logger.info("💾 Saving trained models...")
                system.save_system(output_dir=output_dir)
                
                logger.info("=" * 80)
                logger.info("✅ SUCCESS! Models trained and saved!")
                logger.info("=" * 80)
                logger.info(f"📊 Training Summary:")
                logger.info(f"   • Total samples: {len(training_results['processed_data']):,}")
                logger.info(f"   • Validation accuracy: {training_results['validation_results'].get('compliance_accuracy', 0):.2%}")
                logger.info(f"   • Test accuracy: {training_results['test_results'].get('compliance_accuracy', 0):.2%}")
                logger.info(f"📂 Models saved to: {output_dir}/trained_models/")
                
                return True
            else:
                logger.error("❌ Training failed!")
                return False
                
        except Exception as e:
            logger.error(f"❌ ERROR during training: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False