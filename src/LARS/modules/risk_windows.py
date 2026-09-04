"""
Risk Windows Module for LARS Application

Provides specialized UI windows for Health Risk and Quality Index display.
Triggered by keyword detection in user queries.
Features sample type detection, parameter inputs, and PRIMo 4 population classes.

Author: LARS Team
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import re
from modules.mappings import COMMODITY_TO_ARABIC

# Import risk assessment functions
try:
    from modules.risk_assessment_service import (
        calculate_lars_metrics,
        calculate_commodity_summary_metrics,
        calculate_sample_iqr_summary,
        detect_query_type,
        get_saudi_ir,
        SAUDI_IR_DATA,
        SAUDI_COMMODITY_MAPPING,
        POPULATION_CLASSES
    )
    RISK_SERVICE_AVAILABLE = True
except ImportError as e:
    RISK_SERVICE_AVAILABLE = False
    print(f"⚠️ Risk service not available: {e}")


# ============================================================================
# SAMPLE TYPE DETECTION
# ============================================================================

# Arabic sample type mapping
SAMPLE_TYPE_MAPPING = {
    'طماطم': ('Tomato', 'طماطم'),
    'خيار': ('Cucumber', 'خيار'),
    'فلفل': ('Pepper', 'فلفل'),
    'باذنجان': ('Eggplant', 'باذنجان'),
    'كوسة': ('Zucchini', 'كوسة'),
    'فاصوليا': ('Beans', 'فاصوليا'),
    'بامية': ('Okra', 'بامية'),
    'خس': ('Lettuce', 'خس'),
    'بقدونس': ('Parsley', 'بقدونس'),
    'كزبرة': ('Coriander', 'كزبرة'),
    'نعناع': ('Mint', 'نعناع'),
    'جرجير': ('Leafy Greens', 'جرجير'),
    'سبانخ': ('Leafy Greens', 'سبانخ'),
    'ملفوف': ('Cabbage', 'ملفوف'),
    'جزر': ('Root Vegetables', 'جزر'),
    'بطاطس': ('Root Vegetables', 'بطاطس'),
    # English mappings
    'tomato': ('Tomato', 'طماطم'),
    'cucumber': ('Cucumber', 'خيار'),
    'pepper': ('Pepper', 'فلفل'),
    'eggplant': ('Eggplant', 'باذنجان'),
    'zucchini': ('Zucchini', 'كوسة'),
    'beans': ('Beans', 'فاصوليا'),
    'okra': ('Okra', 'بامية'),
    'lettuce': ('Lettuce', 'خس'),
    'parsley': ('Parsley', 'بقدونس'),
}


def detect_sample_type(query: str) -> Optional[tuple]:
    """
    Detect sample type from query.
    
    Returns:
        Tuple of (commodity_english, arabic_pattern) or None
    """
    query_lower = query.lower()
    
    for keyword, (commodity, pattern) in SAMPLE_TYPE_MAPPING.items():
        if keyword in query or keyword in query_lower:
            return (commodity, pattern)
    
    return None


# ============================================================================
# RISK INPUT FORM
# ============================================================================

def get_residue_data_for_sample(sample_type_arabic: str) -> List[Dict[str, Any]]:
    """
    Query database for residue data filtered by sample type.
    
    Parameters:
        sample_type_arabic: Arabic name of sample type for filtering
    
    Returns:
        List of dicts with name, concentration, mrl
    """
    try:
        import duckdb
        from pathlib import Path
        
        # Find database path
        possible_paths = [
            Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb',
            Path(__file__).parent.parent / 'lars_data_demo.duckdb',
            Path('/app/src/LARS/lars_data_demo.duckdb'),
        ]
        
        db_path = None
        for p in possible_paths:
            if p.exists():
                db_path = p
                break
        
        if not db_path:
            return []
        
        con = duckdb.connect(str(db_path), read_only=True)
        
        # Build query with sample filter
        sample_filter = f"WHERE \"اسم العينة\" LIKE '%{sample_type_arabic}%'" if sample_type_arabic else ""
        
        query = f"""
        SELECT 
            pesticide_name as name,
            concentration,
            limit_value as mrl,
            "التاريخ" as date,
            "كود العينة" as sample_code,
            is_detected
        FROM chemistry_tidy 
        {sample_filter}
        AND pesticide_name NOT IN ('NO DATA')
        ORDER BY "التاريخ" ASC
        LIMIT 2000
        """
        
        result_df = con.execute(query).df()
        con.close()
        
        return result_df.to_dict('records')
    except Exception as e:
        print(f"Error querying database: {e}")
        return []

# Monthly Trend Analysis Constants
ARABIC_MONTHS = {
    1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
    5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
    9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
}

def show_monthly_iqr_trend(residue_data: List[Dict[str, Any]]):
    """
    Shows monthly trend analysis for IqR as requested.
    Formula: Avg IqR = Sum(IqR for all samples) / Total samples
    """
    if not residue_data:
        st.warning("No data available for trend analysis.")
        return

    df = pd.DataFrame(residue_data)
    
    # Check if 'date' column exists to avoid KeyError
    if 'date' not in df.columns or 'sample_code' not in df.columns:
        st.warning("Trend analysis skipped: Date or Sample Code information missing from data.")
        return
        
    # Ensure date is datetime
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    
    if df.empty:
        st.warning("No valid dates found in data for trend analysis.")
        return
        
    # Calculate IqR for each row
    df['iqr_val'] = df.apply(lambda row: row['concentration'] / row['mrl'] if row['mrl'] > 0 else 0.0, axis=1)
    
    # Extract month and year
    df['month'] = df['date'].dt.month
    df['year'] = df['date'].dt.year
    df['month_name'] = df['month'].map(ARABIC_MONTHS)
    
    # Group by month (assuming single year or grouping all years' months)
    # To follow the screenshot's study case (annual study), we group by month
    
    monthly_stats = []
    for month in range(1, 13):
        m_data = df[df['month'] == month]
        if m_data.empty:
            continue
            
        # Total unique samples in this month
        total_samples = m_data['sample_code'].nunique()
        
        # Sum of all IqR ratios in this month
        sum_iqr = m_data['iqr_val'].sum()
        
        # Average IqR per sample
        avg_iqr = sum_iqr / total_samples if total_samples > 0 else 0
        
        # Status based on screenshot rules
        if avg_iqr < 0.5:
            status = "Good / جيدة"
            status_color = "green"
            status_key = "Good"
        elif avg_iqr < 1.0:
            status = "Adequate / مقبولة"
            status_color = "orange"
            status_key = "Adequate"
        else:
            status = "Inadequate / غير مقبولة"
            status_color = "red"
            status_key = "Inadequate"
            
        # Trend observations (simple logic)
        observation = "Stable / مستقر"
        if len(monthly_stats) > 0:
            prev_iqr = monthly_stats[-1]['avg_iqr']
            if avg_iqr > prev_iqr * 1.2:
                observation = "Increasing / ارتفاع"
            elif avg_iqr < prev_iqr * 0.8:
                observation = "Decreasing / انخفاض"
        
        monthly_stats.append({
            'month_num': month,
            'الشهر (Month)': ARABIC_MONTHS[month],
            'عدد العينات (Samples)': total_samples,
            'متوسط قيمة IqR (Avg IqR)': round(avg_iqr, 3),
            'الحالة (Status)': status,
            'الملاحظات (Trend)': observation,
            'avg_iqr': avg_iqr,
            'status_key': status_key
        })
    
    if not monthly_stats:
        st.info("Insufficient monthly distribution for trend analysis.")
        return
        
    trend_df = pd.DataFrame(monthly_stats)
    
    st.markdown("### 📈 Monthly IqR Trend Analysis / تحليل الترند الشهري")
    
    # Plotly Trend Chart
    import plotly.express as px
    fig = px.line(
        trend_df, 
        x='الشهر (Month)', 
        y='avg_iqr',
        markers=True,
        title="Monthly Average IqR Trend / اتجاه متوسط مؤشر الجودة",
        labels={'avg_iqr': 'Average IqR', 'الشهر (Month)': 'Month'}
    )
    
    # Add status zones
    fig.add_hrect(y0=0, y1=0.5, line_width=0, fillcolor="green", opacity=0.1, annotation_text="Good")
    fig.add_hrect(y0=0.5, y1=1.0, line_width=0, fillcolor="orange", opacity=0.1, annotation_text="Adequate")
    fig.add_hrect(y0=1.0, y1=max(max(trend_df['avg_iqr'])*1.2, 1.5), line_width=0, fillcolor="red", opacity=0.1, annotation_text="Inadequate")
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Display table as requested in screenshot
    display_df = trend_df[['الشهر (Month)', 'عدد العينات (Samples)', 'متوسط قيمة IqR (Avg IqR)', 'الحالة (Status)', 'الملاحظات (Trend)']]
    st.dataframe(display_df, use_container_width=True)
    
    # Summary Info
    peak_month = trend_df.loc[trend_df['avg_iqr'].idxmax()]
    st.info(f"💡 **Peak Contamination:** {peak_month['الشهر (Month)']} (Avg IqR: {peak_month['avg_iqr']:.3f})")

"""
INSTRUCTIONS FOR UPDATING risk_windows.py

