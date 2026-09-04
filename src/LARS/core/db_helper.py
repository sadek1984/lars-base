"""
🗄️ LARS DuckDB Database Helper
================================
Provides database connection and query utilities for LARS

Features:
- Connection management
- SQL query execution
- Schema-Only Prompting support
- Data insertion for new samples

Usage:
    from db_helper import LARSDatabase
    
    db = LARSDatabase()
    df = db.query("SELECT * FROM chemistry WHERE YEAR(\"التاريخ\") = 2024")
    db.close()

Author: LARS Development Team
Date: 2025-12-14
"""

import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Any, List
import io


class LARSDatabase:
    """
    Database helper class for LARS application
    Uses DuckDB for fast analytical queries
    Now using CHEMISTRY_TIDY table (transformed data with separate columns)
    """
    
    # Default table name - using transformed tidy data
    DEFAULT_TABLE = 'chemistry_tidy'
    
    def __init__(self, db_path: Optional[str] = None, read_only: bool = True, table: str = None):
        """
        Initialize database connection
        
        Args:
            db_path: Path to DuckDB file. If None, uses default location.
            read_only: If True, opens in read-only mode (faster for queries)
            table: Table name to use (default: 'chemistry')
        """
        if db_path is None:
            # Database is in data/ folder (../data/ from core/)
            db_path = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
        
        self.db_path = Path(db_path)
        self.read_only = read_only
        self.table_name = table or self.DEFAULT_TABLE
        self._connection = None
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
    
    @property
    def connection(self):
        """Lazy connection - only connect when needed"""
        if self._connection is None:
            self._connection = duckdb.connect(
                str(self.db_path), 
                read_only=self.read_only
            )
        return self._connection
    
    def query(self, sql: str) -> pd.DataFrame:
        """
        Execute SQL query and return results as DataFrame
        
        Args:
            sql: SQL query string
            
        Returns:
            pandas DataFrame with results
        """
        return self.connection.execute(sql).df()
    
    def execute(self, sql: str, params: tuple = None) -> Any:
        """
        Execute SQL statement (for INSERT, UPDATE, DELETE)
        
        Args:
            sql: SQL statement
            params: Optional tuple of parameters
            
        Returns:
            Query result
        """
        if params:
            return self.connection.execute(sql, params)
        return self.connection.execute(sql)
    
    def insert_sample(self, sample_data: Dict[str, Any]) -> bool:
        """
        Insert a new sample into the database
        
        Args:
            sample_data: Dictionary with column names as keys
            
        Returns:
            True if successful
        """
        if self.read_only:
            raise PermissionError("Database opened in read-only mode")
        
        columns = list(sample_data.keys())
        placeholders = ', '.join(['?' for _ in columns])
        values = tuple(sample_data.values())
        
        sql = f"INSERT INTO {self.table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        self.execute(sql, values)
        return True
    
    def get_dataframe(self) -> pd.DataFrame:
        """
        Get entire table as DataFrame
        (For compatibility with existing code)
        """
        return self.query(f"SELECT * FROM {self.table_name}")
    
    def close(self):
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # =========================================================================
    # 🔒 SCHEMA-ONLY PROMPTING SUPPORT (Updated for Chemistry Table)
    # =========================================================================
    
    def get_schema_info(self) -> str:
        """
        Get database schema information for Schema-Only Prompting
        Returns metadata WITHOUT exposing actual sensitive data
        
        Returns:
            Formatted schema string for AI prompts
        """
        schema_parts = []
        
        # 1. Get column information
        columns_df = self.query(f"DESCRIBE {self.table_name}")
        schema_parts.append("**Column Information:**")
        schema_parts.append("| Column | Type |")
        schema_parts.append("|--------|------|")
        for _, row in columns_df.iterrows():
            schema_parts.append(f"| {row['column_name']} | {row['column_type']} |")
        
        # 2. Get row count
        count = self.query(f"SELECT COUNT(*) as count FROM {self.table_name}")['count'].iloc[0]
        schema_parts.append(f"\n**Total Records:** {count:,} samples")
        
        # 3. Get sample type statistics
        sample_type_info = self.query(f"""
            SELECT 
                "نوع العينة" as sample_type,
                COUNT(*) as count
            FROM {self.table_name}
            WHERE "نوع العينة" IS NOT NULL
            GROUP BY "نوع العينة"
            ORDER BY count DESC
            LIMIT 10
        """)
        
        schema_parts.append("\n**Sample Types (نوع العينة):**")
        for _, row in sample_type_info.iterrows():
            schema_parts.append(f"- {row['sample_type']}: {row['count']} samples")
        
        # 4. Get test type statistics
        test_type_info = self.query(f"""
            SELECT 
                "نوع الاختبار" as test_type,
                COUNT(*) as count
            FROM {self.table_name}
            GROUP BY "نوع الاختبار"
            ORDER BY count DESC
        """)
        
        schema_parts.append("\n**Test Types (نوع الاختبار):**")
        for _, row in test_type_info.iterrows():
            schema_parts.append(f"- {row['test_type']}: {row['count']} samples")
        
        # 5. Get result statistics
        result_info = self.query(f"""
            SELECT 
                "ch_tracking.نتيجة العينة
Result" as result,
                COUNT(*) as count
            FROM {self.table_name}
            WHERE "ch_tracking.نتيجة العينة
Result" IS NOT NULL
            GROUP BY "ch_tracking.نتيجة العينة
Result"
        """)
        
        schema_parts.append("\n**Result Types (نتيجة العينة):**")
        for _, row in result_info.iterrows():
            if row['result']:
                schema_parts.append(f"- {row['result']}: {row['count']} samples")
        
        # 6. Get neighborhood info
        neighborhood_info = self.query(f"""
            SELECT COUNT(DISTINCT "الحى") as unique_neighborhoods
            FROM {self.table_name}
        """)
        schema_parts.append(f"\n**Unique Neighborhoods (الحى):** {neighborhood_info['unique_neighborhoods'].iloc[0]}")
        
        # 7. Add value patterns
        schema_parts.append("""
**Column Descriptions:**
- `كود العينة`: Sample code (unique identifier)
- `التاريخ`: Sample date (TIMESTAMP)
- `اسم العينة`: Sample name (e.g., 'طماطم', 'بقدونس', 'جزر')
- `نوع العينة`: Sample type (e.g., 'خضراوات', 'فواكهة', 'توابل', 'مكسرات', 'حبوب')
- `تصنيف العينة`: Sample classification (e.g., 'خدمية', 'تجارية')
- `نوع الاختبار`: Test type (e.g., 'متبقيات مبيدات', 'سموم فطرية')
- `اسم المنشاة`: Facility name
- `اسم البلدية`: Municipality name
- `الحى`: Neighborhood name
- `رقم الرخصة`: License number (sensitive)
- `ch_tracking.نتيجة العينة\\nResult`: Result - 'compliant (مطابقة)' or 'non-compliant (غير مطابقة)'
- `ch_tracking.ملوث 1-10\\nName, Conc, Limit`: Contaminant info (name, concentration, limit)
""")
        
        return '\n'.join(schema_parts)
    
    def get_sql_prompt(self, user_query: str) -> str:
        """
        Generate a complete prompt for AI to generate SQL queries
        Uses Schema-Only Prompting (no actual data exposed)
        
        Args:
            user_query: User's question in natural language
            
        Returns:
            Complete prompt for AI
        """
        schema_info = self.get_schema_info()
        
        prompt = f"""Generate a SQL query to answer this question about the CHEMISTRY testing database (الكيمياء).

🔒 Database Schema (Metadata Only - No Actual Data Exposed):

{schema_info}

⚠️ PRIVACY NOTE: You are receiving ONLY schema information.
DO NOT assume specific values exist. Write generic filtering/aggregation code.

**TABLE NAME:** chemistry

**IMPORTANT COLUMN NAMES (with special characters):**
- `"التاريخ"` - Date column
- `"اسم العينة"` - Sample name (e.g., طماطم, بقدونس)
- `"نوع العينة"` - Sample type (e.g., خضراوات, فواكهة)
- `"نوع الاختبار"` - Test type (e.g., متبقيات مبيدات, سموم فطرية)
- `"الحى"` - Neighborhood
- `"اسم البلدية"` - Municipality
- `"ch_tracking.نتيجة العينة\\nResult"` - Result (compliant/non-compliant)
- `"ch_tracking.ملوث 1\\nName, Conc, Limit"` - Contaminant 1 info

**User Question:** {user_query}

**IMPORTANT RULES:**
1. Use standard SQL syntax (DuckDB compatible)
2. ALWAYS use double quotes for column names: "اسم العينة"
3. For Arabic text matching, use: WHERE "column" LIKE '%طماطم%'
4. For compliance: "ch_tracking.نتيجة العينة\\nResult" LIKE '%compliant%' or '%مطابقة%'
5. For date filtering: WHERE YEAR("التاريخ") = 2024
6. Always include ORDER BY for sorted results
7. Use LIMIT for large result sets

**EXAMPLE QUERIES:**

-- Count samples by type
SELECT 
    "نوع العينة" as sample_type,
    COUNT(*) as total_samples
FROM chemistry
GROUP BY "نوع العينة"
ORDER BY total_samples DESC;

-- Vegetables with test results
SELECT 
    "اسم العينة" as sample_name,
    "نوع الاختبار" as test_type,
    "ch_tracking.نتيجة العينة
Result" as result,
    COUNT(*) as count
FROM chemistry
WHERE "نوع العينة" = 'خضراوات'
GROUP BY "اسم العينة", "نوع الاختبار", "ch_tracking.نتيجة العينة
Result"
ORDER BY count DESC;

-- Compliance rate by neighborhood
SELECT 
    "الحى" as neighborhood,
    COUNT(*) as total,
    SUM(CASE WHEN "ch_tracking.نتيجة العينة
Result" LIKE '%compliant%' AND "ch_tracking.نتيجة العينة
Result" NOT LIKE '%non-compliant%' THEN 1 ELSE 0 END) as compliant,
    SUM(CASE WHEN "ch_tracking.نتيجة العينة
Result" LIKE '%non-compliant%' THEN 1 ELSE 0 END) as violations
FROM chemistry
WHERE "الحى" IS NOT NULL
GROUP BY "الحى"
ORDER BY total DESC;

-- Samples with contaminants detected
SELECT 
    "اسم العينة" as sample_name,
    "ch_tracking.ملوث 1
Name, Conc, Limit" as contaminant_1,
    "ch_tracking.نتيجة العينة
Result" as result
FROM chemistry
WHERE "ch_tracking.ملوث 1
Name, Conc, Limit" IS NOT NULL
LIMIT 20;

Generate ONLY the SQL query wrapped in ```sql``` markers:"""
        
        return prompt


