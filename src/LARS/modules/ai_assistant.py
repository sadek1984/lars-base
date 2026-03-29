import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import json
import requests
import duckdb
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import random
from modules.mappings import PESTICIDE_AR_TO_EN, translate_pesticide
# Bilingual translation utilities (Arabic <-> English)
from modules.translation_utils import (
    get_language_system_prompt
)
import logging

# Import risk window components
try:
    from modules.risk_windows import (
        show_health_risk_window,
        show_quality_index_window,
        process_triggered_query
    )
    from modules.risk_assessment_service import detect_query_type
    RISK_WINDOWS_AVAILABLE = True
except ImportError:
    RISK_WINDOWS_AVAILABLE = False

# Semantic pattern recognizer is used inside core_query_engine.py, no need to load it here at module level.



def _chart_cols(df):
    """Return (numeric_cols, text_cols) for a DataFrame."""
    return (
        df.select_dtypes(include=[np.number]).columns.tolist(),
        df.select_dtypes(include=['object']).columns.tolist(),
    )


def generate_bar_chart(df: pd.DataFrame, query: str):
    """Generate an interactive bar chart from DataFrame."""
    try:
        import plotly.graph_objects as go
        numeric_cols, text_cols = _chart_cols(df)
        if not numeric_cols:
            st.warning("⚠️ No numeric columns found for visualization")
            return
        x_col = text_cols[0] if text_cols else df.columns[0]
        y_col = numeric_cols[0]
        fig = go.Figure(data=[go.Bar(
            x=df[x_col], y=df[y_col],
            marker=dict(color=df[y_col], colorscale='Viridis', showscale=True),
            text=df[y_col], textposition='outside', texttemplate='%{text:.1f}'
        )])
        fig.update_layout(title=f"Bar Chart: {y_col} by {x_col}", xaxis_title=x_col,
                          yaxis_title=y_col, height=500, showlegend=False, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating bar chart: {e}")


def generate_line_chart(df: pd.DataFrame, query: str):
    """Generate an interactive line chart from DataFrame."""
    try:
        import plotly.graph_objects as go
        numeric_cols, text_cols = _chart_cols(df)
        if not numeric_cols:
            st.warning("⚠️ No numeric columns found for visualization")
            return
        x_col = text_cols[0] if text_cols else df.columns[0]
        y_col = numeric_cols[0]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='lines+markers',
                                  line=dict(color='#2e7d32', width=3),
                                  marker=dict(size=10, color='#4caf50'), name=y_col))
        fig.update_layout(title=f"Line Chart: {y_col} Trend", xaxis_title=x_col,
                          yaxis_title=y_col, height=500, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating line chart: {e}")


def generate_pie_chart(df: pd.DataFrame, query: str):
    """Generate an interactive pie chart from DataFrame."""
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        numeric_cols, text_cols = _chart_cols(df)
        if not numeric_cols or not text_cols:
            st.warning("⚠️ Need both text and numeric columns for pie chart")
            return
        labels_col, values_col = text_cols[0], numeric_cols[0]
        df_top = df.nlargest(10, values_col) if len(df) > 10 else df
        fig = go.Figure(data=[go.Pie(
            labels=df_top[labels_col], values=df_top[values_col], hole=0.3,
            textinfo='label+percent',
            marker=dict(colors=px.colors.sequential.Viridis, line=dict(color='white', width=2))
        )])
        fig.update_layout(title=f"Pie Chart: {values_col} Distribution", height=500, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating pie chart: {e}")

def generate_radar_chart(df: pd.DataFrame, query: str):
    """Generate an interactive radar chart from DataFrame."""
    try:
        import plotly.graph_objects as go
        numeric_cols, text_cols = _chart_cols(df)
        if not numeric_cols or not text_cols:
            st.warning("⚠️ Need both text and numeric columns for radar chart")
            return
        df_top = df.head(10)
        categories = df_top[text_cols[0]].tolist()
        def _norm(col):
            vals = df_top[col].tolist()
            m = max(vals) if max(vals) > 0 else 1
            return [(v / m) * 100 for v in vals]
        if len(numeric_cols) > 1:
            fig = go.Figure()
            for col in numeric_cols[:3]:
                fig.add_trace(go.Scatterpolar(r=_norm(col), theta=categories, fill='toself', name=col))
        else:
            fig = go.Figure(data=go.Scatterpolar(
                r=_norm(numeric_cols[0]), theta=categories, fill='toself',
                marker=dict(color='#4caf50'), line=dict(color='#2e7d32', width=2)
            ))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                          title="Radar Chart: Comparative Analysis", height=600, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("📊 Values are normalized to 0-100 scale for comparison")
    except Exception as e:
        st.error(f"Error generating radar chart: {e}")


def generate_scatter_plot(df: pd.DataFrame, query: str):
    """Generate an interactive scatter plot from DataFrame."""
    try:
        import plotly.express as px
        numeric_cols, text_cols = _chart_cols(df)
        if len(numeric_cols) < 2:
            st.warning("⚠️ Need at least 2 numeric columns for scatter plot")
            return
        x_col, y_col = numeric_cols[0], numeric_cols[1]
        size_col = numeric_cols[2] if len(numeric_cols) >= 3 else None
        color_col = text_cols[0] if text_cols else None
        fig = px.scatter(df, x=x_col, y=y_col, size=size_col, color=color_col,
                         title=f"Scatter Plot: {y_col} vs {x_col}",
                         height=600, hover_data=df.columns.tolist())
        fig.update_traces(marker=dict(line=dict(width=1, color='white'), opacity=0.7))
        fig.update_layout(xaxis_title=x_col, yaxis_title=y_col, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating scatter plot: {e}")

def process_data_query_sql(query: str, model, include_risk: bool = False):
    """
    Process data analysis queries using SQL + DuckDB.

    Priority 1 – Risk Windows : health-risk / quality-index triggers get their
                                 own analysis window rendered immediately.
    Priority 2 – CoreQueryEngine: pattern matching → intent routing →
                                   LLM SQL generation (Gemini / GPT / Ollama).

    This function is the Streamlit rendering layer only.
    All business logic lives in CoreQueryEngine.process_with_gemini_fallback().
    """
    query_lang = "english"

    # ================================================================
    # PRIORITY 1: Risk Windows (Health Risk Index / Quality Index)
    # ================================================================
    if RISK_WINDOWS_AVAILABLE:
        q_lower = query.lower()
        # Simple stat queries are handled by pattern matching — don't hijack them
        is_simple_stat = (
            any(x in q_lower for x in ["count", "number", "how many", "عدد", "كم", "نسبة"])
            and any(x in q_lower for x in ["limit", "above", "below", "allowed",
                                            "حد", "تجاوز", "مخالف", "راسب", "ناجح"])
        )

        if not is_simple_stat:
            try:
                trigger = detect_query_type(query)
                if trigger:
                    from modules.risk_windows import detect_sample_type
                    detected_sample = detect_sample_type(query)
                    con = get_duckdb_connection()
                    if con:
                        commodity = "Total Vegetables"
                        sample_filter = ""
                        if detected_sample:
                            commodity = detected_sample[0]
                            sample_filter = (
                                f"AND \"اسم العينة\" LIKE '%{detected_sample[1]}%'"
                            )
                            st.info(f"🔍 Filtering for: **{commodity}** ({detected_sample[1]})")

                        residue_df = con.execute(f"""
                            SELECT pesticide_name as name, concentration,
                                   limit_value as mrl, \"التاريخ\" as date,
                                   \"كود العينة\" as sample_code, is_detected
                            FROM chemistry_tidy
                            WHERE pesticide_name NOT IN ('NO DATA') {sample_filter}
                            ORDER BY \"التاريخ\" ASC LIMIT 2000
                        """).df()
                        con.close()
                        residue_data = residue_df.to_dict("records")

                        if trigger == "[TRIGGER_UI: HEALTH_RISK_WINDOW]":
                            st.info(
                                f"🏥 Health risk query — analyzing {len(residue_data)} records..."
                            )
                            for k, v in [
                                ("risk_residue_data",       residue_data),
                                ("risk_query",               query),
                                ("risk_commodity",           commodity),
                                ("risk_selected_commodity",  commodity),
                                ("risk_original_commodity",  commodity),
                                ("risk_show_window",         True),
                                ("iqr_show_window",          False),
                            ]:
                                st.session_state[k] = v
                            show_health_risk_window(residue_data, commodity, query=query)
                            return

                        elif trigger == "[TRIGGER_UI: QUALITY_INDEX_WINDOW]":
                            st.info(
                                f"📐 Quality index query — analyzing {len(residue_data)} records..."
                            )
                            for k, v in [
                                ("iqr_residue_data",        residue_data),
                                ("iqr_query",               query),
                                ("iqr_commodity",           commodity),
                                ("iqr_selected_commodity",  commodity),
                                ("iqr_original_commodity",  commodity),
                                ("iqr_show_window",         True),
                                ("risk_show_window",        False),
                            ]:
                                st.session_state[k] = v
                            show_quality_index_window(residue_data, commodity, query=query)
                            return

            except Exception as _e:
                logging.debug(f"Risk window check error: {_e}")

    # ================================================================
    # PRIORITY 2: CoreQueryEngine (patterns + intent + LLM SQL)
    # ================================================================
    try:
        from modules.core_query_engine import CoreQueryEngine

        if "core_query_engine" not in st.session_state:
            st.session_state.core_query_engine = CoreQueryEngine(enable_llm_fallback=False)
        engine = st.session_state.core_query_engine

        with st.spinner("🔍 Analyzing query..."):
            response_text, result_df, generated_sql = (
                engine.process_with_gemini_fallback(query, model)
            )

        _render_sql_query_result(response_text, result_df, generated_sql, query_lang)

    except Exception as exc:
        st.error(f"❌ Error: {exc}")
        with st.expander("🔍 Debug Details"):
            st.exception(exc)


def _render_sql_query_result(
    response_text: str,
    result_df,
    generated_sql,
    query_lang: str,
) -> None:
    """Render a CoreQueryEngine result with Streamlit UI components."""
    import numpy as np
    from modules.translation_utils import translate_dataframe

    is_unknown = (
        "Sorry, I couldn't fully understand" in response_text
        or "لم أتمكن من فهم" in response_text
    )

    if result_df is not None and not result_df.empty:
        st.success("✅ Query processed successfully!")
        st.markdown(response_text)

        # ── Optional summary metrics (best-effort, never crashes) ──
        try:
            metric_cols = [
                c for c in result_df.columns
                if any(
                    kw in str(c).lower()
                    for kw in ["total", "count", "above", "below", "violation", "عدد", "فوق", "تحت"]
                )
                and pd.api.types.is_numeric_dtype(result_df[c])
            ]
            if 0 < len(metric_cols) <= 4:
                cols_ui = st.columns(len(metric_cols))
                for i, col in enumerate(metric_cols):
                    cols_ui[i].metric(col, int(result_df[col].sum()))
        except Exception:
            pass

        st.dataframe(
            translate_dataframe(result_df, query_lang),
            use_container_width=True,
            hide_index=True,
        )
        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Results (CSV)",
            data=csv,
            file_name="lars_results.csv",
            mime="text/csv",
        )

    elif not is_unknown:
        st.markdown(response_text)

    else:
        st.warning("⚠️ Could not process this query.")
        st.info(
            "💡 Examples: 'how many tomato samples exceed limits' | "
            "'what pesticides in cucumber' | 'samples with 3 pesticides'"
        )

    if generated_sql:
        with st.expander("🔍 View Generated SQL"):
            st.code(generated_sql, language="sql")
            st.caption("This SQL was AI-generated and executed on DuckDB.")



def process_data_query(query: str, df: pd.DataFrame, model, include_risk: bool = False):
    """Process data analysis queries using Gemini with risk assessment option"""
    
    # Language definition for pandas query engine
    query_lang = "english"

    with st.spinner("🔄 Generating analysis code..."):
        try:
            # Enhanced prompt with risk assessment
            risk_instruction = ""
            if include_risk:
                risk_instruction = """
                
Also include risk assessment calculations:
- Calculate exceedance ratio (Result/MRL) 
- Add 'Risk_Level' column: High (>2x MRL), Medium (1-2x MRL), Low (<1x MRL)
- Include health risk indicators if possible
- Show risk summary statistics
"""
            
            # First, detect the query type to apply the right analysis approach
            query_lower = query.lower()
            
            # Detect query type
            is_trend_query = any(kw in query_lower for kw in ['trend', 'by year', 'over time', 'yearly', 'annual', 'year over year', 'from 2', 'to 2'])
            is_pesticide_query = any(kw in query_lower for kw in ['pesticide', 'which pesticide', 'top pesticide', 'most violations', 'pesticides with'])
            is_vegetable_arabic_query = any(kw in query for kw in ['الخضروات', 'عدد', 'فوق الحد', 'تحت الحد', 'الحي'])
            is_compliance_query = any(kw in query_lower for kw in ['compliance', 'compliant', 'non-compliant', 'violation rate'])
            
            # Build context-specific instructions
            if is_trend_query:
                specific_instructions = """
**QUERY TYPE DETECTED: TREND/YEARLY ANALYSIS**
- Group data by 'year' column
- Calculate counts, rates, or averages per year
- Result should show trends: year | metric1 | metric2 | ...
- Sort by year ascending
- DO NOT use Arabic column names for this query
- Example columns: 'year', 'total_samples', 'violations', 'compliance_rate'
"""
            elif is_pesticide_query:
                specific_instructions = """
**QUERY TYPE DETECTED: PESTICIDE ANALYSIS**
- Group by 'pesticide_standardized' or similar pesticide column
- Count violations using 'is_compliant' == 0 or 'result' containing 'غير مطابق'
- Show: pesticide name | total tests | violations | violation_rate
- Sort by violations or violation_rate descending
- DO NOT use Arabic column names unless specifically asked
- Show top 10-20 results
"""
            elif is_compliance_query:
                specific_instructions = """
**QUERY TYPE DETECTED: COMPLIANCE ANALYSIS**
- Calculate compliance metrics (compliant vs non-compliant)
- Use 'is_compliant' column if available (1=compliant, 0=violation)
- Or check 'result' column for 'مطابق' (compliant) vs 'غير مطابق' (non-compliant)
- Show rates as percentages
- Group by the relevant dimension (year, vegetable, pesticide, etc.)
"""
            elif is_vegetable_arabic_query:
                specific_instructions = """
**QUERY TYPE DETECTED: VEGETABLE STATISTICS (ARABIC FORMAT)**
- ONLY use this format when user explicitly asks in Arabic or wants Arabic output
- Group by vegetable (use 'vegetable_arabic' column)
- Calculate: total samples, above limit, below limit
- Use Arabic column names: 'عدد العينات', 'فوق الحد', 'تحت الحد'
- Filter by neighborhood if mentioned in query
"""
            else:
                specific_instructions = """
**QUERY TYPE: GENERAL ANALYSIS**
- Analyze the data based on the specific question
- Use appropriate groupby, aggregation, or filtering
- Use English column names unless Arabic is specifically requested
- Return a clear, well-formatted DataFrame
"""
            
            # 🔒 SCHEMA-ONLY PROMPTING - Privacy Protection
            # Generate DataFrame metadata WITHOUT exposing actual sensitive data
            import io
            
            # Get column types as markdown table
            dtypes_markdown = df.dtypes.to_frame('Type').to_markdown()
            
            # Get structure info (column names, non-null counts, memory usage)
            buffer = io.StringIO()
            df.info(buf=buffer)
            df_info_str = buffer.getvalue()
            
            # Get sample statistics (no actual values, just ranges/stats)
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            sample_stats = ""
            if numeric_cols:
                stats_df = df[numeric_cols].describe()
                # Get min, max, mean from the describe output (these are rows, not columns)
                stats_summary = stats_df.loc[['min', 'max', 'mean']]
                sample_stats = f"\nNumeric column ranges:\n{stats_summary.to_markdown()}"
            
            # 🆕 Add categorical column info (unique counts, NO actual values for sensitive columns)
            categorical_info = "\n**Categorical Columns Info:**\n"
            for col in df.select_dtypes(include=['object']).columns:
                unique_count = df[col].nunique()
                # Don't expose sensitive data like client names or sample IDs
                if col in ['client_name', 'sample_id', 'sample_code']:
                    categorical_info += f"- `{col}`: {unique_count} unique values (sensitive, not shown)\n"
                else:
                    categorical_info += f"- `{col}`: {unique_count} unique values\n"
            
            # 🆕 Add example value patterns (generic, non-sensitive)
            value_patterns = """
**Common Value Patterns (Generic Examples):**
- `vegetable_english`: English vegetable names (e.g., 'Tomato', 'Cucumber', 'Pepper')
- `vegetable_arabic`: Arabic vegetable names (e.g., 'طماطم', 'خيار', 'فلفل')
- `pesticide_standardized`: English pesticide names (use for filtering)
- `pesticide_arabic`: Arabic pesticide names (translate using pesticide_mapping)
- `neighborhood_arabic`: Arabic neighborhood names (e.g., 'الإسكان', 'الصفراء', 'الموطأ')
- `is_compliant`: 1=compliant (below limit), 0=violation (above limit)
- `result`: Arabic text 'مطابق' (compliant) or 'غير مطابق' (non-compliant)
"""
            
            prompt = f"""Generate pandas code to answer this question about the pesticide testing dataset.

**IMPORTANT: READ THE QUESTION CAREFULLY AND ANSWER EXACTLY WHAT IS ASKED!**

🔒 Dataset Schema (Metadata Only - No Actual Data Exposed):

**Column Information:**
{dtypes_markdown}

**DataFrame Structure:**
{df_info_str}
{sample_stats}
{categorical_info}
{value_patterns}

**Available Columns:** {list(df.columns)}
**Total Records:** {len(df)} samples
**Shape:** {df.shape}

⚠️ PRIVACY NOTE: You are receiving ONLY schema information (column names and types).
DO NOT assume specific values exist. Write generic filtering/aggregation code based on column names only.

User Question: {query}
{risk_instruction}

{specific_instructions}

**AVAILABLE VARIABLES IN SCOPE:**
- df: The main DataFrame (already loaded)
- pd: pandas module
- np: numpy module  
- query: The user's question as a string
- pesticide_mapping: Dictionary mapping Arabic pesticide names to English
  Example: pesticide_mapping['البايفنثرن'] = 'Bifenthrin'
  Use this to translate Arabic pesticide names when filtering

**CRITICAL REQUIREMENTS:**
1. ANSWER THE EXACT QUESTION - don't provide generic summaries
2. Store final result in variable 'result'
3. Execute code DIRECTLY - do NOT wrap in a function
4. Do NOT use 'return' statement
5. Handle missing values with .fillna() or dropna()
6. **STRING FILTERING - CRITICAL:** 
   - ALWAYS use `na=False` parameter with .str.contains() to handle NaN values
   - Example: df[df['vegetable_english'].str.contains('Cucumber', case=False, na=False)]
   - Never use .str.contains() without na=False parameter
7. **PESTICIDE NAME MATCHING:** 
   - If query mentions pesticide name in Arabic (e.g., 'البايفنثرن'), use pesticide_mapping
   - Example: pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')
   - Then filter: df[df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False)]

**KEY COLUMNS TO USE:**
- 'year' - for yearly analysis
- 'is_compliant' - 1=compliant, 0=violation
- 'pesticide_standardized' - pesticide name
- 'vegetable_english' - vegetable name in English
- 'reading' - measured value
- 'limits' - maximum allowed limit

**EXAMPLE CODE PATTERNS:**

For "compliance trends by year":
```python
result = df.groupby('year').agg(
    total_samples=('is_compliant', 'count'),
    compliant=('is_compliant', 'sum'),
    violations=('is_compliant', lambda x: (x == 0).sum())
).reset_index()
result['compliance_rate'] = (result['compliant'] / result['total_samples'] * 100).round(2)
result = result.sort_values('year')
```

For "pesticides with most violations":
```python
result = df[df['is_compliant'] == 0].groupby('pesticide_standardized').size().reset_index(name='violations')
result = result.sort_values('violations', ascending=False).head(15)
```

For "total number of cucumber samples" (simple count):
```python
# Count total samples for cucumber (IMPORTANT: use na=False to handle NaN)
cucumber_samples = df[df['vegetable_english'].str.contains('Cucumber', case=False, na=False)]
total_count = len(cucumber_samples)

# Create result DataFrame
result = pd.DataFrame({{
    'الخضار': ['خيار (Cucumber)'],
    'عدد العينات الكلي': [total_count]
}})
```

For "tomato samples with Bifenthrin above/below limit" (Arabic query):
```python
# Extract pesticide name from Arabic
pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')

# Filter for tomato and this pesticide (IMPORTANT: use na=False)
filtered = df[
    (df['vegetable_english'].str.contains('Tomato', case=False, na=False)) &
    (df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False))
].copy()

# Calculate above/below limit
above_limit = (filtered['is_compliant'] == 0).sum()
below_limit = (filtered['is_compliant'] == 1).sum()

# Create result DataFrame
result = pd.DataFrame({{
    'الخضار': ['الطماطم'],
    'المبيد': [pesticide_name],
    'عدد العينات': [len(filtered)],
    'فوق الحد': [above_limit],
    'تحت الحد': [below_limit]
}})
```

For "vegetables in neighborhood with compliance stats" (complex Arabic query):
```python
# Example: "ما هي انواع الخضروات الموجودة في حي الاسكان و ما عددها و ماهي العينات فوق الحد المسموح وتحت الحد المسموح"
# Filter by neighborhood (IMPORTANT: use na=False)
neighborhood_data = df[df['neighborhood_arabic'].str.contains('الإسكان', case=False, na=False)].copy()

# Group by vegetable and calculate compliance stats
result = neighborhood_data.groupby('vegetable_arabic').agg(
    عدد_العينات=('vegetable_arabic', 'count'),
    فوق_الحد=('is_compliant', lambda x: (x == 0).sum()),
    تحت_الحد=('is_compliant', lambda x: (x == 1).sum())
).reset_index()

# Rename columns for clarity
result.columns = ['الخضار', 'عدد العينات', 'فوق الحد', 'تحت الحد']
result = result.sort_values('عدد العينات', ascending=False)
```

For "vegetables affected by pesticide with compliance" (Arabic query):
```python
# Example: "ما هي الخضروات التي يشملها مبيد البايفنثرن و ماهي العينات تحت الحد و فوق الحد المسموح"
# Translate pesticide name
pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')

# Filter by pesticide
pesticide_data = df[df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False)].copy()

# Group by vegetable and calculate compliance
result = pesticide_data.groupby('vegetable_arabic').agg(
    عدد_العينات=('vegetable_arabic', 'count'),
    تحت_الحد=('is_compliant', lambda x: (x == 1).sum()),
    فوق_الحد=('is_compliant', lambda x: (x == 0).sum())
).reset_index()

result.columns = ['الخضار', 'عدد العينات', 'تحت الحد', 'فوق الحد']
result = result.sort_values('عدد العينات', ascending=False)
```

Generate ONLY the Python code wrapped in ```python``` markers:"""


            # Generate response using DeepSeek (first priority) or Gemini (fallback)
            generated_text = ""
            
            try:
                # Check if it looks like an OpenAI/DeepSeek client
                if hasattr(model, 'chat') and hasattr(model.chat, 'completions'):
                    # Get model name from session state (either gpt-4o-mini or qwen2.5:7b)
                    model_name = st.session_state.get('model_name', 'gpt-4o-mini')
                    
                    response = model.chat.completions.create(
                        model=model_name,  # Use dynamic model name
                        messages=[
                            {"role": "system", "content": "You are a Python data analysis expert. Output ONLY python code. 'df' (DataFrame) and 'query' (str) are already defined. Do not define functions."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.0
                    )
                    generated_text = response.choices[0].message.content
                else:
                    # Assume Gemini GenerativeModel
                    response = model.generate_content(prompt)
                    generated_text = response.text
            except Exception as gen_error:
                logging.error(f"LLM generation failed: {gen_error}")
                st.warning(
                    "⚠️ AI assistant is temporarily unavailable. "
                    "Please try again in a moment, or rephrase your question."
                )
                return

            code_match = re.search(r'```python\n(.*?)```', generated_text, re.DOTALL)
            
            if code_match:
                generated_code = code_match.group(1).strip()
            else:
                code_match = re.search(r'```\n(.*?)```', generated_text, re.DOTALL)
                if code_match:
                    generated_code = code_match.group(1).strip()
                else:
                    generated_code = generated_text.strip()
            
            exec_globals = {
                'df': df.copy(),
                'pd': pd,
                'np': np,
                'query': query,
                'pesticide_mapping': PESTICIDE_AR_TO_EN,
                'result': None
            }
            
            exec(generated_code, exec_globals)
            
            result = exec_globals.get('result')
            
            # Store results in session state for persistence across button clicks
            st.session_state.last_query_result = result
            st.session_state.last_query = query
            st.session_state.last_generated_code = generated_code
            st.session_state.last_include_risk = include_risk
            
            st.success("✅ Analysis completed!")
            st.markdown("### 📊 Results:")
            
            # Always show generated code when debugging (moved up for None results)
            if result is None:
                st.warning("⚠️ The generated code did not assign a value to the 'result' variable. Check the code below:")
                st.code(generated_code, language='python')
                st.info("""
                **Tip:** The AI should assign the final output to a variable called `result`. 
                Example: `result = df.groupby(...).agg(...)`
                """)
            elif isinstance(result, pd.DataFrame):
                # Auto-translate for English queries
                result = translate_dataframe(result, query_lang)
                # Smart metrics display based on result type
                result_cols = set(result.columns)
                
                # Type 1: Arabic vegetable statistics format
                if 'vegetable_arabic' in result_cols and 'عدد العينات' in result_cols:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        try:
                            total = result['عدد العينات'].sum() if pd.api.types.is_numeric_dtype(result['عدد العينات']) else len(result)
                            st.metric("🟢 Total Samples", total)
                        except:
                            st.metric("🟢 Total Samples", len(result))
                    with col2:
                        try:
                            above = result['فوق الحد'].sum() if 'فوق الحد' in result_cols else 0
                            st.metric("🔴 Above Limit", above)
                        except:
                            st.metric("🔴 Above Limit", "N/A")
                    with col3:
                        try:
                            below = result['تحت الحد'].sum() if 'تحت الحد' in result_cols else 0
                            st.metric("🟡 Below Limit", below)
                        except:
                            st.metric("🟡 Below Limit", "N/A")
                
                # Type 2: Yearly trend data
                elif 'year' in result_cols and len(result) <= 10:
                    cols = result_cols - {'year'}
                    metric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(result[c])]
                    if metric_cols:
                        display_cols = metric_cols[:4]  # Show up to 4 metrics
                        metric_columns = st.columns(len(display_cols))
                        for i, col_name in enumerate(display_cols):
                            with metric_columns[i]:
                                try:
                                    if 'rate' in col_name.lower() or 'percent' in col_name.lower():
                                        latest = result[col_name].iloc[-1]
                                        st.metric(f"📈 Latest {col_name.replace('_', ' ').title()}", f"{latest:.1f}%")
                                    else:
                                        total = result[col_name].sum()
                                        st.metric(f"📊 Total {col_name.replace('_', ' ').title()}", f"{total:,.0f}")
                                except:
                                    pass
                
                # Type 3: Pesticide/violation analysis
                elif 'pesticide_standardized' in result_cols or 'pesticide' in str(result_cols).lower():
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🧪 Pesticides Analyzed", len(result))
                    with col2:
                        viol_col = [c for c in result_cols if 'violation' in c.lower()]
                        if viol_col:
                            total_violations = result[viol_col[0]].sum()
                            st.metric("⚠️ Total Violations", f"{total_violations:,.0f}")
                
                # Type 4: Generic result - just show row count
                else:
                    st.metric("📋 Results Found", len(result))
                
                st.dataframe(result, use_container_width=True)
                
                # ADDED: Show detailed individual samples for vegetable/neighborhood queries
                if 'vegetable_arabic' in result_cols and 'عدد العينات' in result_cols:
                    st.markdown("---")
                    st.markdown("### 📋 Detailed Individual Samples")
                    st.caption("Showing all individual test samples (not grouped)")
                    
                    # Try to re-query the original data to show individual samples
                    try:
                        # Extract neighborhood from query if present
                        neighborhood_keywords = {
                            'الاسكان': 'Al Iskan',
                            'الموطأ': 'Al Mowata', 
                            'الصفراء': 'Al Safra',
                            'الأفق': 'Al Ufuq',
                            'الريان': 'Al Rayyan',
                            'السلام': 'Al Salam'
                        }
                        
                        neighborhood_found = None
                        for arabic, english in neighborhood_keywords.items():
                            if arabic in query:
                                neighborhood_found = english
                                break
                        
                        if neighborhood_found and 'neighborhood_english' in df.columns:
                            # Filter for this specific neighborhood
                            detailed_df = df[df['neighborhood_english'] == neighborhood_found].copy()
                            
                            # Select relevant columns
                            detail_cols = []
                            if 'vegetable_arabic' in detailed_df.columns:
                                detail_cols.append('vegetable_arabic')
                            if 'pesticide_standardized' in detailed_df.columns:
                                detail_cols.append('pesticide_standardized')
                            if 'reading' in detailed_df.columns:
                                detail_cols.append('reading')
                            if 'limits' in detailed_df.columns:
                                detail_cols.append('limits')
                            if 'result' in detailed_df.columns:
                                detail_cols.append('result')
                            if 'is_compliant' in detailed_df.columns:
                                detail_cols.append('is_compliant')
                            if 'date' in detailed_df.columns:
                                detail_cols.append('date')
                            
                            if detail_cols:
                                detailed_display = detailed_df[detail_cols].copy()
                                
                                # Add above/below limit indicator
                                if 'is_above_limit' in detailed_display.columns:
                                    detailed_display['حالة العينة'] = detailed_display['is_above_limit'].map({
                                        1: '🔴 فوق الحد',
                                        0: '🟢 تحت الحد'
                                    })
                                elif 'is_compliant' in detailed_display.columns:
                                    # Fallback for old data
                                    detailed_display['حالة العينة'] = detailed_display['is_compliant'].map({
                                        0: '🔴 فوق الحد',
                                        1: '🟢 تحت الحد'
                                    })
                                
                                st.info(f"📊 Total individual samples found: **{len(detailed_display)}** samples")
                                st.dataframe(detailed_display, use_container_width=True)
                                
                                # Add download button for detailed data
                                csv = detailed_display.to_csv(index=False).encode('utf-8-sig')
                                st.download_button(
                                    label="📥 Download Detailed Data (CSV)",
                                    data=csv,
                                    file_name=f"detailed_samples_{neighborhood_found}.csv",
                                    mime="text/csv",
                                )
                    except Exception as e:
                        st.info(f"💡 Showing grouped summary. Individual samples: {st.session_state.get('last_query', 'N/A')}")
                
                # Note: Chart buttons are now handled by display_stored_results_with_charts()
                # which is called after this function to persist across button clicks
                
                st.markdown("---")
                
                # Show risk assessment summary if applicable
                if include_risk and isinstance(result, pd.DataFrame):
                    if 'Risk_Level' in result.columns:
                        with st.expander("⚠️ Risk Assessment Summary"):
                            risk_counts = result['Risk_Level'].value_counts()
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("🔴 High Risk", risk_counts.get('High', 0))
                            with col2:
                                st.metric("🟡 Medium Risk", risk_counts.get('Medium', 0))
                            with col3:
                                st.metric("🟢 Low Risk", risk_counts.get('Low', 0))
                            
                            if 'Exceedance_Ratio' in result.columns:
                                max_exc = result['Exceedance_Ratio'].max()
                                avg_exc = result['Exceedance_Ratio'].mean()
                                st.write(f"**Max Exceedance:** {max_exc:.2f}x MRL")
                                st.write(f"**Average Exceedance:** {avg_exc:.2f}x MRL")
                
                csv = result.to_csv(index=False)
                st.download_button(
                    label="📥 Download Results as CSV",
                    data=csv,
                    file_name="analysis_results.csv",
                    mime="text/csv"
                )
                
                # Show code in expander for successful queries
                with st.expander("👨‍💻 View Generated Code"):
                    st.code(generated_code, language='python')
                    st.caption("This code was AI-generated and executed on your dataset")
                
            elif isinstance(result, (pd.Series, list, dict)):
                st.dataframe(pd.DataFrame(result), use_container_width=True)
                with st.expander("👨‍💻 View Generated Code"):
                    st.code(generated_code, language='python')
            else:
                st.write(result)
                with st.expander("👨‍💻 View Generated Code"):
                    st.code(generated_code, language='python')
            
            if 'chat_history' not in st.session_state:
                st.session_state.chat_history = []
            
            st.session_state.chat_history.append({
                'question': query,
                'result': result,
                'code': generated_code,
                'query_type': 'Data Analysis',
                'timestamp': pd.Timestamp.now(),
                'risk_assessment': include_risk
            })
            
        except Exception as e:
            st.error(f"❌ Error in analysis: {str(e)}")
            
            with st.expander("🔍 Debug Details"):
                st.code(f"Error: {str(e)}", language='python')
                if 'generated_code' in locals():
                    st.markdown("**Generated Code:**")
                    st.code(generated_code, language='python')


# In your display_stored_results_with_charts function:
def show_chat_page(api_client):
    """
    Fixed chat page that works with simple query system
    Just copy-paste this to replace your existing show_chat_page function
    
    Args:
        api_client: Your existing API client (or None)
    """
    
    st.header("💬 AI Assistant 🌱")
    st.caption("Powered by GPT-4o-mini - Ask questions in natural language")
    
    # ISO Document Management in Sidebar
    with st.sidebar:
        with st.expander("📄 ISO Document Upload"):
            uploaded_file = st.file_uploader(
                "Upload ISO Document",
                type=['pdf', 'docx', 'xlsx'],
                help="Limit 200MB per file"
            )
            
            doc_type = st.selectbox(
                "Document Type",
                ["Quality Manual", "Procedure", "Work Instruction", "Form"]
            )
            
        if uploaded_file is not None:
            # Show what will be uploaded
            st.caption(f"Will upload to project: {st.session_state.project_id}")
            
            if st.button("📤 Upload ISO Document", use_container_width=True, type="primary"):
                # Pass the project ID from session state
                upload_iso_document_ui(
                    api_client, 
                    uploaded_file, 
                    doc_type, 
                    st.session_state.project_id  # ✅ Use actual project ID
                )
            
        # Settings
        st.markdown("---")
        st.markdown("### ⚙️ Settings")
        
        risk_mode = st.radio(
            "Risk Assessment Mode",
            ["🔵 Auto-detect", "✅ Always On", "❌ Always Off"]
        )
        
        # Apply risk mode to detection
        if risk_mode == "✅ Always On":
            has_risk = True  # Force risk assessment
        elif risk_mode == "❌ Always Off":
            has_risk = False  # Disable risk assessment
        else:
            has_risk = None # Auto-detect will handle this later
        
        # 🆕 Query Engine Selection (SQL vs Pandas)
        st.markdown("---")
        st.markdown("### 🗄️ Query Engine")
        
        # Check if DuckDB database exists
        # Note: ai_assistant.py is in modules/, database is in ../data/
        db_path = Path(__file__).parent.parent / 'data' / 'lars_data.duckdb'
        db_exists = db_path.exists()

        
        if db_exists:
            query_engine = st.radio(
                "Choose Query Engine",
                ["🚀 SQL (DuckDB)", "🐼 Pandas"],
                help="SQL is faster and more secure. Pandas is the legacy option."
            )
            st.session_state.query_engine = 'sql' if 'SQL' in query_engine else 'pandas'
            
            if 'SQL' in query_engine:
                st.success("⚡ SQL mode: Faster queries with DuckDB")
            else:
                st.info("🐼 Pandas mode: Legacy query engine")
        else:
            st.warning("⚠️ DuckDB database not found. Using Pandas.")
            st.caption("Run `python migrate_db.py` to enable SQL mode.")
            st.session_state.query_engine = 'pandas'
        
        # ========================================================================
        # DATE FILTER SECTION
        # ========================================================================
        
        st.markdown("---")
        st.markdown("### 📅 Date Filter")
        
        # Initialize date filter state
        if 'date_filter_enabled' not in st.session_state:
            st.session_state.date_filter_enabled = False
        if 'date_filter_start' not in st.session_state:
            st.session_state.date_filter_start = pd.Timestamp('2022-01-01').date()
        if 'date_filter_end' not in st.session_state:
            st.session_state.date_filter_end = pd.Timestamp.now().date()
        
        # Enable/Disable toggle
        date_filter_enabled = st.checkbox(
            "🔘 Enable Date Filter",
            value=st.session_state.date_filter_enabled,
            help="When enabled, your queries will be filtered to the selected date range",
            key="date_filter_checkbox"
        )
        st.session_state.date_filter_enabled = date_filter_enabled
        
        if date_filter_enabled:
            from datetime import timedelta
            today = pd.Timestamp.now().date()
            
            # Quick Date Buttons
            st.markdown("**⚡ Quick Select:**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📅 Today", use_container_width=True, key="qd_today"):
                    st.session_state.date_filter_start = today
                    st.session_state.date_filter_end = today
                
                if st.button("📆 This Week", use_container_width=True, key="qd_week"):
                    st.session_state.date_filter_start = today - timedelta(days=today.weekday())
                    st.session_state.date_filter_end = today
            
            with col2:
                if st.button("🗓️ This Month", use_container_width=True, key="qd_month"):
                    st.session_state.date_filter_start = today.replace(day=1)
                    st.session_state.date_filter_end = today
                
                if st.button("📊 Last 3 Months", use_container_width=True, key="qd_3months"):
                    st.session_state.date_filter_start = today - timedelta(days=90)
                    st.session_state.date_filter_end = today
            
            with col3:
                if st.button("📈 This Year", use_container_width=True, key="qd_year"):
                    st.session_state.date_filter_start = today.replace(month=1, day=1)
                    st.session_state.date_filter_end = today
                
                if st.button("📚 All Data", use_container_width=True, key="qd_all"):
                    st.session_state.date_filter_start = pd.Timestamp('2022-01-01').date()
                    st.session_state.date_filter_end = today
            
            # Show current filter with formatting
            st.markdown("---")
            start_str = st.session_state.date_filter_start.strftime("%Y-%m-%d")
            end_str = st.session_state.date_filter_end.strftime("%Y-%m-%d")
            st.success(f"📅 **{start_str}** → **{end_str}**")
            
            # Custom date input using text input (more reliable)
            with st.expander("📆 Custom Date Range"):
                col1, col2 = st.columns(2)
                with col1:
                    custom_start = st.date_input(
                        "Start Date", 
                        value=st.session_state.date_filter_start,
                        key="custom_start_date"
                    )
                with col2:
                    custom_end = st.date_input(
                        "End Date", 
                        value=st.session_state.date_filter_end,
                        key="custom_end_date"
                    )
                
                if st.button("✅ Apply Custom Range", use_container_width=True, key="apply_custom"):
                    st.session_state.date_filter_start = custom_start
                    st.session_state.date_filter_end = custom_end
                    st.success(f"✅ Applied: {custom_start} → {custom_end}")
                    st.rerun()
    
    # ========================================================================
    # STEP 1: Get DataFrame (adjust based on your app)
    # ========================================================================
    
    try:
        # Try multiple ways to get the dataframe
        if api_client and hasattr(api_client, 'get_data'):
            df = api_client.get_data()
        elif api_client and hasattr(api_client, 'df'):
            df = api_client.df
        elif 'current_data' in st.session_state:
            df = st.session_state.current_data
        elif 'df' in st.session_state:
            df = st.session_state.df
        else:
            st.warning("⚠️ No data loaded. Please load data first.")
            st.info("💡 Go to the data loading page or upload your Excel file.")
            return
    
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return
    
    # ========================================================================
    # STEP 2: Initialize AI Model (OpenAI or Ollama)
    # ========================================================================
    
    # Add model selection toggle in sidebar
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🤖 AI Model Selection")
        
        model_choice = st.radio(
            "Select AI Model",
            ["🟢 OpenAI (gpt-4o-mini)", "🔵 Ollama (gemma3:4b)"],
            help="Choose between OpenAI API or local Ollama model (gemma is fast & optimized for multilingual)"
        )
        
        if model_choice == "🟢 OpenAI (gpt-4o-mini)":
            st.info("Using OpenAI Cloud API")
        else:
            st.info("Using Local Ollama Model")
    
    # Initialize based on selection
    model = None
    model_name = None
    
    if model_choice == "🟢 OpenAI (gpt-4o-mini)":
        # OpenAI Configuration
        api_key = os.environ.get('OPENAI_API_KEY')
        
        if not api_key:
            st.error("⚠️ OPENAI_API_KEY not set")
            st.info("""
            **How to fix:**
            1. Get your API key from OpenAI
            2. Set it in your .env.app file as `OPENAI_API_KEY`
            """)
            return
        
        # Configure OpenAI Client
        try:
            from openai import OpenAI
            model = OpenAI(api_key=api_key)
            model_name = "gpt-4o-mini"
            st.success("✅ OpenAI model ready")
        except Exception as e:
            st.error(f"Failed to initialize OpenAI client: {e}")
            return
    
    else:  # Ollama
        # Ollama Configuration
        try:
            from openai import OpenAI as OllamaClient
            
            # Initialize Ollama client (defaults to http://localhost:11434)
            model = OllamaClient(
                base_url="http://localhost:11434/v1",
                api_key="ollama"  # Ollama doesn't need real API key
            )
            model_name = "gemma3:4b"
            
            # Test if Ollama is running
            try:
                # Quick test call
                test_response = model.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5
                )
                st.success(f"✅ Ollama model ready: {model_name}")
            except Exception as test_error:
                st.error(f"⚠️ Ollama not responding: {test_error}")
                st.info("""
                **How to fix:**
                1. Install Ollama: https://ollama.ai
                2. Run: `ollama pull gemma3:4b`
                3. Ollama should auto-start, or run: `ollama serve`
                """)
                return
                
        except Exception as e:
            st.error(f"Failed to initialize Ollama client: {e}")
            st.info("Make sure Ollama is installed and running on http://localhost:11434")
            return
    
    # Store model info in session state for use in process_data_query
    st.session_state.model_name = model_name
    
    # ========================================================================
    # STEP 3: Show Instructions
    # ========================================================================
    
    st.info("""
    **🌱 How to use:**
    1. Type your question about the pesticide data
    2. Press Enter or click "Ask"
    3. View the AI-generated code and results
    
    **Example Questions:**
    - "What are the top 5 vegetables with highest violation rates?"
    - "Show me compliance trends by year"
    - "Which pesticides have the most violations?"
    - "Calculate average exceedance ratio by vegetable"
    - "Find vegetables with more than 10 violations"
    """)
    
    # ========================================================================
    # PERSISTENT RISK WINDOW DISPLAY
    # Check if there's ongoing risk analysis in session state and display it
    # This ensures the risk window persists when filters are changed
    # ========================================================================
    
    if RISK_WINDOWS_AVAILABLE:
        # Display Health Risk Window if data exists in session state
        if 'risk_residue_data' in st.session_state and st.session_state.get('risk_show_window', False):
            show_health_risk_window(
                st.session_state['risk_residue_data'],
                st.session_state.get('risk_commodity', 'Total Vegetables'),
                query=st.session_state.get('risk_query', '')
            )
        
        # Display Quality Index Window if data exists in session state
        elif 'iqr_residue_data' in st.session_state and st.session_state.get('iqr_show_window', False):
            show_quality_index_window(
                st.session_state['iqr_residue_data'],
                st.session_state.get('iqr_commodity', 'Total Vegetables'),
                query=st.session_state.get('iqr_query', '')
            )
    
    # ========================================================================
    # STEP 4: Get User Input (THIS IS THE KEY PART!)
    # ========================================================================
    
    # Method 1: Chat input (modern Streamlit way)
    chat_question = st.chat_input("Ask a question about the data...")
    
    # Method 2: Text area + button (alternative)
    st.markdown("---")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        text_question = st.text_area(
            "Or type your question here:",
            height=100,
            placeholder="Example: What are the top 10 vegetables by violation count?"
        )
    
    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        ask_button = st.button("🚀 Ask", type="primary", use_container_width=True)
    
    # Determine which input to use
    user_question = chat_question or (text_question if ask_button else None)
    
    # ========================================================================
    # STEP 5: Process Question
    # ========================================================================
    
    # ================================================================
    # HANDLE QUICK QUERY (from buttons at bottom)
    # ================================================================
    if 'quick_query' in st.session_state and st.session_state.quick_query:
        user_question = st.session_state.quick_query
        st.session_state.quick_query = None  # Clear it immediately
        # Don't rerun - just process it below
    
    if user_question:
        # DETECT QUERY TYPE
        iso_keywords = ['iso', '17025', 'standard', 'procedure', 'manual', 
                        'quality', 'calibration', 'validation', 'document', 'sop']
        risk_keywords = ['risk', 'assessment', 'health', 'safety', 'adi', 'arfd']
        
        query_lower = user_question.lower()
        is_iso = any(kw in query_lower for kw in iso_keywords)
        
        # Handle auto-detect risk
        if has_risk is None:
            has_risk = any(kw in query_lower for kw in risk_keywords)
        
        # HANDLE ISO QUERIES WITH RAG
        if is_iso:
            with st.spinner("🔍 Searching ISO documents..."):
                if hasattr(api_client, 'nlp_controller'):
                    try:
                        result = api_client.nlp_controller.query(user_question)
                        st.success("✅ Found ISO information")
                        st.markdown("### 📋 Answer:")
                        st.write(result.get('answer', 'No information found'))
                        
                        if result.get('sources'):
                            with st.expander("📚 Sources"):
                                for src in result['sources']:
                                    st.write(f"• {src}")
                    except Exception as e:
                        st.error(f"ISO search error: {e}")
                else:
                    st.info("ISO documents not configured. Falling back to general query.")
                    is_iso = False  # Fall back to Gemini
        
        # HANDLE PESTICIDE QUERIES WITH GEMINI (your existing code)
        if not is_iso:  # Only run if not an ISO query
            # Apply risk assessment settings
            risk_mode = st.session_state.get('risk_mode', '🤖 Auto-detect')
            if risk_mode == "✅ Always On":
                include_risk = True
            elif risk_mode == "❌ Always Off":
                include_risk = False
            else:  # Auto-detect
                risk_keywords = ['risk', 'safety', 'safe', 'health', 'assess', 'eat', 'consume', 'adult', 'child', 'population']
                include_risk = any(kw in user_question.lower() for kw in risk_keywords)
            
            if include_risk:
                st.success("🎯 Risk assessment enabled")
            
            # ================================================================
            # APPLY DATE FILTER IF ENABLED
            # ================================================================
            
            df_filtered = df.copy()
            
            if st.session_state.get('date_filter_enabled', False):
                start_date = st.session_state.get('date_filter_start')
                end_date = st.session_state.get('date_filter_end')
                
                if start_date and end_date and 'document_date' in df_filtered.columns:
                    # Convert to datetime for comparison
                    df_filtered['document_date'] = pd.to_datetime(df_filtered['document_date'], errors='coerce')
                    start_ts = pd.Timestamp(start_date)
                    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)  # Include full end date
                    
                    # Apply date filter
                    df_filtered = df_filtered[
                        (df_filtered['document_date'] >= start_ts) & 
                        (df_filtered['document_date'] <= end_ts)
                    ]
                    
                    # Show filter status
                    st.info(f"📅 Date filter active: {start_date} → {end_date} ({len(df_filtered):,} records)")
                    
                    if len(df_filtered) == 0:
                        st.warning("⚠️ No data found in the selected date range. Try a different range.")
                        return
            
            # Choose query engine based on sidebar selection
            query_engine = st.session_state.get('query_engine', 'pandas')
            
            if query_engine == 'sql':
                # 🆕 Use SQL (DuckDB) - faster and more secure
                st.info("🚀 Using SQL (DuckDB) query engine")
                process_data_query_sql(user_question, model, include_risk)
            else:
                # Legacy: Use Pandas
                st.info("🐼 Using Pandas query engine")
                process_data_query(user_question, df_filtered, model, include_risk)

    # ========================================================================
    # STEP 6.5: Display stored results with chart buttons (PERSISTENT)
    # ========================================================================
    
    # Always display stored results - this persists across button clicks
    display_stored_results_with_charts()

    # ========================================================================
    # STEP 6.6: Data Entry Form (when toggled)
    # ========================================================================
    
    # Show data entry button in sidebar
    show_data_entry_sidebar()
    
    # Display data entry form if toggled
    if st.session_state.get('show_data_entry_form', False):
        show_data_entry_form()

    # ========================================================================
    # STEP 7: Show Chat History (Optional)
    # ========================================================================
    
    if 'chat_history' in st.session_state and st.session_state.chat_history:
        st.markdown("---")
        st.subheader("📜 Recent Queries")
        
        # Show last 5 queries
        for i, item in enumerate(reversed(st.session_state.chat_history[-5:])):
            with st.expander(f"Q{i+1}: {item['question'][:60]}..."):
                st.markdown(f"**Question:** {item['question']}")
                st.markdown(f"**Time:** {item['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                if isinstance(item['result'], pd.DataFrame):
                    st.dataframe(item['result'].head(10))
                else:
                    st.write(item['result'])
                
                show_code = st.checkbox("👨‍💻 Show generated code", value=True, key=f"show_code_hist_{i}")
                if show_code:
                    st.code(item['code'], language='python')
                        
        # Clear history button
        if st.button("🗑️ Clear History"):
            st.session_state.chat_history = []
            st.rerun()
    
    # ========================================================================
    # STEP 8: Quick Query Buttons (Optional)
    # ========================================================================
    
    st.markdown("---")
    st.subheader("⚡ Quick Queries")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Top Vegetables"):
            # Trigger quick query by setting it in session state
            st.session_state.quick_query = "What are the top 10 vegetables by violation count?"
            st.rerun()
    
    with col2:
        if st.button("🧪 Top Pesticides"):
            st.session_state.quick_query = "What are the top 10 pesticides by violation count?"
            st.rerun()
    
    with col3:
        if st.button("📈 Yearly Trends"):
            st.session_state.quick_query = "Show me compliance rate by year"
            st.rerun()


def format_result_as_table(df: pd.DataFrame, query_type: str = "statistics") -> pd.DataFrame:
    """Format DataFrame as a clean table for display"""
    if df.empty:
        return df
    
    df = df.copy()
    
    # Remove any duplicate columns
    df = df.loc[:, ~df.columns.duplicated()]
    
    if query_type == "vegetable_statistics":
        # Ensure we have the right columns for vegetable statistics
        expected_cols = ['vegetable_arabic', 'عدد العينات', 'فوق الحد', 'تحت الحد']
        for expected in expected_cols:
            if expected not in df.columns:
                # Try to find similar columns
                for col in df.columns:
                    if any(word in str(col) for word in ['vegetable', 'خضروات', 'نوع']):
                        df = df.rename(columns={col: 'vegetable_arabic'})
                    elif any(word in str(col) for word in ['count', 'عدد', 'عينات']):
                        df = df.rename(columns={col: 'عدد العينات'})
                    elif any(word in str(col) for word in ['above', 'فوق', 'exceed']):
                        df = df.rename(columns={col: 'فوق الحد'})
                    elif any(word in str(col) for word in ['below', 'تحت', 'compliant']):
                        df = df.rename(columns={col: 'تحت الحد'})
    
    # Format numeric columns
    for col in df.select_dtypes(include=[np.number]).columns:
        if 'reading' in str(col).lower() or 'limits' in str(col).lower():
            df[col] = df[col].apply(lambda x: f"{float(x):.2f}" if pd.notnull(x) else "N/A")
        elif any(word in str(col).lower() for word in ['edi', 'hq', 'ratio', 'percentage']):
            df[col] = df[col].apply(lambda x: f"{float(x):.4f}" if pd.notnull(x) else "N/A")
    
    return df
def load_chemical_groups_to_duckdb(con):
    """
    Load chemical classification data from JSON into a temporary DuckDB table.
    This allows joining pesticide data with their chemical groups (e.g. Pyrethroids).
    """
    try:
        # File is in src/LARS/scripts/chemical_classification.json
        config_path = Path(__file__).parent.parent / 'scripts' / 'chemical_classification.json'
        if not config_path.exists():
            return
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        groups_data = []
        for key, data in config.get('chemical_groups', {}).items():
            name_en = data.get('name_en', key)
            name_ar = data.get('name_ar', key)
            primary_use = data.get('primary_use', 'N/A')
            for pesticide in data.get('pesticides', []):
                groups_data.append({
                    'pesticide_name': pesticide.lower().strip(),
                    'group_name_en': name_en,
                    'group_name_ar': name_ar,
                    'group_key': key,
                    'primary_use': primary_use
                })
        
        if groups_data:
            groups_df = pd.DataFrame(groups_data)
            # Create a temporary table in the current connection
            con.execute("CREATE OR REPLACE TEMPORARY TABLE pesticide_groups AS SELECT * FROM groups_df")
    except Exception as e:
        print(f"Warning: Failed to load pesticide groups to DuckDB: {e}")

def get_duckdb_connection():
    """Get DuckDB read-only connection. Delegates path resolution to data_access."""
    from modules.data_access import get_duckdb_read, _DUCKDB_PATH
    if not _DUCKDB_PATH.exists():
        return None
    con = get_duckdb_read()
    load_chemical_groups_to_duckdb(con)
    return con

def get_duckdb_connection_write():
    """Get DuckDB write connection. Delegates path resolution to data_access."""
    from modules.data_access import get_duckdb_write, _DUCKDB_PATH
    if not _DUCKDB_PATH.exists():
        return None
    con = get_duckdb_write()
    load_chemical_groups_to_duckdb(con)
    return con

def transform_pesticide_columns(df):
    """
    Transform pesticide columns (ملوث 1 to ملوث 8) into separate rows
    Each row will have: sample_code, pesticide_name, concentration, limit_value
    """
    # Find pesticide columns dynamically (they contain 'ملوث' in their names)
    pesticide_columns = [col for col in df.columns if 'ملوث' in col]
    
    transformed_data = []
    
    for idx, row in df.iterrows():
        sample_code = row.get('كود العينة', None)
        if pd.isna(sample_code):
            continue
            
        for pesticide_col in pesticide_columns:
            cell_value = row[pesticide_col]
            if pd.notna(cell_value) and str(cell_value).strip() != '':
                # Split the pesticide info: "chlorpyrifos,0.7,0.01"
                parts = str(cell_value).split(',')
                
                # Extract contaminant number (e.g., "ملوث 1" -> "1")
                contaminant_match = re.search(r'ملوث\s*(\d+)', pesticide_col)
                contaminant_num = contaminant_match.group(1) if contaminant_match else '0'
                
                if len(parts) >= 3:
                    pesticide_name = parts[0].strip()
                    try:
                        concentration = float(parts[1].strip())
                        limit_value = float(parts[2].strip())
                        
                        transformed_data.append({
                            'كود العينة': sample_code,
                            'التاريخ': row.get('التاريخ', None),
                            'اسم العينة': row.get('اسم العينة', ''),
                            'نوع العينة': row.get('نوع العينة', ''),
                            'الحى': row.get('الحى', ''),
                            'اسم المنشاة': row.get('اسم المنشاة', ''),
                            'pesticide_name': pesticide_name,
                            'concentration': concentration,
                            'limit_value': limit_value,
                            'exceedance_ratio': concentration / limit_value if limit_value > 0 else 0,
                            'is_compliant': 1 if concentration <= limit_value else 0,
                            'contaminant_number': contaminant_num,
                            'is_detected': 1
                        })
                    except (ValueError, TypeError):
                        # Handle cases like "NO CBD"
                        if 'NO' in str(cell_value).upper():
                            transformed_data.append({
                                'كود العينة': sample_code,
                                'التاريخ': row.get('التاريخ', None),
                                'اسم العينة': row.get('اسم العينة', ''),
                                'نوع العينة': row.get('نوع العينة', ''),
                                'الحى': row.get('الحى', ''),
                                'اسم المنشاة': row.get('اسم المنشاة', ''),
                                'pesticide_name': 'NO DETECTION',
                                'concentration': 0,
                                'limit_value': 0,
                                'exceedance_ratio': 0,
                                'is_compliant': 1,
                                'contaminant_number': contaminant_num,
                                'is_detected': 0
                            })
                else:
                    # Handle "NO CBD" or other non-parseable values
                    if 'NO' in str(cell_value).upper():
                        transformed_data.append({
                            'كود العينة': sample_code,
                            'التاريخ': row.get('التاريخ', None),
                            'اسم العينة': row.get('اسم العينة', ''),
                            'نوع العينة': row.get('نوع العينة', ''),
                            'الحى': row.get('الحى', ''),
                            'اسم المنشاة': row.get('اسم المنشاة', ''),
                            'pesticide_name': 'NO DETECTION',
                            'concentration': 0,
                            'limit_value': 0,
                            'exceedance_ratio': 0,
                            'is_compliant': 1,
                            'contaminant_number': contaminant_num,
                            'is_detected': 0
                        })
    
    return pd.DataFrame(transformed_data)

def find_samples_with_n_pesticides(con, n_pesticides=2, limit=3):
    """
    Find samples that contain exactly N pesticides
    Returns unique sample codes
    """
    query = f"""
    SELECT 
        "كود العينة" as sample_code,
        "اسم العينة" as sample_name,
        COUNT(*) as pesticide_count
    FROM chemistry_tidy
    WHERE is_detected = 1 AND pesticide_name != 'NO DETECTION'
    GROUP BY "كود العينة", "اسم العينة"
    HAVING COUNT(*) = {n_pesticides}
    ORDER BY "كود العينة" DESC
    LIMIT {limit}
    """
    
    return con.execute(query).df()

def load_and_transform_data():
    """
    Load data and transform pesticide columns into tidy format
    This should be called when the app starts or when new data is loaded
    """
    if 'df' not in st.session_state:
        data_path = os.path.join(os.path.dirname(__file__), 'data', 'processed_data_with_neighborhood.xlsx')
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            st.session_state.df = df
            st.session_state.data_loaded = True
            
            # Transform the data
            df_tidy = transform_pesticide_columns(df)
            st.session_state.df_tidy = df_tidy
            
            # Save to DuckDB
            db_path = os.path.join(os.path.dirname(__file__), 'data', 'lars_data.duckdb')
            if os.path.exists(db_path):
                try:
                    con = duckdb.connect(db_path, read_only=False)
                    # Create the tidy table
                    con.execute("CREATE OR REPLACE TABLE chemistry_tidy AS SELECT * FROM df_tidy")
                    con.close()
                    st.success(f"✅ Transformed data loaded: {len(df_tidy):,} pesticide records from {len(df):,} samples")
                except Exception as e:
                    st.error(f"❌ Error saving to DuckDB: {e}")
            else:
                st.warning("⚠️ DuckDB database not found. Create it with: `python migrate_db.py`")

def get_sql_schema_info(con) -> str:
    """
    Get database schema information for Schema-Only Prompting
    Returns metadata for both original and transformed data
    Uses CHEMISTRY_TIDY table (transformed with separate columns)
    """
    schema_parts = []
    
    # Get information about chemistry_tidy table (transformed data)
    try:
        columns_df = con.execute("DESCRIBE chemistry_tidy").df()
        schema_parts.append("**Table: chemistry_tidy (Transformed - One row per pesticide)**")
        schema_parts.append("| Column | Type | Description |")
        schema_parts.append("|--------|------|-------------|")
        
        column_descriptions = {
            'كود العينة': 'Sample code (unique identifier)',
            'التاريخ': 'Sample date (TIMESTAMP)',
            'اسم العينة': 'Sample name in Arabic (e.g., طماطم, خيار, كمون)',
            'نوع العينة': 'Sample type (خضراوات, فواكهة, توابل, etc.)',
            'تصنيف العينة': 'Sample classification (خدمية, تجارية, etc.)',
            'نوع الاختبار': 'Test type (متبقيات مبيدات, افلاتوكسين, etc.)',
            'الحى': 'Neighborhood name',
            'اسم المنشاة': 'Establishment/facility name',
            'اسم البلدية': 'Municipality name (e.g., بلدية غرب بريدة)',
            'رقم الرخصة': 'License number',
            'حالة العينة': 'Sample condition/status',
            'اسم المستلم': 'Receiver name',
            'pesticide_name': 'Pesticide/contaminant name',
            'concentration': 'Measured concentration (DOUBLE)',
            'limit_value': 'Maximum allowed limit (DOUBLE)',
            'exceedance_ratio': 'concentration / limit_value (DOUBLE)',
            'is_above_limit': '1 = above limit (فوق الحد), 0 = below limit (تحت الحد) - CALCULATED',
            'is_compliant': '1 = compliant (مطابق), 0 = non-compliant (غير مطابق) - LAB JUDGMENT',
            'is_detected': '1 = pesticide detected, 0 = no detection',
            'contaminant_number': 'Which contaminant column (1-10)',
            'sample_result': 'Original lab result text'
        }
        
        for _, row in columns_df.iterrows():
            col_name = row['column_name']
            desc = column_descriptions.get(col_name, '')
            schema_parts.append(f"| {col_name} | {row['column_type']} | {desc} |")
        
        # Get row count
        count = con.execute("SELECT COUNT(*) as count FROM chemistry_tidy").fetchone()[0]
        schema_parts.append(f"\n**Total Records:** {count:,} pesticide-sample combinations")
        
        # Get unique sample count
        unique_samples = con.execute("SELECT COUNT(DISTINCT \"كود العينة\") as samples FROM chemistry_tidy").fetchone()[0]
        schema_parts.append(f"**Unique Samples:** {unique_samples:,} samples")
        
        # Get pesticide statistics
        pesticide_stats = con.execute("""
            SELECT 
                pesticide_name,
                COUNT(*) as count,
                SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as violations,
                ROUND(AVG(CASE WHEN is_detected = 1 THEN exceedance_ratio END), 2) as avg_exceedance
            FROM chemistry_tidy
            WHERE pesticide_name != 'NO DETECTION'
            GROUP BY pesticide_name
            ORDER BY count DESC
            LIMIT 10
        """).df()
        
        if not pesticide_stats.empty:
            schema_parts.append("\n**Top Pesticides Detected:**")
            for _, row in pesticide_stats.iterrows():
                schema_parts.append(f"- {row['pesticide_name']}: {row['count']} detections ({row['violations']} violations)")
        
        # Get sample types
        sample_type_stats = con.execute("""
            SELECT 
                "نوع العينة" as sample_type,
                COUNT(DISTINCT "كود العينة") as samples,
                SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as violations
            FROM chemistry_tidy
            WHERE "نوع العينة" IS NOT NULL
            GROUP BY "نوع العينة"
            ORDER BY samples DESC
            LIMIT 5
        """).df()
        
        if not sample_type_stats.empty:
            schema_parts.append("\n**Sample Types:**")
            for _, row in sample_type_stats.iterrows():
                schema_parts.append(f"- {row['sample_type']}: {row['samples']} samples ({row['violations']} violations)")
        
        # NEW: Add information about pesticide groups (helper table)
        try:
            pg_columns = con.execute("DESCRIBE pesticide_groups").df()
            schema_parts.append("\n**Table: pesticide_groups (Helper table for classifications)**")
            schema_parts.append("| Column | Type | Description |")
            schema_parts.append("|--------|------|-------------|")
            schema_parts.append("| pesticide_name | VARCHAR | Pesticide name (joins with chemistry_tidy) |")
            schema_parts.append("| group_name_en | VARCHAR | English group name (e.g., Pyrethroids) |")
            schema_parts.append("| group_name_ar | VARCHAR | Arabic group name (e.g., بايرثرويدات) |")
            schema_parts.append("| group_key | VARCHAR | Internal key indicator |")
            schema_parts.append("| primary_use | VARCHAR | Primary use (Insecticide, Fungicide, etc.) |")
        except:
            pass
            
        # NEW: Add information about original structure for reference
        schema_parts.append("\n---")
        schema_parts.append("**Original Data Structure (for reference):**")
        schema_parts.append("- Each sample can have 0-8 pesticides in columns ملوث 1 to ملوث 8")
        schema_parts.append("- Format in each ملوث column: 'pesticide_name,concentration,limit'")
        schema_parts.append("- Example: 'chlorpyrifos,0.7,0.01'")
        schema_parts.append("- 'NO CBD' means no detection")
        
    except Exception as e:
        schema_parts.append(f"Error reading schema: {e}")
    
    return '\n'.join(schema_parts)

def generate_map_chart(df: pd.DataFrame, query: str = ""):
    """Generate an interactive map chart for neighborhoods in القصيم, السعودية"""
    try:
        import plotly.graph_objects as go
        
        # Enhanced neighborhood coordinates with Arabic names and proper positioning
        NEIGHBORHOOD_COORDS = {
            'الإسكان': (26.3380, 43.9720),
            'الموطأ': (26.3650, 43.9850),
            'الصفراء': (26.3700, 43.9400),
            'الأفق': (26.3550, 43.9650),
            'الريان': (26.3300, 43.9600),
            'النخيل': (26.3400, 43.9900),
            'السلام': (26.3500, 43.9500),
            'الفيصلية': (26.3250, 43.9550),
            'المنار': (26.3200, 43.9450),
            'الراشد': (26.3150, 43.9550),
            'الحمر': (26.3400, 43.9350),
            'الضاحي': (26.3050, 43.9650),
            'قرطبة': (26.2950, 43.9750),
            'الوادي': (26.3550, 43.9800),
            'المروج': (26.3600, 43.9950),
            'الجردة': (26.3350, 43.9250),
            'البصر': (26.3750, 43.9850),
            'الغدير': (26.2900, 43.9500),
            'المحمدية': (26.3480, 43.9480),
            'الربوة': (26.3380, 43.9380),
            'النزهة': (26.3280, 43.9680),
            'الورود': (26.3180, 43.9480),
            'الروضة': (26.3080, 43.9380),
            'الحزم': (26.2980, 43.9580),
            'العليا': (26.3880, 43.9580),
            'واسط': (26.3350, 43.9700),
            'الملك فيصل': (26.3300, 43.9750),
            'الملك عبدالله': (26.3400, 43.9800),
            'الملك سلمان': (26.3200, 43.9750),
            'الخالدية': (26.3100, 43.9700),
            'النهضة': (26.3000, 43.9650),
            'الرمال': (26.2900, 43.9600),
            'الوريف': (26.2800, 43.9550),
            'الغربية': (26.2700, 43.9500),
            'الشمالية': (26.2600, 43.9450),
            'الجنوبية': (26.2500, 43.9400),
            'الشرقية': (26.2400, 43.9350),
            'الوسطى': (26.2300, 43.9300),
        }
        
        DEFAULT_COORDS = (26.3300, 43.9750)
        
        def extract_neighborhood(address):
            if pd.isna(address): return "غير محدد"
            address_str = str(address)
            clean_address = re.sub(r'\d+', '', address_str).strip()
            for neighborhood in NEIGHBORHOOD_COORDS.keys():
                if neighborhood in clean_address: return neighborhood
            return clean_address[:30] if len(clean_address) > 30 else clean_address
        
        neighborhood_col = None
        for col in df.columns:
            if any(word in str(col).lower() for word in ['حي', 'neighborhood', 'الحي', 'بقعة']):
                neighborhood_col = col
                break
        
        if neighborhood_col is None:
            st.error("⚠️ لم يتم العثور على بيانات الأحياء")
            return
        
        violation_col = None
        for col in df.columns:
            if any(word in str(col).lower() for word in ['violation', 'مخالفة', 'غير مطابق']):
                violation_col = col
                break
        
        if violation_col:
            df['violation_count'] = pd.to_numeric(df[violation_col], errors='coerce').fillna(0)
            agg_data = df.groupby(neighborhood_col).agg({'violation_count': ['sum', 'count']}).reset_index()
            agg_data.columns = ['neighborhood', 'violation_count', 'sample_count']
        else:
            agg_data = df.groupby(neighborhood_col).size().reset_index(name='sample_count')
            agg_data['violation_count'] = 0
            agg_data.columns = ['neighborhood', 'sample_count', 'violation_count']
        
        agg_data['violation_rate'] = agg_data.apply(lambda row: row['violation_count'] / row['sample_count'] if row['sample_count'] > 0 else 0, axis=1)
        
        def get_coords(name):
            name_str = str(name).strip()
            # Try exact match
            if name_str in NEIGHBORHOOD_COORDS:
                return NEIGHBORHOOD_COORDS[name_str]
            
            # Normalize (remove alif variants) and try again
            norm_name = name_str.replace('إ', 'ا').replace('أ', 'ا').replace('آ', 'ا')
            for k, v in NEIGHBORHOOD_COORDS.items():
                if k.replace('إ', 'ا').replace('أ', 'ا').replace('آ', 'ا') == norm_name:
                    return v
            return DEFAULT_COORDS

        agg_data['coords'] = agg_data['neighborhood'].apply(get_coords)
        agg_data['lat'] = agg_data['coords'].apply(lambda x: x[0])
        agg_data['lon'] = agg_data['coords'].apply(lambda x: x[1])
        
        fig = go.Figure()
        fig.add_trace(go.Scattermapbox(
            lat=agg_data['lat'], lon=agg_data['lon'], mode='markers+text',
            text=agg_data['neighborhood'], textposition="top center",
            marker=dict(size=agg_data['violation_count'].apply(lambda x: max(20, min(60, x * 5))),
            color=agg_data['violation_rate'].apply(lambda r: 'red' if r > 0.5 else 'orange' if r > 0.3 else 'yellow' if r > 0.1 else 'green')),
            hoverinfo='text',
            hovertext=[f"<b>{r['neighborhood']}</b><br>Samples: {r['sample_count']}<br>Violations: {r['violation_count']}" for _, r in agg_data.iterrows()]
        ))
        
        fig.update_layout(mapbox=dict(style="open-street-map", center=dict(lat=26.33, lon=43.97), zoom=11), height=600)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating map: {e}")

def display_stored_results_with_charts():
    if 'last_query_result' not in st.session_state or st.session_state.last_query_result is None:
        return
    
    result = st.session_state.last_query_result
    query = st.session_state.get('last_query', '')
    
    st.markdown("---")
    st.subheader("📊 نتائج آخر استعلام (Stored Results)")
    st.dataframe(result, use_container_width=True)
    
    if 'selected_chart' not in st.session_state:
        st.session_state.selected_chart = None
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        if st.button("📊 أعمدة", key="btn_bar_stored"): st.session_state.selected_chart = "bar"
    with col2:
        if st.button("📈 خطي", key="btn_line_stored"): st.session_state.selected_chart = "line"
    with col3:
        if st.button("🥧 دائري", key="btn_pie_stored"): st.session_state.selected_chart = "pie"
    with col4:
        if st.button("🎯 رادار", key="btn_radar_stored"): st.session_state.selected_chart = "radar"
    with col5:
        if st.button("💠 مبعثر", key="btn_scatter_stored"): st.session_state.selected_chart = "scatter"
    with col6:
        if st.button("🗺️ خريطة", key="btn_map_stored"): st.session_state.selected_chart = "map"
    
    if st.session_state.selected_chart:
        chart_func = {
            "bar": generate_bar_chart, "line": generate_line_chart, 
            "pie": generate_pie_chart, "radar": generate_radar_chart,
            "scatter": generate_scatter_plot, "map": generate_map_chart
        }.get(st.session_state.selected_chart)
        
        if chart_func:
            chart_func(result, query)
        
        if st.button("🗑️ مسح الرسم البياني"):
            st.session_state.selected_chart = None
            st.rerun()

def show_data_entry_sidebar():
    with st.sidebar:
        st.markdown("---")
        st.markdown("### ➕ Data Entry")
        if st.button("📝 Add New Sample", use_container_width=True):
            st.session_state.show_data_entry_form = not st.session_state.get('show_data_entry_form', False)
            st.rerun()

def show_data_entry_form():
    if not st.session_state.get('show_data_entry_form', False):
        return
    
    st.markdown("---")
    st.subheader("📝 Add New Sample Data")
    
    if 'df' not in st.session_state or st.session_state.df is None:
        st.warning("⚠️ No dataset loaded for dropdowns.")
        return
        
    df = st.session_state.df
    vegetables = sorted(df['vegetable_arabic'].dropna().unique().tolist()) if 'vegetable_arabic' in df.columns else []
    pesticides = sorted(df['pesticide'].dropna().unique().tolist()) if 'pesticide' in df.columns else []
    
    with st.form("data_entry_form"):
        col1, col2 = st.columns(2)
        with col1:
            veg = st.selectbox("نوع الخضروات", ["-- Select --"] + vegetables)
            pest = st.selectbox("المبيد الحشري", ["-- Select --"] + pesticides)
        with col2:
            reading = st.number_input("القراءة", min_value=0.0, format="%.4f")
            limits = st.number_input("الحد الأقصى", min_value=0.0, format="%.4f")
        
        submitted = st.form_submit_button("➕ Add Sample")
        if submitted:
            st.success("✅ Sample added (Demo implementation - please run migrate_db.py for persistent storage)")

def upload_iso_document_ui(api_client, uploaded_file, doc_type: str, project_id: str):
    with st.spinner(f"📤 Uploading {uploaded_file.name}..."):
        try:
            url = f"{api_client.base_url}/api/v1/iso/upload/{project_id}"
            files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            response = requests.post(url, files=files, data={'document_type': doc_type}, timeout=120)
            response.raise_for_status()
            st.success(f"✅ Successfully uploaded and indexed: {uploaded_file.name}")
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")