The following changes need to be made to properly display and use
the new population-specific ingestion rates:

1. Update show_risk_input_form() to display rates in correct units
2. Update parameter passing to risk calculation functions
3. Add information about which rates are being used

Below are the key updates:
"""

# ============================================================================
# UPDATED FUNCTION: show_risk_input_form()
# ============================================================================

def show_risk_input_form(
    query: str,
    detected_sample: Optional[tuple] = None
) -> Dict[str, Any]:
    """
    Show input form for risk assessment parameters.
    
    UPDATED to show population-specific ingestion rates and their sources.
    
    Returns:
        Dictionary with selected parameters
    """
    st.markdown("### ⚙️ Risk Assessment Parameters / معلمات تقييم المخاطر")
    
    # Initialize session state for commodity tracking
    if 'risk_selected_commodity' not in st.session_state:
        default_commodity = "Total Vegetables"
        if detected_sample and detected_sample[0] in SAUDI_IR_DATA:
            default_commodity = detected_sample[0]
        st.session_state['risk_selected_commodity'] = default_commodity
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Population class dropdown
        pop_options = {}
        for key, pc in POPULATION_CLASSES.items():
            pop_options[key] = f"{pc.name_en} ({pc.name_ar}) - {pc.default_weight_kg} kg"
        
        selected_pop = st.selectbox(
            "👥 Population Class / الفئة السكانية",
            options=list(pop_options.keys()),
            format_func=lambda x: pop_options[x],
            index=list(pop_options.keys()).index('saudi_adults') if 'saudi_adults' in pop_options else 4,
            help="Select population for body weight and ingestion rates."
        )
        
        body_weight = POPULATION_CLASSES[selected_pop].default_weight_kg
    
    with col2:
        # Commodity selector
        commodity_options = [k for k in SAUDI_IR_DATA.keys() if k != "Default"]
        
        # Get current commodity from session state
        current_commodity = st.session_state.get('risk_selected_commodity', 'Total Vegetables')
        current_idx = commodity_options.index(current_commodity) if current_commodity in commodity_options else 0
        
        selected_commodity = st.selectbox(
            "🥬 Commodity / المنتج",
            options=commodity_options,
            index=current_idx,
            help="Changing commodity updates the ingestion rate automatically"
        )
        
        # Check if commodity changed
        if selected_commodity != st.session_state.get('risk_selected_commodity'):
            st.session_state['risk_selected_commodity'] = selected_commodity
            # Re-query database for new sample type
            arabic_sample = COMMODITY_TO_ARABIC.get(selected_commodity, '')
            new_data = get_residue_data_for_sample(arabic_sample)
            st.session_state['risk_residue_data'] = new_data
            st.rerun()
    
    with col3:
        # UPDATED: Get population-specific IR in g/kg bw/day
        from modules.risk_assessment_service import RiskAssessmentConfig
        
        # Check if detailed rates are available
        has_detailed = RiskAssessmentConfig.has_detailed_rates(selected_commodity)
        
        # Get ingestion rate for selected population and commodity
        ir_g_kg_bw_day = RiskAssessmentConfig.get_ingestion_rate(
            selected_commodity,
            population=selected_pop,
            use_detailed=True
        )
        
        # Also show equivalent kg/day for reference
        ir_kg_day = (ir_g_kg_bw_day * body_weight) / 1000
        ir_g_day = ir_kg_day * 1000
        
        # Show IR with source indicator
        st.markdown(f"**📊 Ingestion Rate:**")
        if has_detailed:
            st.markdown(f"### {ir_g_kg_bw_day:.3f} g/kg bw/day")
            st.caption(f"✓ Population-specific rate")
            st.caption(f"≈ {ir_g_day:.1f} g/day for {body_weight} kg person")
        else:
            st.markdown(f"### {ir_g_day:.1f} g/day")
            st.caption(f"⚠️ Using standard rate")
            st.caption(f"({ir_g_kg_bw_day:.3f} g/kg bw/day)")
    
    # Real-time MRL Toggle
    st.markdown("---")
    use_realtime = st.checkbox(
        "🌐 Use Real-time EU MRLs / استخدام حدود الاتحاد الأوروبي المباشرة", 
        value=st.session_state.get('risk_use_realtime', False),
        key="hri_realtime_toggle",
        help="Fetch MRL data directly from the EU Pesticides Database API."
    )
    if use_realtime != st.session_state.get('risk_use_realtime'):
        st.session_state['risk_use_realtime'] = use_realtime
    
    # Show selected parameters summary
    rate_source = "Population-specific (IESTI/WHO)" if has_detailed else "Standard rate"
    
    st.info(f"""
    **Selected Parameters:**
    - 👥 Population: {POPULATION_CLASSES[selected_pop].name_en} ({POPULATION_CLASSES[selected_pop].name_ar})
    - ⚖️ Body Weight: {body_weight} kg
    - 🥬 Commodity: {selected_commodity}
    - 📊 Ingestion Rate: {ir_g_kg_bw_day:.3f} g/kg bw/day (≈{ir_g_day:.1f} g/day)
    - 📚 Rate Source: {rate_source}
    - 🌐 MRL Source: {"EU API (Real-time)" if use_realtime else "Original Dataset"}
    """)
    
    return {
        'population': selected_pop,
        'body_weight': body_weight,
        'commodity': selected_commodity,
        'ingestion_rate_g_kg_bw_day': ir_g_kg_bw_day,  # UPDATED: Now in g/kg bw/day
        'detected_sample': detected_sample,
        'use_realtime': use_realtime,
        'has_detailed_rates': has_detailed
    }


# ============================================================================
# HEALTH RISK WINDOW
# ============================================================================

def show_health_risk_window(
    residue_data: List[Dict[str, Any]],
    commodity: str = "Total Vegetables",
    target: str = "adult",
    query: str = ""
):
    """
    Display Health Risk assessment window with HIc and HQc calculations.
    Uses session state to persist data across filter changes.
    """
    # Use session state data if passed data is empty
    if not residue_data:
        residue_data = st.session_state.get('risk_residue_data', [])
        query = st.session_state.get('risk_query', query)
        commodity = st.session_state.get('risk_commodity', commodity)
    
    st.markdown("---")
    
    # Header with close button
    col_title, col_close = st.columns([6, 1])
    with col_title:
        st.subheader("🏥 Health Risk Index (HRI) Assessment / مؤشر الخطر الصحي")
    with col_close:
        if st.button("❌ Close", key="close_risk_window"):
            st.session_state['risk_show_window'] = False
            st.session_state.pop('risk_residue_data', None)
            st.rerun()
    
    # Detect sample type from query
    detected_sample = detect_sample_type(query) if query else None
    
    if detected_sample:
        st.success(f"🔍 Detected sample type: **{detected_sample[0]}** ({detected_sample[1]})")
    
    # Show parameter input form
    params = show_risk_input_form(query, detected_sample)
    
    # Use the residue data
    filtered_data = residue_data
    
    st.markdown("---")
    
    # Calculate LARS metrics with selected parameters
    if filtered_data:
        target_type = "adult" if params['body_weight'] >= 50 else "child"
        
        
        summary_analysis = calculate_commodity_summary_metrics(
            filtered_data,
            params['commodity'],
            params['population'],  # UPDATED: Use selected population
            body_weight=params['body_weight'],
            ingestion_rate=None,  # UPDATED: Let function get population-specific rate
            use_realtime_mrl=params.get('use_realtime', False)
        )
        
        original_analysis = calculate_lars_metrics(
            filtered_data, 
            params['commodity'], 
            params['population'],  # UPDATED: Use selected population
            body_weight=params['body_weight'],
            ingestion_rate=None,  # UPDATED: Let function get population-specific rate
            use_realtime_mrl=params.get('use_realtime', False)
        )
        # UPDATED: Show ingestion rate units in display
        st.caption(f"""
        **Calculation Details:**
        - Population-specific ingestion rate: {params['ingestion_rate_g_kg_bw_day']:.3f} g/kg bw/day
        - EDI = (Concentration × IR) / 1000
        - HQ = EDI / ADI
        """)

        # Display summary metrics (Using Median-based logic as primary)
        st.markdown(f"### 📊 Health Risk Summary / ملخص الخطر الصحي ({params['commodity']})")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            hi_total = summary_analysis["hi_total"]
            st.metric(
                "Total HIc / مؤشر الخطر",
                f"{hi_total:.4f}",
                delta="⚠️ Unsafe" if hi_total >= 1 else "✅ Safe",
                delta_color="inverse" if hi_total >= 1 else "normal"
            )
        
        with col2:
            # Most common pesticide
            common_pests = pd.DataFrame(filtered_data)['name'].value_counts()
            if not common_pests.empty:
                top_p_name = common_pests.index[0]
                st.metric(
                    "Top Pesticide",
                    top_p_name[:12] + "..." if len(top_p_name) > 12 else top_p_name,
                    f"{common_pests.iloc[0]} detections"
                )
        
        with col3:
            st.metric(
                "Unique Pesticides",
                summary_analysis["total_pesticides"]
            )
        
        with col4:
            # Count of samples
            sample_count = pd.DataFrame(filtered_data)['sample_code'].nunique()
            st.metric(
                "Total Samples",
                sample_count
            )
        
        # Risk interpretation banner
        if hi_total >= 1:
            st.error(f"⚠️ **مؤشر الخطر غير مقبول** - HIc (Median Sum) = {hi_total:.4f} (≥1)")
        elif hi_total >= 0.5:
            st.warning(f"⚡ **خطر مرتفع** - HIc (Median Sum) = {hi_total:.4f} (≥0.5)")
        else:
            st.success(f"✅ **الخطر مقبول** - HIc (Median Sum) = {hi_total:.4f} (<0.5)")
        
        # ====================================================================
        # NEW TABLE AS PER IMAGE: Grouped by Pesticide with Min, Max, Median, HQ
        # ====================================================================
        st.markdown("### 📋 Pesticide Risk Table / جدول مخاطر المبيدات")
        st.caption("Calculation: HQ for each pesticide is calculated based on its MEDIAN concentration.")
        
        if summary_analysis["individual_results"]:
            risk_table_df = pd.DataFrame(summary_analysis["individual_results"])
            
            # Format columns
            risk_table_df = risk_table_df.rename(columns={
                "pesticide": "Pesticide / المبيد",
                "chemical_group": "Group / المجموعة",
                "min": "Min",
                "max": "Max",
                "median": "Median",
                "adi": "ADI",
                "ir": "IR",
                "bw": "BW",
                "hqc": "HQ"
            })
            
            # Reorder columns for transparency
            display_cols = ["Pesticide / المبيد", "Min", "Max", "Median", "ADI", "IR", "BW", "HQ"]
            risk_table_df = risk_table_df[display_cols]
            
            # Highlighting and display
            st.dataframe(
                risk_table_df.style.format({
                    "Min": "{:.4f}",
                    "Max": "{:.4f}",
                    "Median": "{:.4f}",
                    "ADI": "{:.4f}",
                    "IR": "{:.4f}",
                    "BW": "{:.1f}",
                    "HQ": "{:.5f}"
                }).background_gradient(subset=["HQ"], cmap="OrRd"),
                use_container_width=True,
                hide_index=True
            )
            
            # Show the final HIc calculation below the table
            st.markdown(f"""
            <div style="text-align: right; padding: 10px; border-top: 2px solid #ddd; font-weight: bold; font-size: 1.2em;">
                Total HIc (Sum of HQ) = {hi_total:.4f}
            </div>
            """, unsafe_allow_html=True)

        # Chemical group statistics
        with st.expander("🧪 Statistics by Chemical Group / إحصائيات حسب المجموعة"):
            if original_analysis["stats"]:
                stats_data = []
                for group, data in original_analysis["stats"].items():
                    stats_data.append({
                        "Group / المجموعة": group,
                        "Count": data["count"],
                        "Min": f"{data['min']:.4f}",
                        "Max": f"{data['max']:.4f}",
                        "Mean": f"{data['mean']:.4f}",
                        "Median": f"{data['median']:.4f}"
                    })
                
                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, use_container_width=True)
                
                # Bar chart
                chart_data = pd.DataFrame([
                    {"Group": r["chemical_group"], "HQc": r["hqc"]}
                    for r in summary_analysis["individual_results"]
                ])
                if not chart_data.empty:
                    chart_data = chart_data.groupby("Group").sum().reset_index()
                    chart_data = chart_data.sort_values("HQc", ascending=False)
                    
                    import plotly.express as px
                    fig = px.bar(
                        chart_data,
                        x="Group",
                        y="HQc",
                        color="HQc",
                        color_continuous_scale="Reds",
                        title="Aggregated Hazard Quotient (HQc) by Chemical Group"
                    )
                    fig.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Risk Threshold")
                    st.plotly_chart(fig, use_container_width=True)
        
        # Detected samples detail
        with st.expander("📜 Raw Detection Details / تفاصيل الاكتشافات الخام"):
            raw_detections_df = pd.DataFrame(filtered_data)
            if not raw_detections_df.empty:
                st.dataframe(raw_detections_df, use_container_width=True)
    else:
        st.warning("No residue data available for analysis. / لا توجد بيانات متبقيات للتحليل")


# ============================================================================
# QUALITY INDEX WINDOW
# ============================================================================

def show_quality_index_window(
    residue_data: List[Dict[str, Any]],
    commodity: str = "Total Vegetables",
    query: str = ""
):
    """
    Display Quality Index (IqR) assessment window.
    Uses session state to persist data across filter changes.
    """
    # Use session state data if passed data is empty
    if not residue_data:
        residue_data = st.session_state.get('iqr_residue_data', [])
        query = st.session_state.get('iqr_query', query)
        commodity = st.session_state.get('iqr_commodity', commodity)
    
    st.markdown("---")
    
    # Header with close button
    col_title, col_close = st.columns([6, 1])
    with col_title:
        st.subheader("📐 Quality Index (IqR) Assessment / مؤشر الجودة")
    with col_close:
        if st.button("❌ Close", key="close_iqr_window"):
            st.session_state['iqr_show_window'] = False
            st.session_state.pop('iqr_residue_data', None)
            st.rerun()
    
    st.markdown("""
    **Index of Quality for Residues (IqR)** = Concentration / MRL  
    مؤشر جودة المتبقيات = التركيز / الحد الأقصى المسموح
    """)
    
    # Detect sample type from query
    detected_sample = detect_sample_type(query) if query else None
    
    if detected_sample:
        st.success(f"🔍 Detected sample type: **{detected_sample[0]}** ({detected_sample[1]})")
    
    # Initialize session state for IqR commodity tracking
    if 'iqr_selected_commodity' not in st.session_state:
        default_commodity = detected_sample[0] if detected_sample and detected_sample[0] in SAUDI_IR_DATA else "Total Vegetables"
        st.session_state['iqr_selected_commodity'] = default_commodity
    
    # Show parameter input form (simplified for IqR - no body weight needed)
    col1, col2 = st.columns(2)
    
    with col1:
        commodity_options = [k for k in SAUDI_IR_DATA.keys() if k != "Default"]
        
        # Get current commodity from session state
        current_commodity = st.session_state.get('iqr_selected_commodity', 'Total Vegetables')
        current_idx = commodity_options.index(current_commodity) if current_commodity in commodity_options else 0
        
        selected_commodity = st.selectbox(
            "🥬 Commodity / المنتج",
            options=commodity_options,
            index=current_idx,
            help="Changing commodity will re-query database for that sample type"
        )
        
        # Check if commodity changed - re-query database
        if selected_commodity != st.session_state.get('iqr_selected_commodity'):
            st.session_state['iqr_selected_commodity'] = selected_commodity
            # Re-query database for new sample type
            arabic_sample = COMMODITY_TO_ARABIC.get(selected_commodity, '')
            new_data = get_residue_data_for_sample(arabic_sample)
            # Update data (even if empty)
            st.session_state['iqr_residue_data'] = new_data
            st.rerun()
    
    with col2:
        # UPDATED: Show if population-specific rates are available for this commodity
        from modules.risk_assessment_service import RiskAssessmentConfig
        
        has_detailed = RiskAssessmentConfig.has_detailed_rates(selected_commodity)
        
        st.info(f"🔍 Sample Filter: **{selected_commodity}**")
        
        if has_detailed:
            st.success("✓ Population-specific rates available")
            
            # Show available populations
            available_pops = RiskAssessmentConfig.get_available_populations(selected_commodity)
            if available_pops:
                st.caption(f"Data for: {', '.join(available_pops[:3])}...")
        else:
            st.warning("⚠️ Using standard rates")
        


    
    st.markdown("---")
    
    # Calculate metrics
    if residue_data:
        # Use the new sample-level IQR calculation
        iqr_analysis = calculate_sample_iqr_summary(
            residue_data,
            commodity=selected_commodity
        )
        
        # Summary metrics
        st.markdown(f"### 📊 Quality Summary for {selected_commodity} / ملخص الجودة")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "🥇 Excellent (IQR=0)",
                f"{iqr_analysis['category_counts']['Excellent']}",
                f"{iqr_analysis['category_percentages']['Excellent']:.1f}%"
            )
        
        with col2:
            st.metric(
                "✅ Good (0<IQR≤0.6)",
                f"{iqr_analysis['category_counts']['Good']}",
                f"{iqr_analysis['category_percentages']['Good']:.1f}%"
            )
        
        with col3:
            st.metric(
                "⚠️ Adequate (0.6<IQR≤1)",
                f"{iqr_analysis['category_counts']['Adequate']}",
                f"{iqr_analysis['category_percentages']['Adequate']:.1f}%"
            )
        
        with col4:
            st.metric(
                "❌ Inadequate (IQR>1)",
                f"{iqr_analysis['category_counts']['Inadequate']}",
                f"{iqr_analysis['category_percentages']['Inadequate']:.1f}%"
            )
        
        st.info(f"📊 Total Samples Analyzed: **{iqr_analysis['total_samples']}**")
        
        # Quality interpretation based on categories
        inadequate_pct = iqr_analysis['category_percentages']['Inadequate']
        if inadequate_pct > 10:
            st.error(f"⚠️ **مشكلة جودة كبيرة** - {inadequate_pct:.1f}% من العينات غير ملائمة")
        elif inadequate_pct > 0:
            st.warning(f"⚡ **تحذير جودة** - {inadequate_pct:.1f}% من العينات غير ملائمة")
        else:
            st.success(f"✅ **الجودة ممتازة** - لا توجد عينات غير ملائمة")
        
        st.markdown("---")
        
        # Pie chart for category distribution
        st.markdown("### 📈 Sample Quality Distribution / توزيع جودة العينات")
        
        chart_data = pd.DataFrame([
            {"Category": "Excellent (IQR=0)", "Count": iqr_analysis['category_counts']['Excellent'], "Color": "#28a745"},
            {"Category": "Good (0<IQR≤0.6)", "Count": iqr_analysis['category_counts']['Good'], "Color": "#17a2b8"},
            {"Category": "Adequate (0.6<IQR≤1)", "Count": iqr_analysis['category_counts']['Adequate'], "Color": "#ffc107"},
            {"Category": "Inadequate (IQR>1)", "Count": iqr_analysis['category_counts']['Inadequate'], "Color": "#dc3545"},
        ])
        
        # Filter out zero counts
        chart_data = chart_data[chart_data['Count'] > 0]
        
        if not chart_data.empty:
            import plotly.express as px
            fig = px.pie(
                chart_data,
                names="Category",
                values="Count",
                title="Sample Quality Categories",
                color="Category",
                color_discrete_map={
                    "Excellent (IQR=0)": "#28a745",
                    "Good (0<IQR≤0.6)": "#17a2b8",
                    "Adequate (0.6<IQR≤1)": "#ffc107",
                    "Inadequate (IQR>1)": "#dc3545"
                }
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        # NEW: Monthly IqR Trend Analysis
        show_monthly_iqr_trend(residue_data)
        
        st.markdown("---")
        
        # Sample details table
        st.markdown("### 📋 Sample IQR Details / تفاصيل مؤشر الجودة لكل عينة")
        
        sample_details_df = pd.DataFrame([
            {
                "Sample Code": s['sample_code'],
                "Pesticides": s['pesticide_count'],
                "Total IQR": s['total_iqr'],
                "Category": s['category']
            }
            for s in iqr_analysis['sample_iqr_details']
        ])
        
        if not sample_details_df.empty:
            sample_details_df = sample_details_df.sort_values("Total IQR", ascending=False)
            
            # Color coding for table
            def highlight_category(row):
                if row['Category'] == 'Inadequate':
                    return ['background-color: #f8d7da'] * len(row)
                elif row['Category'] == 'Adequate':
                    return ['background-color: #fff3cd'] * len(row)
                elif row['Category'] == 'Good':
                    return ['background-color: #d4edda'] * len(row)
                else:
                    return ['background-color: #cce5ff'] * len(row)
            
            st.dataframe(
                sample_details_df.style.apply(highlight_category, axis=1).format({
                    "Total IQR": "{:.4f}"
                }),
                use_container_width=True,
                hide_index=True
            )
        
    else:
        st.warning("No residue data available for analysis. / لا توجد بيانات متبقيات للتحليل")


# ============================================================================
# MAIN TRIGGER FUNCTION
# ============================================================================

def process_triggered_query(
    query: str,
    residue_data: List[Dict[str, Any]],
    commodity: str = "Total Vegetables"
) -> bool:
    """
    Check if query triggers a specialized window and display it.
    Passes query for sample type detection.
    """
    trigger = detect_query_type(query)
    
    if trigger == "[TRIGGER_UI: HEALTH_RISK_WINDOW]":
        show_health_risk_window(residue_data, commodity, query=query)
        return True
    elif trigger == "[TRIGGER_UI: QUALITY_INDEX_WINDOW]":
        show_quality_index_window(residue_data, commodity, query=query)
        return True
    
    return False