# Singleton instance for easy import
_db_instance: Optional[LARSDatabase] = None

def get_database(read_only: bool = True, table: str = 'chemistry_tidy') -> LARSDatabase:
    """
    Get database instance (singleton pattern)
    
    Args:
        read_only: If True, opens in read-only mode
        table: Table name to use (default: 'chemistry')
        
    Returns:
        LARSDatabase instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = LARSDatabase(read_only=read_only, table=table)
    return _db_instance


def execute_sql(sql: str) -> pd.DataFrame:
    """
    Quick helper to execute SQL and return DataFrame
    
    Args:
        sql: SQL query
        
    Returns:
        pandas DataFrame
    """
    db = get_database()
    return db.query(sql)


# Pesticide mapping for Arabic → English translation
PESTICIDE_MAPPING = {
    'البايفنثرن': 'Bifenthrin',
    'الكلوربيريفوس': 'Chlorpyrifos',
    'الديمثويت': 'Dimethoate',
    'اللامبدا': 'Lambda-cyhalothrin',
    'الميثوميل': 'Methomyl',
    'الكاربندزيم': 'Carbendazim',
    'الإيماميكتين': 'Emamectin',
    'الأيميداكلوبريد': 'Imidacloprid',
    'الثيامثوكسام': 'Thiamethoxam',
    'البروفيزين': 'Buprofezin',
    'الأباميكتين': 'Abamectin',
    'الأسيتامبريد': 'Acetamiprid',
    'الدلتامثرين': 'Deltamethrin',
    'السيبرمثرين': 'Cypermethrin'
}


if __name__ == "__main__":
    # Test the database helper
    print("🧪 Testing LARS Database Helper (Chemistry Table)...")
    
    db = LARSDatabase()
    
    # Test basic query
    print("\n1. Testing basic query:")
    result = db.query("SELECT COUNT(*) as count FROM chemistry")
    print(f"   Total records: {result['count'].iloc[0]}")
    
    # Test sample types
    print("\n2. Testing sample types query:")
    result = db.query("""
        SELECT "نوع العينة" as sample_type, COUNT(*) as count 
        FROM chemistry 
        WHERE "نوع العينة" IS NOT NULL
        GROUP BY "نوع العينة" 
        ORDER BY count DESC
        LIMIT 5
    """)
    print(result)
    
    # Test schema info
    print("\n3. Testing schema info (Schema-Only Prompting):")
    schema = db.get_schema_info()
    print(schema[:500] + "...")
    
    # Test SQL prompt generation
    print("\n4. Testing SQL prompt generation:")
    prompt = db.get_sql_prompt("ما هي أنواع الخضروات في حي المنار؟")
    print(f"   Prompt length: {len(prompt)} characters")
    
    db.close()
    print("\n✅ All tests passed!")

