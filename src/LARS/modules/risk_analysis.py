import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.express as px
import plotly.graph_objects as go
from modules.utils import map_season_names, calculate_violations, load_data_from_path

# Import risk assessment service
try:
    from modules.risk_assessment_service import (
        RiskAssessmentService,
        get_population_options,
        get_population_weight,
        POPULATION_CLASSES,
        EU_COMMODITY_CODES,
        EUMRLClient
    )
    RISK_SERVICE_AVAILABLE = True
except ImportError as e:
    RISK_SERVICE_AVAILABLE = False
    class RiskAssessmentService:
        pass
    get_population_options = lambda: []
    get_population_weight = lambda x: 60
    print(f"⚠️ Risk assessment service not available: {e}")


def show_eu_mrl_lookup_section(df: pd.DataFrame):
    """
    Show a dedicated EU MRL lookup tool using local database.
    Uses pre-downloaded EU MRL data for instant lookups.
    """
    import sqlite3
    from pathlib import Path
    
    st.markdown("---")
    st.subheader("🌐 EU MRL Lookup Tool / أداة البحث عن الحدود الأوروبية")
    
    # Check if database exists
    db_path = Path(__file__).parent.parent / "scripts" / "eu_mrl_data" / "eu_mrl.db"
    
    if not db_path.exists():
        st.warning("⚠️ EU MRL database not found. Run `scripts/download_eu_mrl.py` to download the data.")
        st.link_button(
            "🔗 Open EU Pesticides Database Online",
            "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/start/screen/mrls",
            type="secondary"
        )
        return
    
    st.markdown("""
    Look up the official **Maximum Residue Limit (MRL)** from the EU Pesticides Database.
    Data is stored locally for instant lookups (239,000+ records).
    """)
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        # Get unique pesticides from data
        if 'pesticide' in df.columns:
            pesticides = sorted(df['pesticide'].dropna().unique().tolist())
        else:
            pesticides = ["Chlorpyrifos", "Imidacloprid", "Cypermethrin", "Fipronil", "Atrazine"]
        
        selected_pesticide = st.selectbox(
            "🧪 Select Pesticide / اختر المبيد",
            pesticides,
            index=0,
            key="eu_mrl_pesticide"
        )
    
    with col2:
        # Common commodities for vegetables
        commodities = [
            "Tomatoes", "Cucumbers", "Peppers", "Aubergines/eggplants",
            "Lettuce", "Spinach", "Carrots", "Potatoes", "Beans",
            "Courgettes", "Okra", "Cabbages", "Cauliflower"
        ]
        selected_commodity = st.selectbox(
            "🥦 Select Commodity / اختر المنتج",
            commodities,
            index=0,
            key="eu_mrl_commodity"
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Lookup MRL", type="primary", key="eu_mrl_search")
    
    # Perform search
    if search_clicked:
        with st.spinner("Searching EU MRL database..."):
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Search with LIKE for flexibility
                cursor.execute('''
                    SELECT pesticide, product, mrl_value, mrl_text, is_loq
                    FROM eu_mrl
                    WHERE pesticide_lower LIKE ? AND product_lower LIKE ?
                    ORDER BY mrl_value ASC
                    LIMIT 20
                ''', (f'%{selected_pesticide.lower()}%', f'%{selected_commodity.lower()}%'))
                
                results = [dict(row) for row in cursor.fetchall()]
                conn.close()
                
                if results:
                    st.success(f"✅ Found {len(results)} MRL entries!")
                    
                    # Display primary result
                    primary = results[0]
                    mrl_val = primary['mrl_value'] if primary['mrl_value'] else primary['mrl_text']
                    is_loq = primary['is_loq']
                    
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    
                    with col_m1:
                        st.metric("📊 EU MRL", f"{mrl_val} mg/kg")
                    
                    with col_m2:
                        st.metric("🧪 Pesticide", primary['pesticide'][:25])
                    
                    with col_m3:
                        st.metric("🥦 Product", primary['product'][:20])
                    
                    with col_m4:
                        st.metric("⚠️ At LOQ?", "✅ Yes" if is_loq else "❌ No")
                    
                    # Show comparison with dataset if available
                    if 'pesticide' in df.columns and 'limits' in df.columns:
                        matching = df[df['pesticide'].str.lower() == selected_pesticide.lower()]
                        if not matching.empty:
                            dataset_mrl = matching['limits'].iloc[0]
                            st.info(f"📝 **Your Dataset MRL:** {dataset_mrl} mg/kg | **EU MRL:** {mrl_val} mg/kg")
                    
                    # Show all results in expander
                    if len(results) > 1:
                        with st.expander(f"📋 All {len(results)} matching entries"):
                            results_df = pd.DataFrame(results)
                            results_df['LOQ'] = results_df['is_loq'].apply(lambda x: '✅' if x else '')
                            st.dataframe(
                                results_df[['pesticide', 'product', 'mrl_value', 'LOQ']],
                                use_container_width=True,
                                hide_index=True
                            )
                    
                    st.caption("Source: EU Pesticides Database (local copy)")
                else:
                    st.warning(f"❌ No MRL found for '{selected_pesticide}' in '{selected_commodity}'")
                    st.info("💡 Try different spellings or broader product categories.")
            
            except Exception as e:
                st.error(f"Database error: {e}")
    
    # Database info
    with st.expander("📚 Database Info & Quick Links"):
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM eu_mrl")
            count = cursor.fetchone()[0]
            conn.close()
            
            st.markdown(f"""
            - **Total Records:** {count:,} MRL entries
            - **Source:** [EU Pesticides Database](https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/start/screen/mrls)
            - **Update:** Run `python scripts/download_eu_mrl.py` to refresh data
            """)
        except:
            st.markdown("Database info unavailable")


def show_dietary_exposure_section(df: pd.DataFrame, risk_service: RiskAssessmentService):
    """Show dietary exposure and risk assessment section."""
    
    st.markdown("---")
    st.subheader("🧬 Dietary Exposure Assessment (PRIMo 4)")
    
    st.markdown("""
    Calculate **Estimated Daily Intake (EDI)**, **Hazard Quotient (HQc)**, and 
    **Hazard Index (HIc)** based on ADI values and population body weights.
    """)
    
    # Population and consumption settings
    col1, col2 = st.columns(2)
    
    with col1:
        # Population selector
        pop_options = get_population_options()
        pop_labels = [opt['label'] for opt in pop_options]
        pop_keys = [opt['key'] for opt in pop_options]
        
        selected_idx = st.selectbox(
            "🧑‍🤝‍🧑 Population Class / الفئة السكانية",
            range(len(pop_labels)),
            format_func=lambda i: pop_labels[i],
            index=pop_keys.index('adult') if 'adult' in pop_keys else 0,
            help="Select population group for body weight. Based on PRIMo 4 methodology."
        )
        selected_pop_data = pop_options[selected_idx]
        selected_population = selected_pop_data['key']
        body_weight = selected_pop_data['weight']
    
    with col2:
        # Consumption rate
        consumption_rate = st.number_input(
            "🍽️ Consumption Rate (kg/day)",
            min_value=0.001,
            max_value=1.0,
            value=0.1,
            step=0.01,
            help="Daily consumption of the food commodity in kg"
        )
    
    # Display selected parameters
    st.info(f"**Selected:** {selected_pop_data['name_en']} "
            f"({selected_pop_data['name_ar']}) - "
            f"Body weight: {body_weight} kg")
    
    # Note about EU MRL Lookup
    st.caption("💡 To look up real-time EU MRLs for specific pesticides, use the **EU MRL Lookup Tool** below.")
    
    # Analyze data
    if 'pesticide' in df.columns and 'reading' in df.columns:
        # Get unique pesticide-concentration pairs
        pesticide_data = df[['pesticide', 'reading']].dropna()
        pesticide_data = pesticide_data[pesticide_data['reading'] > 0]
        
        if len(pesticide_data) > 0:
            # Prepare sample results
            sample_results = [
                {'pesticide': row['pesticide'], 'concentration': row['reading']}
                for _, row in pesticide_data.iterrows()
            ]
            
            # Run risk analysis (uses dataset MRLs for batch analysis)
            with st.spinner("Analyzing dietary exposure..."):
                analysis = risk_service.analyze_sample_risk(
                    sample_results,
                    population_class=selected_population,
                    consumption_rate=consumption_rate
                )
            
            # Display summary metrics
            st.markdown("### 📊 Risk Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Pesticides Analyzed",
                    f"{analysis['analyzed_count']}/{analysis['pesticide_count']}",
                    help="Number of pesticides with ADI data available"
                )
            
            with col2:
                total_hic = analysis['hazard_index']['total_hic']
                st.metric(
                    "Total Hazard Index (HIc)",
                    f"{total_hic:.4f}",
                    delta=f"{total_hic*100:.1f}% of ADI" if total_hic < 1 else "⚠️ Exceeds limit",
                    delta_color="normal" if total_hic < 1 else "inverse"
                )
            
            with col3:
                if analysis['highest_risk_pesticide']:
                    st.metric(
                        "Highest Risk Pesticide",
                        analysis['highest_risk_pesticide']['pesticide'][:15],
                        f"HQc: {analysis['highest_risk_pesticide']['hqc']:.3f}"
                    )
                else:
                    st.metric("Highest Risk Pesticide", "N/A")
            
            with col4:
                if analysis['highest_risk_group']:
                    st.metric(
                        "Highest Risk Group",
                        analysis['highest_risk_group']['name_en'][:15],
                        f"HIc: {analysis['highest_risk_group']['hic']:.3f}"
                    )
                else:
                    st.metric("Highest Risk Group", "N/A")
            
            # Overall interpretation
            if total_hic >= 1:
                st.error(f"⚠️ **Total risk is UNACCEPTABLE** - HIc = {total_hic:.4f} (≥1)")
            elif total_hic >= 0.5:
                st.warning(f"⚡ **Elevated risk** - HIc = {total_hic:.4f} (≥0.5)")
            else:
                st.success(f"✅ **Risk is acceptable** - HIc = {total_hic:.4f} (<0.5)")
            
            # Chemical Group Analysis
            st.markdown("### 🧪 Risk by Chemical Group")
            
            hic_by_group = analysis['hazard_index'].get('by_chemical_group', {})
            
            if hic_by_group:
                # Create DataFrame for visualization
                group_data = []
                for key, data in hic_by_group.items():
                    group_data.append({
                        'Group': data['name_en'],
                        'Group_AR': data['name_ar'],
                        'HIc': data['hic'],
                        'HIc_Percent': data['hic_percent'],
                        'Pesticides': data['pesticide_count']
                    })
                
                group_df = pd.DataFrame(group_data)
                group_df = group_df.sort_values('HIc', ascending=False)
                
                # Bar chart by chemical group
                fig = px.bar(
                    group_df,
                    x='Group',
                    y='HIc',
                    color='HIc',
                    color_continuous_scale='RdYlGn_r',
                    title="Hazard Index by Chemical Group",
                    labels={'HIc': 'Hazard Index', 'Group': 'Chemical Group'},
                    hover_data=['Group_AR', 'Pesticides', 'HIc_Percent']
                )
                
                # Add threshold line
                fig.add_hline(
                    y=1.0, 
                    line_dash="dash", 
                    line_color="red",
                    annotation_text="Risk Threshold (HIc=1)"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Table view
                with st.expander("📋 Detailed Chemical Group Data"):
                    display_df = group_df.copy()
                    display_df['HIc'] = display_df['HIc'].apply(lambda x: f"{x:.4f}")
                    display_df['HIc_Percent'] = display_df['HIc_Percent'].apply(lambda x: f"{x:.2f}%")
                    st.dataframe(display_df, use_container_width=True)
            
            # Individual Pesticide Risks
            st.markdown("### 🔬 Individual Pesticide Risk Analysis")
            
            individual_risks = analysis.get('individual_risks', [])
            
            if individual_risks:
                # Create DataFrame
                risk_df = pd.DataFrame(individual_risks)
                risk_df = risk_df.sort_values('hqc', ascending=False)
                
                # Top 10 highest risk pesticides chart
                top_risks = risk_df.head(10)
                
                fig = px.bar(
                    top_risks,
                    x='pesticide',
                    y='hqc',
                    color='hqc',
                    color_continuous_scale='Reds',
                    title="Top 10 Highest Risk Pesticides (HQc)",
                    labels={'hqc': 'Hazard Quotient', 'pesticide': 'Pesticide'}
                )
                
                fig.add_hline(
                    y=1.0, 
                    line_dash="dash", 
                    line_color="red",
                    annotation_text="Risk Threshold"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Full table
                with st.expander("📋 Complete Pesticide Risk Data"):
                    base_cols = ['pesticide', 'concentration', 'adi', 'edi', 'hqc', 'hqc_percent', 'chemical_group', 'interpretation']
                    col_names = ['Pesticide', 'Conc (mg/kg)', 'ADI', 'EDI', 'HQc', 'HQc %', 'Chemical Group', 'Risk Level']
                    
                    # Only include columns that exist
                    available_cols = [c for c in base_cols if c in risk_df.columns]
                    available_names = [col_names[base_cols.index(c)] for c in available_cols]
                    
                    display_risk_df = risk_df[available_cols].copy()
                    display_risk_df.columns = available_names
                    
                    # Format numeric columns
                    if 'HQc' in display_risk_df.columns:
                        display_risk_df['HQc'] = display_risk_df['HQc'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
                    if 'EDI' in display_risk_df.columns:
                        display_risk_df['EDI'] = display_risk_df['EDI'].apply(lambda x: f"{x:.8f}" if pd.notna(x) else "N/A")
                    if 'HQc %' in display_risk_df.columns:
                        display_risk_df['HQc %'] = display_risk_df['HQc %'].apply(lambda x: f"{x:.4f}%" if pd.notna(x) else "N/A")
                         
                    st.dataframe(display_risk_df, use_container_width=True)
            
            # Missing ADI warning
            if analysis['missing_adi_count'] > 0:
                with st.expander(f"⚠️ {analysis['missing_adi_count']} Pesticides Missing ADI Data"):
                    st.write("The following pesticides could not be analyzed due to missing ADI values:")
                    for pest in analysis['missing_adi']:
                        st.write(f"  - {pest}")
        else:
            st.warning("No valid pesticide concentration data found in the dataset.")
    else:
        st.warning("Required columns 'pesticide' and 'reading' not found in the data.")


def show_risk_analysis_page(api_client):
    """Advanced insights with risk combinations and forecasting"""
    
    st.title("🎯 Advanced Risk Intelligence")
    
    st.markdown("""
    **Strategic Analytics for Lab Operations**
    - Identify high-risk vegetable-pesticide combinations
    - Forecast seasonal contamination risks
    - **Dietary exposure assessment (EDI/HQc/HIc)**
    - Optimize testing schedules and resource allocation
    """)
    
    # Initialize risk service if available
    risk_service = None
    if RISK_SERVICE_AVAILABLE:
        try:
            risk_service = RiskAssessmentService()
        except Exception as e:
            st.warning(f"⚠️ Could not initialize risk service: {e}")
    
    # Load data
    df = load_data_from_path()
    
    if df is None:
        st.warning("📤 Please upload your data first")
        uploaded_file = st.file_uploader("Upload CSV or Excel file", type=['csv', 'xlsx', 'xls'])
        
        if uploaded_file:
            try:
                file_extension = uploaded_file.name.split('.')[-1].lower()
                if file_extension == 'csv':
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                st.success("✅ Data loaded successfully!")
            except Exception as e:
                st.error(f"Error: {e}")
                return
        else:
            return
    
    # Ensure violations are calculated
    df = calculate_violations(df)
    
    # ===== DEBUG PANEL =====
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🐛 Debug Tools")
    
    if st.sidebar.checkbox("Show Debug Panel", value=False):
        st.markdown("---")
        st.markdown("## 🐛 DEBUG PANEL")
        
        with st.expander("📊 Raw Data Inspection", expanded=True):
            st.write("**DataFrame Shape:**", df.shape)
            st.write("**Columns:**")
            st.json(df.columns.tolist())
            
            debug_cols = ['vegetable_english', 'pesticide', 'reading', 'limits']
            if 'is_compliant' in df.columns:
                debug_cols.append('is_compliant')
            
            available_debug_cols = [col for col in debug_cols if col in df.columns]
            st.dataframe(df[available_debug_cols].head(20), use_container_width=True)
        
        with st.expander("🔍 Violation Column Analysis", expanded=True):
            st.write("**Checking existing columns:**")
            
            violation_related = ['is_compliant', 'violation', 'violation_numeric', 
                                'compliance', 'compliant', 'result', 'is_violation']
            
            for col in violation_related:
                if col in df.columns:
                    st.write(f"✅ Found column: `{col}`")
                    st.write(f"   - Type: {df[col].dtype}")
                    st.write(f"   - Unique values: {df[col].nunique()}")
                    st.write(f"   - Value counts:")
                    st.write(df[col].value_counts())
                else:
                    st.write(f"❌ Missing column: `{col}`")
    
    # Map seasons
    df = map_season_names(df)
    
    # Show data preview
    with st.expander("🔍 Data Preview & Validation"):
        st.dataframe(df.head(10), use_container_width=True)
    
    # ===== DIETARY EXPOSURE SECTION =====
    if risk_service:
        show_dietary_exposure_section(df, risk_service)
    else:
        st.info("💡 Dietary exposure analysis requires the risk assessment service. "
                "Please ensure `risk_assessment_service.py` is properly installed.")
    
    # ===== EU MRL LOOKUP TOOL =====
    if RISK_SERVICE_AVAILABLE:
        show_eu_mrl_lookup_section(df)
    
    st.markdown("---")
    
    # Interactive Heatmap
    st.subheader("🔥 Risk Combination Heatmap")
    
    # Group by vegetable and pesticide to see violation counts
    if 'vegetable_english' in df.columns and 'pesticide' in df.columns and 'is_violation' in df.columns:
        risk_matrix = df.groupby(['vegetable_english', 'pesticide'])['is_violation'].sum().unstack(fill_value=0)
        
        # Filter to TOP 15 vegetables and TOP 20 pesticides for readability
        top_vegs = df.groupby('vegetable_english')['is_violation'].sum().sort_values(ascending=False).head(15).index
        top_pests = df.groupby('pesticide')['is_violation'].sum().sort_values(ascending=False).head(20).index
        
        risk_matrix_filtered = risk_matrix.loc[risk_matrix.index.isin(top_vegs), risk_matrix.columns.isin(top_pests)]
        
        fig = px.imshow(risk_matrix_filtered,
                       labels=dict(x="Pesticide", y="Vegetable", color="Violations"),
                       color_continuous_scale="Reds",
                       title="Top Vegetable-Pesticide Risk Combinations")
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Heatmap requires 'vegetable_english', 'pesticide', and 'is_violation' columns.")

    # Seasonal Risk Distribution
    st.subheader("📅 Seasonal Risk Distribution")
    if 'season' in df.columns and 'is_violation' in df.columns:
        seasonal_risk = df.groupby('season')['is_violation'].mean().reset_index()
        seasonal_risk.columns = ['Season', 'Violation Rate']
        
        fig = px.bar(seasonal_risk, x='Season', y='Violation Rate',
                    color='Violation Rate', color_continuous_scale='Viridis',
                    title="Average Violation Rate by Season")
        st.plotly_chart(fig, use_container_width=True)
