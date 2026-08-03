#!/usr/bin/env python3
"""
Pesticide Data Processor for Small Dataset (340 positive readings)
=================================================================

Optimized for small datasets with comprehensive analysis and production features.
Perfect for 340 positive pesticide detection samples.

Usage:
    python pesticide_processor.py [dataset_file] [--output output_file]
    
Example:
    python pesticide_processor.py dataset.xlsx --output processed_data.xlsx
"""

import pandas as pd
import numpy as np
from pathlib import Path
import argparse
import sys
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

class PesticideDataProcessor:
    """
    Pesticide data processor optimized for small datasets (340 samples)
    Production-ready with comprehensive analysis features
    """
    
    def __init__(self):
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
            'برتقال': 'orange', 'ليمون': 'lemon', 'نعناع': 'mint',
            'جرجير': 'arugula', 'شمام': 'cantaloupe', 'سبانخ': 'spinach'
        }
    
    def load_dataset(self, filepath):
        """Load the cleaned dataset with 340 positive readings"""
        try:
            file_path = Path("/Users/a12/mini-rag/src/data/dataset.xlsx")
            print(f"📁 Loading dataset from {file_path}")
            
            # Load Excel file
            if file_path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(filepath)
            elif file_path.suffix.lower() == '.csv':
                df = pd.read_csv(filepath)
            else:
                raise ValueError(f"Unsupported file format: {file_path.suffix}")
            
            print(f"✅ Dataset loaded: {len(df):,} rows, {len(df.columns)} columns")
            
            # Expected column structure for your cleaned dataset
            expected_columns = [
                'result', 'uncertainty', 'limits', 'reading', 
                'pesticide', 'vegetable_arabic', 'sample_code', 'document_date'
            ]
            
            # If columns don't match exactly, use first 8 columns
            if len(df.columns) >= 8:
                if list(df.columns[:8]) != expected_columns:
                    print("📝 Mapping columns to expected structure...")
                    df = df.iloc[:, :8].copy()
                    df.columns = expected_columns
            
            # Remove any empty rows
            df = df.dropna(subset=['vegetable_arabic', 'pesticide'])
            print(f"📊 Clean dataset: {len(df):,} valid samples")
            
            return df
            
        except Exception as e:
            print(f"❌ Error loading dataset: {str(e)}")
            return None
    
    def standardize_pesticide_names(self, pesticide_series):
        """Standardize pesticide name variations"""
        
        def standardize_single(name):
            if pd.isna(name):
                return 'unknown'
            
            name_clean = str(name).strip()
            name_lower = name_clean.lower()
            
            # Common standardizations based on your data
            if 'bifenthrin' in name_lower:
                return 'Bifenthrin'
            elif 'pyridaben' in name_lower:
                return 'Pyridaben'
            elif 'buprofezin' in name_lower:
                return 'Buprofezin'
            elif 'quinalphos' in name_lower:
                return 'Quinalphos'
            elif 'fipronil' in name_lower:
                return 'Fipronil'
            elif 'bifenazate' in name_lower:
                return 'Bifenazate'
            elif 'cyhalothrin' in name_lower or 'lambda' in name_lower:
                return 'Lambda-cyhalothrin'
            elif 'deltamethrin' in name_lower:
                return 'Deltamethrin'
            elif 'fenpropathrin' in name_lower:
                return 'Fenpropathrin'
            elif 'myclobutanil' in name_lower:
                return 'Myclobutanil'
            elif 'pyriproxifen' in name_lower:
                return 'Pyriproxifen'
            else:
                return name_clean
        
        return pesticide_series.apply(standardize_single)
    
    def classify_pesticide_groups(self, pesticide_series):
        """Classify pesticides into chemical groups"""
        
        def classify_single(pesticide):
            if pd.isna(pesticide):
                return 'unknown'
            
            lower = str(pesticide).lower()
            
            # Chemical group classification
            if any(x in lower for x in ['bifenthrin', 'cyhalothrin', 'deltamethrin', 'fenpropathrin']):
                return 'pyrethroid'
            elif 'quinalphos' in lower:
                return 'organophosphorus'
            elif 'buprofezin' in lower:
                return 'chitin_synthesis_inhibitor'
            elif any(x in lower for x in ['pyridaben', 'bifenazate']):
                return 'mite_control'
            elif 'fipronil' in lower:
                return 'phenylpyrazole'
            elif any(x in lower for x in ['myclobutanil', 'triadimenol']):
                return 'triazole_fungicide'
            elif 'pyriproxifen' in lower:
                return 'juvenile_hormone_mimic'
            else:
                return 'other'
        
        return pesticide_series.apply(classify_single)
    
    def categorize_vegetables(self, vegetable_series):
        """Categorize vegetables for analysis"""
        
        def categorize_single(vegetable):
            if pd.isna(vegetable):
                return 'unknown'
            
            veg_english = str(vegetable).lower()
            
            # Peppers (major category in your data)
            if 'pepper' in veg_english:
                if 'hot' in veg_english:
                    return 'hot_peppers'
                else:
                    return 'bell_peppers'
            
            # Leafy greens
            elif any(x in veg_english for x in ['lettuce', 'parsley', 'spinach', 'arugula']):
                return 'leafy_greens'
            
            # Fruit vegetables
            elif any(x in veg_english for x in ['tomato', 'cucumber', 'eggplant', 'zucchini']):
                return 'fruit_vegetables'
            
            # Legumes
            elif 'beans' in veg_english:
                return 'legumes'
            
            # Fruits
            elif any(x in veg_english for x in ['fig', 'pomegranate', 'orange', 'strawberry']):
                return 'fruits'
            
            else:
                return 'other_vegetables'
        
        return vegetable_series.apply(categorize_single)
    
    def process_dataset(self, df):
        """Process the complete dataset"""
        print("🔄 Processing dataset...")
        
        if df is None or len(df) == 0:
            raise ValueError("No data to process")
        
        # Convert numeric columns
        numeric_columns = ['uncertainty', 'limits', 'reading']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Process date column if present
        if 'document_date' in df.columns:
            df['document_date'] = pd.to_datetime(df['document_date'], errors='coerce')
            
            # Extract time features for time series analysis
            df['year'] = df['document_date'].dt.year
            df['month'] = df['document_date'].dt.month
            df['quarter'] = df['document_date'].dt.quarter
            df['day_of_year'] = df['document_date'].dt.dayofyear
            df['week_of_year'] = df['document_date'].dt.isocalendar().week
            
            # Season indicators
            df['season'] = df['month'].apply(lambda x: 
                'winter' if x in [12, 1, 2] else
                'spring' if x in [3, 4, 5] else
                'summer' if x in [6, 7, 8] else 'fall'
            )
            df['is_summer'] = (df['season'] == 'summer').astype(int)
            df['is_winter'] = (df['season'] == 'winter').astype(int)
        
        # Remove rows with missing critical data
        initial_rows = len(df)
        df = df.dropna(subset=['reading', 'limits', 'pesticide', 'vegetable_arabic'])
        print(f"📊 Removed {initial_rows - len(df)} rows with missing data")
        
        # Apply transformations
        print("🔄 Applying transformations...")
        df['pesticide_standardized'] = self.standardize_pesticide_names(df['pesticide'])
        df['pesticide_group'] = self.classify_pesticide_groups(df['pesticide_standardized'])
        
        # Map vegetables to English
        df['vegetable_english'] = df['vegetable_arabic'].map(self.vegetable_mapping)
        df['vegetable_english'] = df['vegetable_english'].fillna(df['vegetable_arabic'])
        df['vegetable_category'] = self.categorize_vegetables(df['vegetable_english'])
        
        # Calculate risk features
        print("📊 Calculating risk features...")
        
        # Exceedance ratio (handling division by zero)
        df['exceedance_ratio'] = np.where(
            df['limits'] > 0, 
            df['reading'] / df['limits'], 
            0
        )
        
        # Risk scoring
        def calculate_risk_score(ratio):
            if ratio <= 1:
                return 1  # Low
            elif ratio <= 2:
                return 2  # Medium  
            elif ratio <= 5:
                return 3  # High
            else:
                return 4  # Critical
        
        df['risk_score'] = df['exceedance_ratio'].apply(calculate_risk_score)
        df['risk_level'] = df['risk_score'].map({
            1: 'low', 2: 'medium', 3: 'high', 4: 'critical'
        })
        
        # Compliance indicators
        df['is_compliant'] = (df['result'] == 'مطابق').astype(int)
        df['exceeds_limit'] = (df['exceedance_ratio'] > 1).astype(int)
        
        # Log transformations for ML
        df['log_reading'] = np.log1p(df['reading'])
        df['log_limits'] = np.log1p(df['limits'])
        
        # Concentration categories
        df['concentration_level'] = pd.cut(
            df['reading'], 
            bins=[0, 10, 50, 100, 500, float('inf')], 
            labels=['very_low', 'low', 'medium', 'high', 'very_high']
        )
        
        print(f"✅ Processing complete! Final dataset: {len(df)} rows")
        return df
    
    def generate_comprehensive_summary(self, df):
        """Generate comprehensive summary for 340 samples"""
        print("📊 Generating comprehensive summary...")
        
        summary = {
            'dataset_overview': {
                'total_samples': len(df),
                'processing_date': datetime.now().isoformat(),
                'date_range': f"{df['document_date'].min()} to {df['document_date'].max()}" if 'document_date' in df.columns else 'No dates available'
            },
            'compliance_analysis': {
                'compliant_samples': int(df['is_compliant'].sum()),
                'non_compliant_samples': int((df['is_compliant'] == 0).sum()),
                'compliance_rate': f"{df['is_compliant'].mean():.1%}",
                'samples_exceeding_limits': int(df['exceeds_limit'].sum()),
                'exceedance_rate': f"{df['exceeds_limit'].mean():.1%}"
            },
            'concentration_statistics': {
                'min_concentration': f"{df['reading'].min():.2f} µg/kg",
                'max_concentration': f"{df['reading'].max():.2f} µg/kg",
                'mean_concentration': f"{df['reading'].mean():.2f} µg/kg",
                'median_concentration': f"{df['reading'].median():.2f} µg/kg",
                'concentration_range': f"{df['reading'].max() - df['reading'].min():.2f} µg/kg"
            },
            'pesticide_analysis': {
                'unique_pesticides': int(df['pesticide_standardized'].nunique()),
                'most_detected_pesticides': df['pesticide_standardized'].value_counts().head().to_dict(),
                'chemical_group_distribution': df['pesticide_group'].value_counts().to_dict(),
                'pesticide_concentration_stats': df.groupby('pesticide_standardized')['reading'].agg(['count', 'mean', 'max']).round(2).to_dict()
            },
            'vegetable_analysis': {
                'unique_vegetables': int(df['vegetable_english'].nunique()),
                'most_tested_vegetables': df['vegetable_english'].value_counts().head().to_dict(),
                'vegetable_categories': df['vegetable_category'].value_counts().to_dict(),
                'vegetable_contamination_rates': df.groupby('vegetable_english')['exceeds_limit'].mean().round(3).to_dict()
            },
            'risk_assessment': {
                'risk_level_distribution': df['risk_level'].value_counts().to_dict(),
                'high_risk_samples': int((df['risk_score'] >= 3).sum()),
                'critical_risk_samples': int((df['risk_score'] == 4).sum()),
                'max_exceedance_ratio': f"{df['exceedance_ratio'].max():.2f}x",
                'avg_exceedance_ratio': f"{df['exceedance_ratio'].mean():.2f}x"
            }
        }
        
        # Add temporal analysis if dates available
        if 'year' in df.columns:
            summary['temporal_analysis'] = {
                'years_covered': df['year'].nunique(),
                'samples_per_year': df['year'].value_counts().sort_index().to_dict(),
                'seasonal_distribution': df['season'].value_counts().to_dict() if 'season' in df.columns else {},
                'monthly_contamination_trend': df.groupby('month')['exceeds_limit'].mean().round(3).to_dict() if 'month' in df.columns else {}
            }
        
        # High-risk combinations
        high_risk_combos = df[df['risk_score'] >= 3].groupby(['vegetable_english', 'pesticide_standardized']).size()
        summary['high_risk_combinations'] = high_risk_combos.sort_values(ascending=False).head().to_dict()
        
        return summary
    
    def export_results(self, df, summary, output_path='processed_pesticide_data'):
        """Export all results with timestamp"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = {}
        
        # Main processed dataset
        main_file = f"{output_path}_{timestamp}.xlsx"
        df.to_excel(main_file, index=False)
        results['main_dataset'] = main_file
        print(f"📁 Main dataset: {main_file}")
        
        # ML-ready features
        ml_columns = [
            'vegetable_english', 'vegetable_category', 'pesticide_standardized', 
            'pesticide_group', 'reading', 'limits', 'uncertainty',
            'log_reading', 'log_limits', 'exceedance_ratio',
            'concentration_level', 'risk_score', 'risk_level', 'is_compliant'
        ]
        
        # Add temporal features if available
        if 'year' in df.columns:
            ml_columns.extend(['year', 'month', 'quarter', 'season', 'is_summer', 'is_winter'])
        
        ml_features = df[ml_columns].copy()
        ml_file = f"{output_path}_ml_features_{timestamp}.xlsx"
        ml_features.to_excel(ml_file, index=False)
        results['ml_features'] = ml_file
        print(f"🤖 ML features: {ml_file}")
        
        # High-risk samples
        high_risk = df[df['risk_score'] >= 3]
        if len(high_risk) > 0:
            risk_file = f"{output_path}_high_risk_{timestamp}.xlsx"
            high_risk.to_excel(risk_file, index=False)
            results['high_risk'] = risk_file
            print(f"⚠️ High-risk samples: {risk_file}")
        
        # Time series data (if dates available)
        if 'document_date' in df.columns:
            # Monthly aggregations for time series
            monthly_agg = df.groupby([df['document_date'].dt.to_period('M')]).agg({
                'reading': ['count', 'mean', 'max'],
                'exceeds_limit': ['sum', 'mean'],
                'risk_score': 'mean',
                'vegetable_english': lambda x: x.mode().iloc[0] if not x.empty else 'unknown'
            }).round(3)
            
            monthly_agg.columns = ['sample_count', 'avg_concentration', 'max_concentration', 
                                 'violations', 'violation_rate', 'avg_risk', 'primary_vegetable']
            monthly_agg = monthly_agg.reset_index()
            
            ts_file = f"{output_path}_time_series_{timestamp}.xlsx"
            monthly_agg.to_excel(ts_file, index=False)
            results['time_series'] = ts_file
            print(f"📅 Time series: {ts_file}")
        
        # Summary report
        summary_file = f"{output_path}_summary_{timestamp}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        results['summary'] = summary_file
        print(f"📊 Summary: {summary_file}")
        
        return results

def main():
    """Main function for production use"""
    parser = argparse.ArgumentParser(description='Process 340 positive pesticide readings')
    parser.add_argument('input_file', nargs='?', default='dataset.xlsx', 
                       help='Input Excel file (default: dataset.xlsx)')
    parser.add_argument('--output', default='processed_pesticide_data', 
                       help='Output file prefix (default: processed_pesticide_data)')
    
    args = parser.parse_args()
    
    try:
        print("🔬 Pesticide Data Processor for 340 Positive Readings")
        print("=" * 60)
        
        processor = PesticideDataProcessor()
        
        # Load and process
        df = processor.load_dataset(args.input_file)
        if df is None:
            return 1
        
        processed_df = processor.process_dataset(df)
        summary = processor.generate_comprehensive_summary(processed_df)
        results = processor.export_results(processed_df, summary, args.output)
        
        # Print final summary
        print("\n" + "🎉" * 30 + " SUCCESS! " + "🎉" * 30)
        print(f"📊 Processed {summary['dataset_overview']['total_samples']} samples")
        print(f"✅ Compliance rate: {summary['compliance_analysis']['compliance_rate']}")
        print(f"⚠️ High-risk samples: {summary['risk_assessment']['high_risk_samples']}")
        print(f"🧪 Unique pesticides: {summary['pesticide_analysis']['unique_pesticides']}")
        print(f"🥬 Unique vegetables: {summary['vegetable_analysis']['unique_vegetables']}")
        print(f"📅 Date coverage: {summary['dataset_overview']['date_range']}")
        print("\n📁 Generated files:")
        for file_type, filepath in results.items():
            print(f"• {file_type}: {filepath}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1

def test_processor():
    """Quick test function"""
    print("🧪 Quick Test Mode")
    print("=" * 30)
    
    processor = PesticideDataProcessor()
    df = processor.load_dataset('dataset.xlsx')
    
    if df is None:
        print("❌ Test failed - could not load dataset")
        return False
    
    processed_df = processor.process_dataset(df)
    summary = processor.generate_comprehensive_summary(processed_df)
    
    print(f"✅ Test successful!")
    print(f"• Samples: {summary['dataset_overview']['total_samples']}")
    print(f"• Compliance: {summary['compliance_analysis']['compliance_rate']}")
    print(f"• Pesticides: {summary['pesticide_analysis']['unique_pesticides']}")
    print(f"• Ready for production!")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No arguments - run test
        test_success = test_processor()
        if test_success:
            print("\n💡 To run full processing:")
            print("python pesticide_processor.py dataset.xlsx")
    else:
        # Run main processing
        sys.exit(main())