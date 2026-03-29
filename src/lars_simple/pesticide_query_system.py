"""
Natural Language Query System for Pesticide Testing Data
Uses LLM to generate Pandas code instead of RAG for better accuracy
"""

import pandas as pd
import json
from datetime import datetime
from typing import Dict, Any, List

class PesticideDataQuerySystem:
    """
    A query system that converts natural language questions into Pandas operations
    Much more accurate than RAG for structured data
    """
    
    def __init__(self, excel_path: str):
        """Initialize with the Excel file path"""
        self.df = pd.read_excel(excel_path)
        self.excel_path = excel_path
        
        # Parse document_date if it exists
        if 'document_date' in self.df.columns:
            self.df['document_date'] = pd.to_datetime(self.df['document_date'])
        
        self._prepare_dataset_info()
    
    def _prepare_dataset_info(self):
        """Prepare metadata about the dataset for the LLM"""
        self.dataset_info = {
            'total_rows': len(self.df),
            'columns': list(self.df.columns),
            'date_range': {
                'min_year': int(self.df['year'].min()),
                'max_year': int(self.df['year'].max()),
                'years_available': sorted(self.df['year'].unique().tolist())
            },
            'sample_data': self.df.head(3).to_dict('records'),
            'column_descriptions': {
                'result': 'Compliance result in Arabic (مطابق = compliant, غير مطابق = non-compliant)',
                'limits': 'Maximum allowed pesticide limit',
                'reading': 'Actual pesticide reading/measurement',
                'pesticide': 'Pesticide name (original)',
                'pesticide_standardized': 'Standardized pesticide name',
                'pesticide_group': 'Chemical group of pesticide',
                'vegetable_arabic': 'Vegetable name in Arabic',
                'vegetable_english': 'Vegetable name in English',
                'vegetable_category': 'Category of vegetable',
                'document_date': 'Date of the test',
                'year': 'Year of test',
                'month': 'Month of test',
                'quarter': 'Quarter of test',
                'season': 'Season code',
                'week_of_year': 'Week number in year',
                'is_compliant': '1 if compliant, 0 if non-compliant',
                'exceedance_ratio': 'Ratio of reading to limit',
                'risk_score': 'Calculated risk score',
                'log_reading': 'Log-transformed reading',
                'log_limits': 'Log-transformed limits'
            },
            'unique_values': {
                'pesticides': self.df['pesticide_standardized'].nunique(),
                'vegetables': self.df['vegetable_english'].nunique(),
                'pesticide_groups': self.df['pesticide_group'].nunique()
            },
            'statistics': {
                'total_tests': len(self.df),
                'compliant_tests': int(self.df['is_compliant'].sum()),
                'non_compliant_tests': int((self.df['is_compliant'] == 0).sum()),
                'compliance_rate': f"{(self.df['is_compliant'].mean() * 100):.2f}%"
            }
        }
    
    def get_dataset_summary(self) -> str:
        """Return a human-readable dataset summary"""
        info = self.dataset_info
        summary = f"""
Dataset Summary:
================
Total Records: {info['total_rows']:,}
Date Range: {info['date_range']['min_year']} - {info['date_range']['max_year']}
Years Available: {', '.join(map(str, info['date_range']['years_available']))}

Content:
- {info['unique_values']['pesticides']} unique pesticides
- {info['unique_values']['vegetables']} unique vegetables
- {info['unique_values']['pesticide_groups']} pesticide groups

Compliance Statistics:
- Total Tests: {info['statistics']['total_tests']:,}
- Compliant: {info['statistics']['compliant_tests']:,}
- Non-Compliant: {info['statistics']['non_compliant_tests']:,}
- Compliance Rate: {info['statistics']['compliance_rate']}

Available Columns: {', '.join(info['columns'])}
"""
        return summary
    
    def generate_query_code(self, question: str) -> str:
        """
        Generate the prompt for an LLM to create pandas code
        In a real system, you'd send this to Claude API
        """
        
        prompt = f"""You are a data analyst expert. Generate Python pandas code to answer the following question about pesticide testing data.

DATASET INFORMATION:
{json.dumps(self.dataset_info, indent=2, default=str)}

IMPORTANT RULES:
1. The dataframe is already loaded as 'df'
2. Only use pandas operations, numpy if needed
3. Return the final result in a variable called 'result'
4. Make the result human-readable (formatted tables, clear numbers)
5. Handle edge cases (empty results, divisions by zero)
6. Use proper error handling
7. For Arabic text (result column): مطابق = compliant, غير مطابق = non-compliant

USER QUESTION: {question}

Generate ONLY the Python code, no explanations. The code should:
- Answer the question accurately
- Be efficient
- Handle errors gracefully
- Produce readable output

Code:
```python
import pandas as pd
import numpy as np

# Your code here
# df is already loaded
"""
        return prompt
    
    def execute_query(self, code: str) -> Any:
        """
        Execute the generated pandas code safely
        """
        try:
            # Create a safe execution environment
            local_vars = {
                'df': self.df.copy(),
                'pd': pd,
                'np': __import__('numpy'),
                'result': None
            }
            
            # Execute the code
            exec(code, {}, local_vars)
            
            return local_vars.get('result', 'No result generated')
        
        except Exception as e:
            return f"Error executing query: {str(e)}"
    
    def quick_stats(self):
        """Get quick statistics"""
        stats = {
            'by_year': self.df.groupby('year').agg({
                'is_compliant': ['count', 'sum', 'mean']
            }).round(3),
            'by_vegetable': self.df.groupby('vegetable_english').agg({
                'is_compliant': ['count', 'mean']
            }).sort_values(('is_compliant', 'count'), ascending=False).head(10),
            'by_pesticide': self.df.groupby('pesticide_standardized').agg({
                'is_compliant': ['count', 'mean']
            }).sort_values(('is_compliant', 'count'), ascending=False).head(10)
        }
        return stats
    
    def answer_common_questions(self, question_type: str) -> Any:
        """Pre-built answers for common questions"""
        
        if question_type == 'compliance_by_year':
            result = self.df.groupby('year').agg({
                'is_compliant': ['count', 'sum', lambda x: (x.mean() * 100)]
            }).round(2)
            result.columns = ['Total Tests', 'Compliant', 'Compliance %']
            return result
        
        elif question_type == 'worst_vegetables':
            result = self.df.groupby('vegetable_english').agg({
                'is_compliant': ['count', 'mean']
            })
            result.columns = ['Total Tests', 'Compliance Rate']
            result['Non-Compliance Rate'] = (1 - result['Compliance Rate']) * 100
            result = result[result['Total Tests'] >= 5]  # At least 5 tests
            return result.sort_values('Non-Compliance Rate', ascending=False).head(10)
        
        elif question_type == 'worst_pesticides':
            result = self.df.groupby('pesticide_standardized').agg({
                'is_compliant': ['count', 'mean']
            })
            result.columns = ['Total Tests', 'Compliance Rate']
            result['Non-Compliance Rate'] = (1 - result['Compliance Rate']) * 100
            result = result[result['Total Tests'] >= 5]
            return result.sort_values('Non-Compliance Rate', ascending=False).head(10)
        
        elif question_type == 'trends':
            result = self.df.groupby(['year', 'quarter']).agg({
                'is_compliant': ['count', 'mean']
            }).round(3)
            result.columns = ['Tests', 'Compliance Rate']
            return result
        
        elif question_type == 'high_risk':
            high_risk = self.df[self.df['exceedance_ratio'] > 2].copy()
            high_risk = high_risk.sort_values('exceedance_ratio', ascending=False)
            return high_risk[['year', 'month', 'vegetable_english', 'pesticide_standardized', 
                             'reading', 'limits', 'exceedance_ratio']].head(20)
        
        else:
            return "Unknown question type"


# Example usage functions
def demo_system(excel_path: str):
    """Demonstrate the query system"""
    
    print("="*70)
    print("PESTICIDE DATA QUERY SYSTEM")
    print("="*70)
    
    # Initialize system
    system = PesticideDataQuerySystem(excel_path)
    
    # Show summary
    print(system.get_dataset_summary())
    
    # Common questions
    print("\n" + "="*70)
    print("EXAMPLE QUERIES")
    print("="*70)
    
    print("\n1. Compliance by Year:")
    print(system.answer_common_questions('compliance_by_year'))
    
    print("\n2. Worst Performing Vegetables (by non-compliance):")
    print(system.answer_common_questions('worst_vegetables'))
    
    print("\n3. Most Problematic Pesticides:")
    print(system.answer_common_questions('worst_pesticides'))
    
    print("\n4. High Risk Cases (reading > 2x limit):")
    print(system.answer_common_questions('high_risk'))
    
    return system


if __name__ == "__main__":
    # Run demo
    system = demo_system('/mnt/user-data/uploads/processed_data_output.xlsx')