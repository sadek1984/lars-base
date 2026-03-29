
import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow import keras
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.metrics import classification_report, confusion_matrix, mean_squared_error, accuracy_score
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime

class PesticideClassificationModel:
    """
    Single dataset pesticide classification system with comprehensive ML models
    Adapted from the working multi-file system for consolidated dataset processing
    """
    
    def __init__(self, dataset_path: str = None):
        # Encoders and scalers
        self.scaler = StandardScaler()
        self.group_label_encoder = LabelEncoder()
        
        # Models
        self.compliance_model = None
        self.group_classifier = None
        self.concentration_predictor = None
        self.risk_classifier = None
        
        # Feature encoders (will be populated during training)
        self.onehot_encoders = {}
        self.feature_imputer = None

        self.statistical_baseline = {}
        self.control_limits = {}
        
        # Arabic to English vegetable mapping (from your working code)
        self.vegetable_mapping = {
            'طماطم': 'tomato', 'خيار': 'cucumber', 'فلفل أخضر بارد': 'green_bell_pepper',
            'فلفل احمر بارد': 'red_bell_pepper', 'فلفل حار احمر': 'red_hot_pepper',
            'فلفل أحمر حار': 'red_hot_pepper', 'فلفل حار أحمر': 'red_hot_pepper',
            'فلفل أخضر حار': 'green_hot_pepper', 'فلفل حار اخضر': 'green_hot_pepper',
            'فلفل اخضر حار': 'green_hot_pepper', 'فلفل حار أخضر': 'green_hot_pepper',
            'فلفل بارد': 'bell_pepper', 'فلفل بارد اخضر': 'green_bell_pepper',
            'فلفل اخضر بارد': 'green_bell_pepper', 'فلفل بارد أخضر': 'green_bell_pepper',
            'فلفل بارداخضر': 'green_bell_pepper', 'فلفل بارد احمر': 'red_bell_pepper',
            'فلفل أحمر بارد': 'red_bell_pepper', 'فلفل ملون بارد': 'mixed_bell_pepper',
            'فلفل ملون': 'mixed_bell_pepper', 'فلفل بارد ملون': 'mixed_bell_pepper',
            'كوسة': 'zucchini', 'فاصوليا': 'beans', 'فاصووليا': 'beans',
            'باذنجان': 'eggplant', 'خس': 'lettuce', 'فراولة': 'strawberry',
            'ملفوف': 'cabbage', 'باميا': 'okra', 'بقدونس': 'parsley',
            'تين': 'fig', 'رمان': 'pomegranate', 'قرع': 'pumpkin',
            'قرع نجدى': 'najdi_pumpkin', 'قرع امريكى': 'american_pumpkin',
            'برتقال': 'orange', 'ليمون': 'lemon', 'الوبا': 'jujube',
            'فروت': 'grapefruit', 'قثة': 'armenian_cucumber', 'جبا': 'juba_fruit',
            'نعناع': 'mint', 'جرجير': 'arugula', 'شمام': 'cantaloupe',
            'سبانخ': 'spinach'
        }
        
        # Pesticide group health risk profiles
        self.group_risk_profiles = {
            'pyrethroid': {'neurotoxicity': 'medium', 'skin_irritation': 'high', 'persistence': 'medium'},
            'organophosphorus': {'neurotoxicity': 'high', 'cholinesterase': 'high', 'persistence': 'low'},
            'chitin_synthesis_inhibitor': {'toxicity': 'low', 'endocrine': 'medium', 'persistence': 'high'},
            'mite_control': {'neurotoxicity': 'medium', 'dermal': 'medium', 'persistence': 'medium'},
            'phenylpyrazole': {'neurotoxicity': 'high', 'bioaccumulation': 'high', 'persistence': 'high'}
        }
    
    def classify_pesticide_group(self, pesticide):
        """Complete pesticide classification (from your working code)"""
        if not pesticide or pesticide == 'لا يوجد' or pesticide == '':
            return 'none'
        
        pesticide_lower = str(pesticide).lower().strip()
        
        # 1. PYRETHROID GROUP
        pyrethroid_compounds = [
            'bifenthrin', 'bifnthrin', 'bifenthein', 'deltamethrin', 'fenpropathrin', 
            'cyhalothrin', 'lampda-cyhalothrin', 'lampda- cyhalothrin', 'lambda_cyhalothrin',
            'cypermethrin', 'permethrin', 'alpha-cypermethrin'
        ]
        if any(compound in pesticide_lower for compound in pyrethroid_compounds):
            return 'pyrethroid'
        
        # 2. ORGANOPHOSPHORUS GROUP
        organophosphorus_compounds = [
            'quinalphos', 'profenofos', 'diazinone', 'diazinon',
            'malathion', 'chlorpyrifos', 'dimethoate', 'parathion'
        ]
        if any(compound in pesticide_lower for compound in organophosphorus_compounds):
            return 'organophosphorus'
        
        # 3. CHITIN SYNTHESIS INHIBITOR GROUP
        chitin_inhibitor_compounds = ['buprofezin', 'buprifezin', 'diflubenzuron', 'teflubenzuron']
        if any(compound in pesticide_lower for compound in chitin_inhibitor_compounds):
            return 'chitin_synthesis_inhibitor'
        
        # 4. MITE CONTROL GROUP
        mite_control_compounds = [
            'pyridaben', 'pyridben', 'pyridabien', 'ptridaben',
            'bifenazate', 'bifenzate', 'bifanazate', 'fenpyroximate', 'tebufenpyrad'
        ]
        if any(compound in pesticide_lower for compound in mite_control_compounds):
            return 'mite_control'
        
        # 5. PHENYLPYRAZOLE GROUP
        phenylpyrazole_compounds = ['fipronil', 'chlorfenapyr']
        if any(compound in pesticide_lower for compound in phenylpyrazole_compounds):
            return 'phenylpyrazole'
        
        # 6. TRIAZOLE FUNGICIDE GROUP
        triazole_compounds = [
            'myclobutanil', 'triadimenol', 'triadiminol',
            'propiconazole', 'tebuconazole', 'difenoconazole'
        ]
        if any(compound in pesticide_lower for compound in triazole_compounds):
            return 'triazole_fungicide'
        
        # 7. JUVENILE HORMONE MIMIC GROUP
        juvenile_hormone_compounds = [
            'pyriproxifen', 'pyriproxyfen', 'pyripoxyfen', 'methoprene', 'fenoxycarb'
        ]
        if any(compound in pesticide_lower for compound in juvenile_hormone_compounds):
            return 'juvenile_hormone_mimic'
        
        # 8. HERBICIDE GROUP
        herbicide_compounds = [
            'atrazine', 'pendimethalin', 'pendimethlin', 'pendimerhanil',
            'glyphosate', '2,4-d', 'dicamba'
        ]
        if any(compound in pesticide_lower for compound in herbicide_compounds):
            return 'herbicide'
        
        # 9. DICARBOXIMIDE FUNGICIDE GROUP
        dicarboximide_compounds = ['procymidon', 'iprodione', 'vinclozolin']
        if any(compound in pesticide_lower for compound in dicarboximide_compounds):
            return 'dicarboximide_fungicide'
        
        # 10. CARBAMATE GROUP
        carbamate_compounds = ['carbaryl', 'methomyl', 'aldicarb', 'carbofuran']
        if any(compound in pesticide_lower for compound in carbamate_compounds):
            return 'carbamate'
        
        # 11. GIBBERELLIN BIOSYNTHESIS INHIBITOR GROUP
        gibberellin_compounds = ['paclobutrazole', 'paclobutrazol']
        if any(compound in pesticide_lower for compound in gibberellin_compounds):
            return 'gibberellin_inhibitor'
        
        return 'other'
    
    def standardize_pesticide_names(self, pesticide_series):
        """Standardize pesticide name variations (from your working code)"""
        def standardize_single(name):
            if pd.isna(name):
                return name
                
            name_lower = str(name).lower()
            
            if any(x in name_lower for x in ['bifenthrin', 'bifnthrin', 'bifenthein']):
                return 'Bifenthrin'
            elif any(x in name_lower for x in ['pyridaben', 'pyridben', 'pyridabien', 'ptridaben']):
                return 'Pyridaben'
            elif any(x in name_lower for x in ['buprofezin', 'buprifezin']):
                return 'Buprofezin'
            elif any(x in name_lower for x in ['bifenazate', 'bifenzate', 'bifanazate']):
                return 'Bifenazate'
            elif any(x in name_lower for x in ['cyhalothrin', 'lambda']):
                return 'Lambda-cyhalothrin'
            elif any(x in name_lower for x in ['pyriproxifen', 'pyriproxyfen', 'pyripoxyfen']):
                return 'Pyriproxifen'
            else:
                return str(name).strip()
        
        return pesticide_series.apply(standardize_single)
    
    def categorize_vegetable(self, vegetable):
        """Categorize vegetables by type (from your working code)"""
        leafy = ['lettuce', 'parsley', 'spinach', 'cabbage', 'arugula']
        fruits = ['tomato', 'cucumber', 'eggplant', 'zucchini', 'strawberry']
        peppers = ['green_bell_pepper', 'red_bell_pepper', 'red_hot_pepper', 'green_hot_pepper']
        
        if any(v in vegetable.lower() for v in leafy):
            return 'leafy_greens'
        elif any(v in vegetable.lower() for v in fruits):
            return 'fruit_vegetables'
        elif any(v in vegetable.lower() for v in peppers):
            return 'peppers'
        else:
            return 'other'
    
    def get_season(self, month):
        """Convert month to season"""
        if month in [12, 1, 2]:
            return 0  # Winter
        elif month in [3, 4, 5]:
            return 1  # Spring
        elif month in [6, 7, 8]:
            return 2  # Summer
        else:
            return 3  # Fall
    
    def load_and_prepare_dataset(self, file_path: str) -> pd.DataFrame:
        """Load and prepare the consolidated dataset"""
        print(f"Loading dataset from: {file_path}")
        
        try:
            df = pd.read_excel(file_path)
            print(f"Dataset loaded: {len(df)} records, {len(df.columns)} columns")
            print(f"Columns: {list(df.columns)}")
            
            return df
            
        except Exception as e:
            print(f"Error loading dataset: {e}")
            return pd.DataFrame()
    # Update the prepare_features method in src/models/PesticideClassificationModel.py

    def prepare_features(self, df):
        """Prepare comprehensive feature set with outlier detection and imputation"""
        print("Preparing features from consolidated dataset...")
        
        # Map dataset columns to expected names
        column_mapping = {
            'النتيجة result': 'result',
            'الحدود limits': 'limits', 
            'قراءة الجهاز reading of device': 'reading',
            'اسم المبيد pesticide name': 'pesticide',
            'اسم العينة sample name': 'vegetable_arabic'
        }
        
        # Rename columns to standard names
        df_processed = df.rename(columns=column_mapping)
        
        # Clean and validate data
        for col in ['reading', 'limits']:
            if col in df_processed.columns:
                # Convert to numeric, handling Arabic "لا يوجد" and other non-numeric values
                df_processed[col] = df_processed[col].astype(str).replace(['لا يوجد', 'nan', ''], np.nan)
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
        
        # Remove invalid records
        initial_count = len(df_processed)
        df_processed = df_processed.dropna(subset=['reading', 'limits', 'pesticide', 'vegetable_arabic'])
        df_processed = df_processed[(df_processed['reading'] > 0) & (df_processed['limits'] > 0)]
        
        print(f"Data cleaning: {initial_count} -> {len(df_processed)} records ({len(df_processed)/initial_count*100:.1f}% retained)")
        
        # ========== NEW: OUTLIER DETECTION AND IMPUTATION ==========
        print("\n🔍 Detecting and handling outliers...")
        
        for col in ['reading', 'limits']:
            if col in df_processed.columns:
                # Calculate IQR
                Q1 = df_processed[col].quantile(0.25)
                Q3 = df_processed[col].quantile(0.75)
                IQR = Q3 - Q1
                
                # Define outlier bounds
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                # Detect outliers
                outliers_mask = (df_processed[col] < lower_bound) | (df_processed[col] > upper_bound)
                outliers_count = outliers_mask.sum()
                
                if outliers_count > 0:
                    print(f"  📊 {col}: Found {outliers_count} outliers ({outliers_count/len(df_processed)*100:.2f}%)")
                    print(f"     Lower bound: {lower_bound:.2f}, Upper bound: {upper_bound:.2f}")
                    
                    # Calculate median for imputation
                    median_value = df_processed[col].median()
                    
                    # Impute outliers with median
                    df_processed.loc[outliers_mask, col] = median_value
                    print(f"     ✅ Outliers imputed with median: {median_value:.2f}")
                else:
                    print(f"  ✅ {col}: No outliers detected")
        
        # Alternative: Z-score method (commented out, you can switch if needed)
        """
        from scipy import stats
        for col in ['reading', 'limits']:
            if col in df_processed.columns:
                z_scores = np.abs(stats.zscore(df_processed[col]))
                outliers_mask = z_scores > 3
                outliers_count = outliers_mask.sum()
                
                if outliers_count > 0:
                    median_value = df_processed[col].median()
                    df_processed.loc[outliers_mask, col] = median_value
                    print(f"  Z-score method: {col} - {outliers_count} outliers imputed")
        """
        # ========== END OUTLIER DETECTION ==========
        
        # Apply transformations (from your working code)
        df_processed['pesticide'] = df_processed['pesticide'].astype(str).fillna('unknown')
        df_processed['vegetable_arabic'] = df_processed['vegetable_arabic'].astype(str).fillna('unknown')
        
        df_processed['pesticide_standardized'] = self.standardize_pesticide_names(df_processed['pesticide'])
        df_processed['pesticide_group'] = df_processed['pesticide_standardized'].apply(self.classify_pesticide_group)
        df_processed['vegetable_english'] = df_processed['vegetable_arabic'].map(self.vegetable_mapping).fillna(df_processed['vegetable_arabic'])
        
        # Handle compliance status
        if 'result' in df_processed.columns:
            result_clean = df_processed['result'].astype(str).str.strip()
            df_processed['is_compliant'] = (result_clean == 'مطابق').astype(int)
        else:
            df_processed['is_compliant'] = (df_processed['reading'] <= df_processed['limits']).astype(int)
        
        # Calculate risk features
        df_processed['exceedance_ratio'] = df_processed['reading'] / df_processed['limits']
        
        def calculate_risk_score(ratio):
            if ratio <= 1:
                return 1
            elif ratio <= 2:
                return 2
            elif ratio <= 5:
                return 3
            else:
                return 4
        
        df_processed['risk_score'] = df_processed['exceedance_ratio'].apply(calculate_risk_score)
        df_processed['vegetable_category'] = df_processed['vegetable_english'].apply(self.categorize_vegetable)
        
        # Log transforms
        df_processed['log_reading'] = np.log1p(df_processed['reading'])
        df_processed['log_limits'] = np.log1p(df_processed['limits'])
        
        # Temporal features
        if 'document_date' in df_processed.columns:
            df_processed['document_date'] = pd.to_datetime(df_processed['document_date'], errors='coerce')
            df_processed['month'] = df_processed['document_date'].dt.month.fillna(6)
        elif 'month' in df_processed.columns:
            df_processed['month'] = pd.to_numeric(df_processed['month'], errors='coerce').fillna(6)
        else:
            df_processed['month'] = 6
        
        df_processed['season'] = df_processed['month'].apply(self.get_season)
        
        print(f"✅ Feature preparation complete: {len(df_processed)} samples")
        return df_processed
    
    # src/models/PesticideClassificationModel.py

    def build_models_separate_features(self, X_train_all, X_train_no_reading, y_train_dict):
        """
        Build all models with separate feature sets
        Models 1, 2, 4: Use ALL features (including reading)
        Model 3: Use REDUCED features (NO reading) - TRUE PREDICTOR
        """
        models = {}
        
        # ============================================================
        # MODEL 1: Compliance (uses ALL features)
        # ============================================================
        print("Building compliance model (with reading)...")
        compliance_model = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, class_weight='balanced'
        )
        compliance_model.fit(X_train_all, y_train_dict['compliance'])
        models['compliance'] = compliance_model
        print("  ✅ Compliance model trained")
        
        # ============================================================
        # MODEL 2: Group Classifier (uses ALL features)
        # ============================================================
        print("Building group classifier (with reading)...")
        unique_groups = np.unique(y_train_dict['pesticide_group'])
        n_classes = len(unique_groups)
        
        # Remap labels
        sorted_labels = sorted(unique_groups)
        label_mapping = {old: new for new, old in enumerate(sorted_labels)}
        y_train_remapped = np.array([label_mapping[label] for label in y_train_dict['pesticide_group']])
        
        try:
            from tensorflow import keras
            
            group_model = keras.Sequential([
                keras.layers.Dense(64, activation='relu', input_shape=(X_train_all.shape[1],)),
                keras.layers.Dropout(0.3),
                keras.layers.Dense(32, activation='relu'),
                keras.layers.Dropout(0.3),
                keras.layers.Dense(16, activation='relu'),
                keras.layers.Dense(n_classes, activation='softmax')
            ])
            
            group_model.compile(
                optimizer='adam',
                loss='sparse_categorical_crossentropy',
                metrics=['accuracy']
            )
            
            group_model.fit(X_train_all, y_train_remapped, 
                        epochs=50, verbose=0, batch_size=16, validation_split=0.2)
            models['pesticide_group'] = group_model
            print("  ✅ Group classifier trained (Keras NN)")
            
        except Exception as e:
            print(f"  ⚠️ Keras failed: {e}, using RandomForest")
            group_model = RandomForestClassifier(n_estimators=50, random_state=42)
            group_model.fit(X_train_all, y_train_dict['pesticide_group'])
            models['pesticide_group'] = group_model
            print("  ✅ Group classifier trained (RandomForest)")
        
        # ============================================================
        # MODEL 3: Concentration Predictor (NO reading!) - REDESIGNED
        # ============================================================
        print("Building TRUE concentration predictor (WITHOUT reading)...")
        print(f"  Feature count: {X_train_no_reading.shape[1]} (vs {X_train_all.shape[1]} with reading)")
        
        concentration_model = GradientBoostingRegressor(
            n_estimators=100, 
            max_depth=6, 
            learning_rate=0.1, 
            random_state=42
        )
        concentration_model.fit(X_train_no_reading, y_train_dict['concentration'])
        models['concentration'] = concentration_model
        print("  ✅ Concentration predictor trained (TRUE PREDICTOR - no data leakage!)")
        
        # ============================================================
        # MODEL 4: Risk Classifier (uses ALL features)
        # ============================================================
        print("Building risk classifier (with reading)...")
        
        try:
            from tensorflow import keras
            
            risk_model = keras.Sequential([
                keras.layers.Dense(32, activation='relu', input_shape=(X_train_all.shape[1],)),
                keras.layers.Dropout(0.2),
                keras.layers.Dense(16, activation='relu'),
                keras.layers.Dropout(0.2),
                keras.layers.Dense(8, activation='relu'),
                keras.layers.Dense(4, activation='softmax')
            ])
            
            risk_model.compile(
                optimizer='adam',
                loss='sparse_categorical_crossentropy',
                metrics=['accuracy']
            )
            
            risk_model.fit(X_train_all, y_train_dict['risk_level'], 
                        epochs=50, verbose=0, batch_size=16, validation_split=0.2)
            models['risk_level'] = risk_model
            print("  ✅ Risk classifier trained (Keras NN)")
            
        except Exception as e:
            print(f"  ⚠️ Keras failed: {e}")
            models['risk_level'] = None
        
        return models


    def train_all_models(self, df, verbose_training=False, test_size=0.2, val_size=0.2):
        """Complete training pipeline with pesticide name and season features"""
        print("Training comprehensive pesticide classification models...")
        
        # Prepare features
        df_processed = self.prepare_features(df)
        
        if df_processed.empty:
            print("No valid data for training!")
            return None
        
        print(f"Training on {len(df_processed)} samples...")
        print(f"Unique pesticides: {df_processed['pesticide_standardized'].nunique()}")
        print(f"Unique groups: {df_processed['pesticide_group'].nunique()}")
        
        try:
            # ============================================================
            # STEP 1: Calculate Statistical Baseline
            # ============================================================
            statistical_baseline = self.calculate_statistical_baseline(df_processed)
            
            # ============================================================
            # STEP 2: Prepare Features - WITH PESTICIDE NAME
            # ============================================================
            categorical_features = [
                'vegetable_english',
                'pesticide_standardized',  # ⬅️ NEW: Specific pesticide
                'pesticide_group',         # Keep for generalization
                'vegetable_category'
            ]
            
            # Encode categorical features
            encoded_features = []
            self.onehot_encoders = {}
            
            for feature in categorical_features:
                if feature in df_processed.columns:
                    encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
                    encoded = encoder.fit_transform(df_processed[[feature]])
                    encoded_features.append(encoded)
                    self.onehot_encoders[feature] = encoder
                    print(f"  ✅ Encoded {feature}: {encoded.shape[1]} categories")
            
            categorical_encoded = np.hstack(encoded_features)
            print(f"  Total categorical features: {categorical_encoded.shape[1]}")
            
            # VERSION A: ALL numerical features (for Models 1, 2, 4)
            numerical_features_all = []
            numerical_cols_all = ['reading', 'limits', 'log_reading', 'exceedance_ratio', 'month', 'season']
            
            for col in numerical_cols_all:
                if col in df_processed.columns:
                    numerical_features_all.append(df_processed[col].values.reshape(-1, 1))
            
            numerical_matrix_all = np.hstack(numerical_features_all)
            
            # VERSION B: NO reading features (for Model 3)
            numerical_features_no_reading = []
            numerical_cols_no_reading = ['limits', 'month', 'season']
            
            for col in numerical_cols_no_reading:
                if col in df_processed.columns:
                    numerical_features_no_reading.append(df_processed[col].values.reshape(-1, 1))
            
            numerical_matrix_no_reading = np.hstack(numerical_features_no_reading)
            
            print(f"  Numerical features (all): {numerical_matrix_all.shape[1]}")
            print(f"  Numerical features (no reading): {numerical_matrix_no_reading.shape[1]}")
            
            # ============================================================
            # STEP 3: Combine Features
            # ============================================================
            features_all = np.hstack([categorical_encoded, numerical_matrix_all])
            features_no_reading = np.hstack([categorical_encoded, numerical_matrix_no_reading])
            
            print(f"  Final feature count (all): {features_all.shape[1]}")
            print(f"  Final feature count (no reading): {features_no_reading.shape[1]}")
            
            # Handle NaN values
            if np.isnan(features_all).any():
                print("  Imputing NaN values with median...")
                from sklearn.impute import SimpleImputer
                
                imputer_all = SimpleImputer(strategy='median')
                features_all = imputer_all.fit_transform(features_all)
                self.feature_imputer = imputer_all
                
                imputer_no_reading = SimpleImputer(strategy='median')
                features_no_reading = imputer_no_reading.fit_transform(features_no_reading)
                self.feature_imputer_no_reading = imputer_no_reading
            else:
                self.feature_imputer = None
                self.feature_imputer_no_reading = None
            
            # ============================================================
            # STEP 4: Scale Features
            # ============================================================
            from sklearn.preprocessing import StandardScaler
            
            self.scaler = StandardScaler()
            features_all_scaled = self.scaler.fit_transform(features_all)
            
            self.scaler_no_reading = StandardScaler()
            features_no_reading_scaled = self.scaler_no_reading.fit_transform(features_no_reading)
            
            print("  ✅ Features scaled")
            
            # ============================================================
            # STEP 5: Create Target Variables
            # ============================================================
            y_dict = {
                'compliance': df_processed['is_compliant'].values,
                'pesticide_group': self.group_label_encoder.fit_transform(df_processed['pesticide_group']),
                'concentration': df_processed['log_reading'].values,
                'risk_level': df_processed['risk_score'].values - 1
            }
            
            # ============================================================
            # STEP 6: Train/Val/Test Splits
            # ============================================================
            print(f"\n📊 Creating train/validation/test splits...")
            
            X_temp_all, X_test_all, indices_temp, indices_test = train_test_split(
                features_all_scaled, range(len(features_all_scaled)), 
                test_size=test_size, random_state=42
            )
            
            val_size_adjusted = val_size / (1 - test_size)
            X_train_all, X_val_all, indices_train, indices_val = train_test_split(
                X_temp_all, indices_temp, 
                test_size=val_size_adjusted, random_state=42
            )
            
            # Split for reduced features (same indices)
            X_train_no_reading = features_no_reading_scaled[indices_train]
            X_val_no_reading = features_no_reading_scaled[indices_val]
            X_test_no_reading = features_no_reading_scaled[indices_test]
            
            # Target splits
            y_train = {name: values[indices_train] for name, values in y_dict.items()}
            y_val = {name: values[indices_val] for name, values in y_dict.items()}
            y_test = {name: values[indices_test] for name, values in y_dict.items()}
            
            print(f"  Training: {X_train_all.shape[0]} samples")
            print(f"  Validation: {X_val_all.shape[0]} samples")
            print(f"  Test: {X_test_all.shape[0]} samples")
            
            # ============================================================
            # STEP 7: Build Models
            # ============================================================
            print(f"\n🤖 Building models...")
            models = self.build_models_separate_features(
                X_train_all, X_train_no_reading, y_train
            )
            
            self.compliance_model = models['compliance']
            self.group_classifier = models['pesticide_group']
            self.concentration_predictor = models['concentration']
            self.risk_classifier = models['risk_level']
            
            # ============================================================
            # STEP 8: Validation
            # ============================================================
            print("\n📊 Validation Results:")
            val_results = {}
            
            val_pred_compliance = self.compliance_model.predict(X_val_all)
            val_acc_compliance = accuracy_score(y_val['compliance'], val_pred_compliance)
            val_results['compliance_accuracy'] = val_acc_compliance
            print(f"  Compliance accuracy: {val_acc_compliance:.4f}")
            
            val_pred_concentration = self.concentration_predictor.predict(X_val_no_reading)
            val_mse_concentration = mean_squared_error(y_val['concentration'], val_pred_concentration)
            val_results['concentration_mse'] = val_mse_concentration
            print(f"  Concentration MSE: {val_mse_concentration:.4f}")
            
            # Test results
            print("\n📊 Test Results:")
            test_results = {}
            
            test_pred_compliance = self.compliance_model.predict(X_test_all)
            test_acc_compliance = accuracy_score(y_test['compliance'], test_pred_compliance)
            test_results['compliance_accuracy'] = test_acc_compliance
            print(f"  Compliance test accuracy: {test_acc_compliance:.4f}")
            
            test_pred_concentration = self.concentration_predictor.predict(X_test_no_reading)
            test_mse_concentration = mean_squared_error(y_test['concentration'], test_pred_concentration)
            test_results['concentration_mse'] = test_mse_concentration
            print(f"  Concentration test MSE: {test_mse_concentration:.4f}")
            
            print("\n✅ All models trained successfully!")
            print(f"🎯 Model includes {df_processed['pesticide_standardized'].nunique()} specific pesticides")
            print(f"📅 Model uses actual month/season from data")
            
            return {
                'processed_data': df_processed,
                'statistical_baseline': statistical_baseline,
                'validation_results': val_results,
                'test_results': test_results,
                'train_data': (X_train_all, X_train_no_reading, y_train),
                'val_data': (X_val_all, X_val_no_reading, y_val),
                'test_data': (X_test_all, X_test_no_reading, y_test)
            }
            
        except Exception as e:
            print(f"Training error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None



    def predict_comprehensive_analysis(
        self, 
        vegetable, 
        pesticide_name,      # ⬅️ UPDATED: Now uses specific pesticide
        pesticide_group, 
        reading, 
        limits,
        collection_date=None  # ⬅️ NEW: Date for season extraction
    ):
        """
        Make comprehensive predictions with pesticide name and actual season
        """
        if not hasattr(self, 'onehot_encoders') or not self.onehot_encoders:
            return {'error': 'Models not trained yet'}
        
        try:
            # ============================================================
            # EXTRACT MONTH AND SEASON FROM DATE
            # ============================================================
            if collection_date:
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(collection_date, "%Y-%m-%d")
                    month = date_obj.month
                    season = self.get_season(month)
                except Exception as e:
                    print(f"Warning: Could not parse date '{collection_date}': {e}")
                    from datetime import datetime
                    month = datetime.now().month
                    season = self.get_season(month)
            else:
                from datetime import datetime
                month = datetime.now().month
                season = self.get_season(month)
            
            print(f"📅 Using: Month={month}, Season={season} ({['Winter','Spring','Summer','Fall'][season]})")
            
            # Check model version
            has_new_scaler = hasattr(self, 'scaler_no_reading') and self.scaler_no_reading is not None
            has_statistical_baseline = hasattr(self, 'statistical_baseline') and self.statistical_baseline
            has_pesticide_name_encoder = 'pesticide_standardized' in self.onehot_encoders
            
            # ============================================================
            # STATISTICAL VALIDATION
            # ============================================================
            statistical_check = None
            if has_statistical_baseline:
                statistical_check = self.validate_reading_statistical(
                    vegetable, pesticide_group, reading, season
                )
            
            # ============================================================
            # PREPARE FEATURES WITH PESTICIDE NAME
            # ============================================================
            if has_pesticide_name_encoder:
                # New model - includes pesticide name
                input_data = pd.DataFrame({
                    'vegetable_english': [vegetable],
                    'pesticide_standardized': [pesticide_name],  # ⬅️ Specific pesticide
                    'pesticide_group': [pesticide_group],
                    'vegetable_category': [self.categorize_vegetable(vegetable)]
                })
                
                feature_list = ['vegetable_english', 'pesticide_standardized', 'pesticide_group', 'vegetable_category']
            else:
                # Old model - only group
                input_data = pd.DataFrame({
                    'vegetable_english': [vegetable],
                    'pesticide_group': [pesticide_group],
                    'vegetable_category': [self.categorize_vegetable(vegetable)]
                })
                
                feature_list = ['vegetable_english', 'pesticide_group', 'vegetable_category']
                print("⚠️  OLD MODEL: Does not use specific pesticide name")
            
            # Encode categorical features
            encoded_features = []
            for feature in feature_list:
                if feature in self.onehot_encoders:
                    try:
                        encoded = self.onehot_encoders[feature].transform(input_data[[feature]])
                        encoded_features.append(encoded)
                    except Exception as e:
                        print(f"Warning: Could not encode {feature}: {e}")
                        return {'error': f'Encoding failed for {feature}'}
            
            if not encoded_features:
                return {'error': 'Could not encode any features'}
            
            categorical_encoded = np.hstack(encoded_features)
            
            # Numerical features
            log_reading = np.log1p(reading)
            exceedance_ratio = reading / limits if limits > 0 else 0
            
            # VERSION A: All features (with actual month/season)
            numerical_all = np.array([[reading, limits, log_reading, exceedance_ratio, month, season]])
            features_all = np.hstack([categorical_encoded, numerical_all])
            
            # VERSION B: No reading features (with actual month/season)
            if has_new_scaler:
                numerical_no_reading = np.array([[limits, month, season]])  # ⬅️ Uses actual season!
                features_no_reading = np.hstack([categorical_encoded, numerical_no_reading])
            else:
                features_no_reading = features_all
            
            # Apply preprocessing
            if hasattr(self, 'feature_imputer') and self.feature_imputer is not None:
                features_all = self.feature_imputer.transform(features_all)
            
            if hasattr(self, 'feature_imputer_no_reading') and self.feature_imputer_no_reading is not None:
                features_no_reading = self.feature_imputer_no_reading.transform(features_no_reading)
            
            # Scale
            features_all_scaled = self.scaler.transform(features_all)
            
            if has_new_scaler:
                features_no_reading_scaled = self.scaler_no_reading.transform(features_no_reading)
            else:
                features_no_reading_scaled = features_all_scaled
            
            results = {}
            
            # ============================================================
            # MODEL 1: COMPLIANCE
            # ============================================================
            if self.compliance_model is not None:
                try:
                    compliance_prob = self.compliance_model.predict_proba(features_all_scaled)[0]
                    results['compliance'] = {
                        'model_type': 'RandomForest',
                        'probability_compliant': float(compliance_prob[1]),
                        'probability_non_compliant': float(compliance_prob[0]),
                        'prediction': 'Compliant' if compliance_prob[1] > 0.5 else 'Non-compliant',
                        'confidence': float(max(compliance_prob))
                    }
                    print("✅ Compliance prediction (Model 1/4)")
                except Exception as e:
                    print(f"❌ Compliance error: {e}")
                    results['compliance'] = {'error': str(e)}
            
            # ============================================================
            # MODEL 2: GROUP CLASSIFICATION
            # ============================================================
            if self.group_classifier is not None:
                try:
                    is_keras = not hasattr(self.group_classifier, 'predict_proba')
                    
                    if is_keras:
                        group_probs = self.group_classifier.predict(features_all_scaled, verbose=0)[0]
                    else:
                        group_probs = self.group_classifier.predict_proba(features_all_scaled)[0]
                    
                    predicted_group_idx = int(np.argmax(group_probs))
                    predicted_group = self.group_label_encoder.inverse_transform([predicted_group_idx])[0]
                    
                    results['pesticide_group_classification'] = {
                        'model_type': 'Keras NN' if is_keras else 'RandomForest',
                        'predicted_group': predicted_group,
                        'input_group': pesticide_group,
                        'matches_input': predicted_group == pesticide_group,
                        'confidence': float(group_probs[predicted_group_idx]),
                        'all_probabilities': {
                            str(self.group_label_encoder.inverse_transform([i])[0]): float(prob)
                            for i, prob in enumerate(group_probs)
                        }
                    }
                    print("✅ Group classification (Model 2/4)")
                except Exception as e:
                    print(f"❌ Group classification error: {e}")
                    results['pesticide_group_classification'] = {'error': str(e)}
            
            # ============================================================
            # MODEL 3: CONCENTRATION VALIDATION (HYBRID)
            # ============================================================
            if self.concentration_predictor is not None:
                try:
                    predicted_log = self.concentration_predictor.predict(features_no_reading_scaled)[0]
                    expected_concentration = np.expm1(predicted_log)
                    
                    ml_deviation = abs(expected_concentration - reading)
                    ml_relative_error = (ml_deviation / reading * 100) if reading > 0 else 0
                    
                    validation_result = {
                        'model_type': 'Hybrid: Statistical + GradientBoosting' if has_statistical_baseline else 'GradientBoosting Only',
                        'uses_pesticide_name': has_pesticide_name_encoder,
                        'uses_actual_season': True,
                        'season_info': {
                            'month': month,
                            'season': season,
                            'season_name': ['Winter', 'Spring', 'Summer', 'Fall'][season]
                        },
                        'ml_prediction': {
                            'expected_concentration': float(expected_concentration),
                            'actual_reading': float(reading),
                            'deviation': float(ml_deviation),
                            'relative_error_percent': float(ml_relative_error)
                        }
                    }
                    
                    # Hybrid decision logic
                    if statistical_check:
                        validation_result['statistical'] = statistical_check
                        z_score = statistical_check.get('z_score')
                        
                        if statistical_check['status'] == 'NO_BASELINE':
                            if ml_relative_error > 50:
                                final_status = '🚨 ANOMALY (ML only)'
                                action = 'Verify reading - significant deviation'
                            elif ml_relative_error > 30:
                                final_status = '⚠️ WARNING (ML only)'
                                action = 'Consider retesting'
                            else:
                                final_status = '✅ NORMAL (ML only)'
                                action = 'No action needed'
                        
                        elif z_score is not None and abs(z_score) > 3:
                            if ml_relative_error < 30:
                                final_status = '🚨 STATISTICAL ANOMALY (ML normal)'
                                action = 'Statistical anomaly - verify with duplicate test'
                            else:
                                final_status = '🚨 ANOMALY (Both methods agree)'
                                action = 'CRITICAL - immediate investigation required'
                        
                        elif abs(z_score) > 2:
                            if ml_relative_error > 30:
                                final_status = '⚠️ WARNING (Both methods concerned)'
                                action = 'Approaching limits - consider retesting'
                            else:
                                final_status = '⚠️ STATISTICAL WARNING (ML normal)'
                                action = 'Monitor closely'
                        
                        else:
                            if ml_relative_error > 50:
                                final_status = '⚠️ ML ANOMALY (Statistics normal)'
                                action = 'ML detects unusual pattern - verify pesticide'
                            elif ml_relative_error > 30:
                                final_status = '⚠️ ML WARNING (Statistics normal)'
                                action = 'Slight deviation from prediction'
                            else:
                                final_status = '✅ NORMAL (Both methods agree)'
                                action = 'No action needed'
                        
                        validation_result['final_status'] = final_status
                        validation_result['recommended_action'] = action
                        
                        # Generate interpretation
                        baseline = statistical_check.get('baseline', {})
                        interpretation_parts = []
                        
                        if statistical_check['status'] != 'NO_BASELINE':
                            interpretation_parts.append(
                                f"Statistical: Reading of {reading:.1f} μg/kg is {z_score:.2f} standard deviations "
                                f"from historical mean of {baseline.get('mean', 0):.1f} μg/kg "
                                f"(based on {baseline.get('historical_samples', 0)} samples in {['Winter','Spring','Summer','Fall'][season]}). "
                                f"Control limits: {baseline.get('lcl', 0):.1f} - {baseline.get('ucl', 0):.1f} μg/kg."
                            )
                        
                        interpretation_parts.append(
                            f"ML Prediction: Based on {vegetable} + {pesticide_name} ({pesticide_group}) patterns in {['Winter','Spring','Summer','Fall'][season]}, "
                            f"expected {expected_concentration:.1f} μg/kg, got {reading:.1f} μg/kg "
                            f"({ml_relative_error:.1f}% deviation)."
                        )
                        
                        if abs(z_score or 0) < 2 and ml_relative_error < 30:
                            interpretation_parts.append("✅ Both methods confirm this is a normal reading for this season.")
                        elif abs(z_score or 0) > 3 and ml_relative_error > 50:
                            interpretation_parts.append("🚨 CRITICAL: Both methods detect significant anomaly.")
                        
                        validation_result['interpretation'] = " ".join(interpretation_parts)
                    
                    else:
                        # ML-only
                        if ml_relative_error > 50:
                            final_status = '🚨 ANOMALY'
                            action = 'Verify reading - significant deviation'
                        elif ml_relative_error > 30:
                            final_status = '⚠️ WARNING'
                            action = 'Consider retesting'
                        else:
                            final_status = '✅ NORMAL'
                            action = 'No action needed'
                        
                        validation_result['final_status'] = final_status
                        validation_result['recommended_action'] = action
                        validation_result['interpretation'] = (
                            f'Based on {vegetable} + {pesticide_name} patterns in {["Winter","Spring","Summer","Fall"][season]}, '
                            f'expected {expected_concentration:.1f} μg/kg, got {reading:.1f} μg/kg '
                            f'({ml_relative_error:.1f}% deviation).'
                        )
                    
                    results['reading_validation'] = validation_result
                    print("✅ Reading validation (Model 3/4)")
                    
                except Exception as e:
                    print(f"❌ Reading validation error: {e}")
                    import traceback
                    traceback.print_exc()
                    results['reading_validation'] = {'error': str(e)}
            
            # ============================================================
            # MODEL 4: RISK CLASSIFICATION
            # ============================================================
            if self.risk_classifier is not None:
                try:
                    risk_probs = self.risk_classifier.predict(features_all_scaled, verbose=0)[0]
                    predicted_risk_idx = int(np.argmax(risk_probs))
                    risk_levels = ['Low', 'Medium', 'High', 'Critical']
                    predicted_risk = risk_levels[predicted_risk_idx]
                    
                    results['risk_classification'] = {
                        'model_type': 'Keras Neural Network',
                        'predicted_risk_level': predicted_risk,
                        'risk_index': predicted_risk_idx,
                        'confidence': float(risk_probs[predicted_risk_idx]),
                        'risk_probabilities': {
                            level: float(prob)
                            for level, prob in zip(risk_levels, risk_probs)
                        }
                    }
                    print("✅ Risk classification (Model 4/4)")
                except Exception as e:
                    print(f"❌ Risk classification error: {e}")
                    risk_level = 'Critical' if exceedance_ratio > 5 else 'High' if exceedance_ratio > 2 else 'Medium' if exceedance_ratio > 1 else 'Low'
                    results['risk_classification'] = {
                        'model_type': 'Rule-based (Fallback)',
                        'predicted_risk_level': risk_level,
                        'exceedance_ratio': exceedance_ratio
                    }
            
            # Add summary
            results['model_summary'] = {
                'total_models_used': 4,
                'models_successful': sum(1 for k, v in results.items() if k != 'model_summary' and 'error' not in v),
                'models': ['compliance', 'group_classification', 'reading_validation_hybrid', 'risk_classification'],
                'validation_approach': 'Hybrid (Statistical 3-sigma + ML)' if has_statistical_baseline else 'ML Only',
                'features_used': {
                    'pesticide_name': has_pesticide_name_encoder,
                    'actual_season': True,
                    'month': month,
                    'season': ['Winter', 'Spring', 'Summer', 'Fall'][season]
                }
            }
            
            return results
            
        except Exception as e:
            import traceback
            print(f"Full traceback:")
            traceback.print_exc()
            return {'error': f'Prediction failed: {str(e)}'}
            
    def _generate_validation_interpretation(self, statistical_check, expected, actual, ml_error, vegetable, pesticide):
        """Generate human-readable interpretation of validation results"""
        
        z_score = statistical_check.get('z_score')
        baseline = statistical_check.get('baseline', {})
        
        interpretation_parts = []
        
        # Statistical component
        if statistical_check['status'] != 'NO_BASELINE':
            interpretation_parts.append(
                f"Statistical: Reading of {actual:.1f} μg/kg is {z_score:.2f} standard deviations "
                f"from historical mean of {baseline.get('mean', 0):.1f} μg/kg "
                f"(based on {baseline.get('historical_samples', 0)} samples). "
                f"Control limits: {baseline.get('lcl', 0):.1f} - {baseline.get('ucl', 0):.1f} μg/kg."
            )
        
        # ML component
        interpretation_parts.append(
            f"ML Prediction: Based on {vegetable} + {pesticide} patterns, "
            f"expected {expected:.1f} μg/kg, got {actual:.1f} μg/kg "
            f"({ml_error:.1f}% deviation)."
        )
        
        # Overall assessment
        if abs(z_score or 0) < 2 and ml_error < 30:
            interpretation_parts.append("✅ Both methods confirm this is a normal reading.")
        elif abs(z_score or 0) > 3 and ml_error > 50:
            interpretation_parts.append("🚨 CRITICAL: Both methods detect significant anomaly - immediate action required.")
        elif abs(z_score or 0) > 3 and ml_error < 30:
            interpretation_parts.append("⚠️ Statistical anomaly detected, but ML suggests reading is plausible. May indicate shift in contamination patterns.")
        elif abs(z_score or 0) < 2 and ml_error > 50:
            interpretation_parts.append("⚠️ ML detects unusual pattern despite normal statistics. Verify pesticide identification.")
        
        return " ".join(interpretation_parts)


    def analyze_dataset_patterns(self, df_processed):
        """Analyze patterns in the dataset (from your working code)"""
        try:
            analysis = {
                'pesticide_group_distribution': df_processed['pesticide_group'].value_counts().to_dict(),
                'vegetable_contamination_rates': df_processed.groupby('vegetable_english')['is_compliant'].mean().sort_values().to_dict(),
                'risk_distribution': {str(k): int(v) for k, v in df_processed['risk_score'].value_counts().sort_index().to_dict().items()},
                'concentration_statistics': {
                    'mean': float(df_processed['reading'].mean()),
                    'median': float(df_processed['reading'].median()),
                    'std': float(df_processed['reading'].std()),
                    'min': float(df_processed['reading'].min()),
                    'max': float(df_processed['reading'].max())
                }
            }
            return analysis
        except Exception as e:
            print(f"Analysis error: {e}")
            return {}
    
    def generate_recommendations(self, prediction_result, vegetable, pesticide_group):
        """Generate specific recommendations (from your working code)"""
        recommendations = []
        
        try:
            if 'compliance' in prediction_result and prediction_result['compliance']['probability_compliant'] < 0.5:
                recommendations.append("HIGH PRIORITY: Sample likely non-compliant - immediate investigation required")
            
            if 'risk_score' in prediction_result:
                risk_level = prediction_result['risk_score']['predicted_level']
                if risk_level in ['High', 'Critical']:
                    recommendations.append(f"{risk_level} risk detected - increase testing frequency")
            
            if pesticide_group in self.group_risk_profiles:
                group_risks = self.group_risk_profiles[pesticide_group]
                for risk_type, level in group_risks.items():
                    if level in ['high', 'medium']:
                        recommendations.append(f"Monitor for {risk_type} effects due to {pesticide_group} exposure")
            
            if 'pepper' in vegetable.lower():
                recommendations.append("Peppers show high contamination rates - implement enhanced washing protocols")
            elif 'leafy' in self.categorize_vegetable(vegetable):
                recommendations.append("Leafy greens require special attention - difficult to decontaminate")
            
        except Exception as e:
            recommendations.append(f"Error generating recommendations: {str(e)}")
        
        return recommendations if recommendations else ["No specific recommendations available"]
    
    def calculate_statistical_baseline(self, df_processed):
        """
        Calculate control limits for each vegetable-pesticide-season combination
        This implements Food Safety Best Practice: Control Charts
        """
        print("\n📊 Calculating Statistical Process Control Baselines...")
        
        # Group by key combinations
        grouping_cols = ['vegetable_english', 'pesticide_group', 'season']
        
        baseline_stats = df_processed.groupby(grouping_cols)['reading'].agg([
            'count',
            'mean',
            'std',
            'median',
            ('p25', lambda x: x.quantile(0.25)),
            ('p75', lambda x: x.quantile(0.75)),
            'min',
            'max'
        ]).reset_index()
        
        # Calculate control limits (3-sigma)
        baseline_stats['ucl'] = baseline_stats['mean'] + 3 * baseline_stats['std']
        baseline_stats['lcl'] = baseline_stats['mean'] - 3 * baseline_stats['std']
        baseline_stats['lcl'] = baseline_stats['lcl'].clip(lower=0)  # Can't be negative
        
        # Store as dictionary for fast lookup
        for _, row in baseline_stats.iterrows():
            key = (row['vegetable_english'], row['pesticide_group'], row['season'])
            self.statistical_baseline[key] = {
                'count': int(row['count']),
                'mean': float(row['mean']),
                'std': float(row['std']),
                'median': float(row['median']),
                'p25': float(row['p25']),
                'p75': float(row['p75']),
                'min': float(row['min']),
                'max': float(row['max']),
                'ucl': float(row['ucl']),
                'lcl': float(row['lcl'])
            }
        
        print(f"   ✅ Statistical baseline calculated for {len(self.statistical_baseline)} combinations")
        return baseline_stats
    
    def validate_reading_statistical(self, vegetable, pesticide_group, reading, season=2):
        """
        Validate reading using Statistical Process Control
        Returns Z-score and control limit status
        """
        key = (vegetable, pesticide_group, season)
        
        if key not in self.statistical_baseline:
            # Try without season specificity
            key_no_season = (vegetable, pesticide_group, None)
            baseline = None
            
            # Find any matching baseline
            for k, v in self.statistical_baseline.items():
                if k[0] == vegetable and k[1] == pesticide_group:
                    baseline = v
                    break
            
            if baseline is None:
                return {
                    'status': 'NO_BASELINE',
                    'message': f'No historical data for {vegetable} + {pesticide_group}',
                    'z_score': None,
                    'within_control_limits': None
                }
        else:
            baseline = self.statistical_baseline[key]
        
        # Calculate Z-score
        mean = baseline['mean']
        std = baseline['std']
        
        if std == 0 or std is None:
            z_score = 0
        else:
            z_score = (reading - mean) / std
        
        # Check control limits
        within_ucl = reading <= baseline['ucl']
        within_lcl = reading >= baseline['lcl']
        within_limits = within_ucl and within_lcl
        
        # Determine status
        if abs(z_score) > 3:
            status = '🚨 STATISTICAL ANOMALY'
            interpretation = f'Reading is {abs(z_score):.1f} standard deviations from historical mean'
        elif abs(z_score) > 2:
            status = '⚠️ WARNING'
            interpretation = f'Reading is {abs(z_score):.1f} standard deviations from mean (approaching limits)'
        else:
            status = '✅ NORMAL'
            interpretation = f'Reading within expected range (Z={z_score:.2f})'
        
        return {
            'status': status,
            'z_score': float(z_score),
            'within_control_limits': within_limits,
            'interpretation': interpretation,
            'baseline': {
                'mean': mean,
                'std': std,
                'ucl': baseline['ucl'],
                'lcl': baseline['lcl'],
                'historical_samples': baseline['count']
            }
        }


class SingleDatasetClassificationSystem:
    """Main system class for single dataset processing"""
    
    def __init__(self, dataset_path: str = None):
        self.dataset_path = Path(dataset_path)
        self.classifier = PesticideClassificationModel(dataset_path)
        self.training_results = None
    
    def run_complete_training(self, verbose_training=False):
        """Run the complete training pipeline"""
        print("SINGLE DATASET PESTICIDE CLASSIFICATION SYSTEM")
        print("=" * 60)
        print("Streamlined system for consolidated dataset processing")
        
        # Load dataset
        df = self.classifier.load_and_prepare_dataset(str(self.dataset_path))
        
        if df.empty:
            print("Failed to load dataset!")
            return None
        
        # Train models with train/val/test splits
        print(f"\nTraining models on dataset with {len(df)} records...")
        print(f"Verbose training: {verbose_training}")
        self.training_results = self.classifier.train_all_models(
            df, verbose_training=verbose_training
        )
        
        if self.training_results is None:
            print("Model training failed!")
            return None
        
        # Analyze patterns
        df_processed = self.training_results['processed_data']
        patterns = self.classifier.analyze_dataset_patterns(df_processed)
        
        print(f"\nTraining completed successfully!")
        self.print_training_summary(df_processed, patterns)
        
        return self.training_results, patterns
    
    def print_training_summary(self, df_processed, patterns):
        """Print comprehensive training summary"""
        print(f"\nTraining Summary:")
        print(f"• Total records processed: {len(df_processed):,}")
        print(f"• Pesticide groups identified: {len(patterns.get('pesticide_group_distribution', {}))}")
        print(f"• Vegetables analyzed: {len(patterns.get('vegetable_contamination_rates', {}))}")
        print(f"• Risk distribution: {patterns.get('risk_distribution', {})}")
        
        # Validation results
        if 'validation_results' in self.training_results:
            val_results = self.training_results['validation_results']
            print(f"\nValidation Performance:")
            for metric, value in val_results.items():
                print(f"• {metric}: {value:.4f}")
        
        # Test results
        if 'test_results' in self.training_results:
            test_results = self.training_results['test_results']
            print(f"\nTest Performance:")
            for metric, value in test_results.items():
                print(f"• {metric}: {value:.4f}")
    
    def demonstrate_capabilities(self, patterns):
        """Demonstrate system capabilities"""
        print("\nSYSTEM CAPABILITIES DEMONSTRATION")
        print("=" * 50)
        
        print("What analysts can discover:")
        
        # Top contaminated vegetables
        if 'vegetable_contamination_rates' in patterns and patterns['vegetable_contamination_rates']:
            print("\nVegetables by contamination risk:")
            sorted_vegetables = sorted(
                patterns['vegetable_contamination_rates'].items(),
                key=lambda x: 1-x[1]
            )[:5]
            
            for veg, compliance_rate in sorted_vegetables:
                contamination_rate = (1 - compliance_rate) * 100
                print(f"  • {veg}: {contamination_rate:.1f}% contamination rate")
        
        # Pesticide group distribution
        if 'pesticide_group_distribution' in patterns and patterns['pesticide_group_distribution']:
            print("\nMost detected pesticide groups:")
            sorted_groups = sorted(
                patterns['pesticide_group_distribution'].items(), 
                key=lambda x: x[1], reverse=True
            )[:5]
            total_samples = sum(patterns['pesticide_group_distribution'].values())
            
            for group, count in sorted_groups:
                percentage = (count / total_samples) * 100
                print(f"  • {group}: {count} samples ({percentage:.1f}%)")
    
    def test_prediction_system(self):
        """Test the trained prediction system"""
        print("\nTESTING PREDICTION SYSTEM")
        print("=" * 40)
        
        test_cases = [
            {
                'vegetable': 'tomato',
                'pesticide_group': 'pyrethroid',
                'reading': 45.5,
                'limits': 10.0,
                'description': 'High contamination tomato'
            },
            {
                'vegetable': 'green_bell_pepper',
                'pesticide_group': 'mite_control',
                'reading': 25.3,
                'limits': 50.0,
                'description': 'Normal pepper sample'
            },
            {
                'vegetable': 'cucumber',
                'pesticide_group': 'chitin_synthesis_inhibitor',
                'reading': 155.0,
                'limits': 10.0,
                'description': 'Critical contamination cucumber'
            }
        ]
        
        for i, case in enumerate(test_cases, 1):
            print(f"\nTest Case {i}: {case['description']}")
            print(f"Sample: {case['vegetable']} with {case['pesticide_group']}")
            print(f"Reading: {case['reading']} μg/kg (limit: {case['limits']})")
            
            try:
                result = self.classifier.predict_comprehensive_analysis(
                    case['vegetable'], case['pesticide_group'],
                    case['reading'], case['limits']
                )
                
                if 'error' in result:
                    print(f"Prediction failed: {result['error']}")
                    continue
                
                print("Results:")
                if 'compliance' in result:
                    print(f"  Compliance: {result['compliance']['prediction']}")
                    print(f"  Confidence: {result['compliance']['probability_compliant']:.1%}")
                
                if 'risk_score' in result:
                    print(f"  Risk Level: {result['risk_score']['predicted_level']}")
                
                # Generate recommendations
                recommendations = self.classifier.generate_recommendations(
                    result, case['vegetable'], case['pesticide_group']
                )
                
                if recommendations:
                    print(f"  Key Recommendation: {recommendations[0]}")
                
                print("  Prediction successful")
                
            except Exception as e:
                print(f"Prediction failed: {str(e)}")
    
    # src/models/PesticideClassificationModel.py

    def save_system(self, output_dir: str = "single_dataset_system"):
        """Save the trained system with statistical baseline"""
        if not self.training_results:
            print("No trained system to save!")
            return
        
        try:
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save processed dataset
            df_processed = self.training_results['processed_data']
            processed_file = output_path / f"processed_dataset_{timestamp}.xlsx"
            df_processed.to_excel(processed_file, index=False)
            
            # Save models
            models_dir = output_path / "trained_models"
            models_dir.mkdir(exist_ok=True)
            
            try:
                import joblib
                
                # Save sklearn models
                if self.classifier.compliance_model:
                    joblib.dump(self.classifier.compliance_model, models_dir / "compliance_model.pkl")
                
                if self.classifier.concentration_predictor:
                    joblib.dump(self.classifier.concentration_predictor, models_dir / "concentration_predictor.pkl")
                
                # Save encoders and scalers
                joblib.dump(self.classifier.scaler, models_dir / "scaler.pkl")
                joblib.dump(self.classifier.scaler_no_reading, models_dir / "scaler_no_reading.pkl")  # NEW
                joblib.dump(self.classifier.group_label_encoder, models_dir / "group_label_encoder.pkl")
                joblib.dump(self.classifier.onehot_encoders, models_dir / "onehot_encoders.pkl")
                
                # Save statistical baseline (NEW)
                joblib.dump(self.classifier.statistical_baseline, models_dir / "statistical_baseline.pkl")
                print(f"  ✅ Statistical baseline saved ({len(self.classifier.statistical_baseline)} combinations)")
                
                if hasattr(self.classifier, 'feature_imputer') and self.classifier.feature_imputer:
                    joblib.dump(self.classifier.feature_imputer, models_dir / "feature_imputer.pkl")
                
                if hasattr(self.classifier, 'feature_imputer_no_reading') and self.classifier.feature_imputer_no_reading:
                    joblib.dump(self.classifier.feature_imputer_no_reading, models_dir / "feature_imputer_no_reading.pkl")
                
                # Save TensorFlow models
                if self.classifier.group_classifier:
                    try:
                        self.classifier.group_classifier.save(models_dir / "group_classifier.keras")
                    except:
                        joblib.dump(self.classifier.group_classifier, models_dir / "group_classifier.pkl")
                
                if self.classifier.risk_classifier:
                    self.classifier.risk_classifier.save(models_dir / "risk_classifier.keras")
                
                print(f"Models saved to: {models_dir}")
                
            except Exception as e:
                print(f"Error saving models: {str(e)}")
            
            # Save results summary
            results_file = output_path / f"training_results_{timestamp}.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                import json
                
                serializable_results = {
                    'training_summary': {
                        'total_samples': len(df_processed),
                        'training_date': timestamp,
                        'dataset_path': str(self.dataset_path),
                        'statistical_combinations': len(self.classifier.statistical_baseline)
                    },
                    'validation_results': self.training_results.get('validation_results', {}),
                    'test_results': self.training_results.get('test_results', {}),
                    'approach': 'Hybrid: Statistical Process Control + ML Prediction (no data leakage)'
                }
                
                json.dump(serializable_results, f, indent=2, default=str)
            
            print(f"\n✅ System saved successfully:")
            print(f"  • Processed dataset: {processed_file}")
            print(f"  • Training results: {results_file}")
            print(f"  • Models directory: {models_dir}")
            print(f"  • Statistical baseline: {len(self.classifier.statistical_baseline)} combinations")
            
        except Exception as e:
            print(f"Error saving system: {e}")

def main():
    """Main function to run the single dataset classification system"""
    print("SINGLE DATASET PESTICIDE CLASSIFICATION SYSTEM")
    print("=" * 60)
    
    # Update this path to your consolidated dataset
    dataset_path = "/Users/a12/mini-rag/src/data/dataset.xlsx"  # Change this to your dataset path
    
    if not Path(dataset_path).exists():
        print(f"Dataset file not found: {dataset_path}")
        print("Please update the dataset_path variable")
        dataset_path = input("Enter path to your dataset file: ").strip()
        
        if not Path(dataset_path).exists():
            print(f"File not found: {dataset_path}")
            return
    
    try:
        # Initialize system
        system = SingleDatasetClassificationSystem(dataset_path)
        
        # Run complete training
        result = system.run_complete_training()
        
        if result:
            training_results, patterns = result
            
            # --- Save the processed data to an Excel file ---

            # df_processed = training_results['processed_data']
            # output_filename = "processed_data_output.xlsx"
            # try:
            #     df_processed.to_excel(output_filename, index=False, engine='openpyxl')
            #     print(f"\n✅ Successfully saved the processed data to '{output_filename}'")
            # except Exception as e:
            #     print(f"\n❌ Could not save the processed data file: {e}")
            # ---

            # Demonstrate capabilities
            system.demonstrate_capabilities(patterns)
            
            # Test prediction system
            system.test_prediction_system()
            
            # Save system
            system.save_system()
            
            print("\nSUCCESS! Single dataset classification system ready!")
            print("\nNext steps:")
            print("• Deploy models for real-time prediction")
            print("• Create dashboard for visualization")
            print("• Integrate with laboratory workflows")
            print("• Set up automated reporting")
            
        else:
            print("System training failed")
            
    except Exception as e:
        print(f"System error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()