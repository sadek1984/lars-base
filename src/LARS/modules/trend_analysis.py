import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os


from modules.utils import map_season_names, calculate_violations, load_data_from_path

def show_trend_analysis_page(api_client):
    # ============================================================================
    # TAB 4: TREND ANALYSIS
    # ============================================================================

    st.header("📈 Contamination Trend Analysis")
    
    st.info("""
    **Business Value:** Track how contamination patterns change over time.
    - Identify if contamination is improving or worsening
    - Monitor effectiveness of interventions
    - Predict future contamination risks
    """)
    
    # Load data
    df = load_data_from_path()
    
    if df is None:
        st.markdown("### 📤 Upload Your Data")
        
        # File uploader with multiple file types
        uploaded_file = st.file_uploader(
            "Upload CSV or Excel file",
            type=['csv', 'xlsx', 'xls'],
            help="Drag and drop file here (Limit 200MB per file)"
        )
        
        if uploaded_file:
            try:
                # Determine file type and read accordingly
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                with st.spinner(f"📂 Loading {file_extension.upper()} file..."):
                    if file_extension == 'csv':
                        df = pd.read_csv(uploaded_file)
                    elif file_extension in ['xlsx', 'xls']:
                        # For Excel files, allow sheet selection
                        excel_file = pd.ExcelFile(uploaded_file)
                        
                        if len(excel_file.sheet_names) > 1:
                            st.info(f"📋 Found {len(excel_file.sheet_names)} sheets in the Excel file")
                            selected_sheet = st.selectbox(
                                "Select sheet to analyze:",
                                options=excel_file.sheet_names,
                                index=0
                            )
                        else:
                            selected_sheet = excel_file.sheet_names[0]
                        
                        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                    else:
                        st.error(f"❌ Unsupported file type: {file_extension}")
                        return
                
                st.success(f"✅ Data uploaded successfully from {uploaded_file.name}!")
                
                # Show data preview
                with st.expander("👀 Preview Data"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Rows", len(df))
                    with col2:
                        st.metric("Total Columns", len(df.columns))
                    with col3:
                        st.metric("Memory Usage", f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
                    
                    st.dataframe(df.head(10), use_container_width=True)
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")
                return
        else:
            st.info("Expected columns: vegetable_english, season, pesticide, reading, limits")
            return

    # Use shared utilities
    df = map_season_names(df)
    df = calculate_violations(df)


     # ===== VIOLATION CALCULATION =====

    st.info("🔧 Analyzing existing is_compliant column...")

    # ✅ Check what's actually in is_compliant
    if 'is_compliant' in df.columns:
        with st.expander("📊 Current is_compliant Analysis"):
            st.write("**Data type:**", df['is_compliant'].dtype)
            st.write("**Unique values:**", df['is_compliant'].unique())
            st.write("**Value counts:**")
            st.write(df['is_compliant'].value_counts())
            
            # Show sample rows
            sample = df[['vegetable_english', 'pesticide', 'reading', 'limits', 'is_compliant']].head(10)
            st.dataframe(sample, use_container_width=True)

    # Clean the data
    df = df.dropna(subset=['reading', 'limits'])

    # Ensure numeric types for reading and limits
    df['reading'] = pd.to_numeric(df['reading'], errors='coerce')
    df['limits'] = pd.to_numeric(df['limits'], errors='coerce')

    # Remove invalid values
    df = df.dropna(subset=['reading', 'limits'])
    df = df[(df['reading'] >= 0) & (df['limits'] > 0)]

    # ✅ RECALCULATE violations regardless of existing column
    st.info("🔧 Recalculating violations from scratch...")

    # Drop existing violation columns
    for col in ['violation', 'violation_numeric', 'is_violation']:
        if col in df.columns:
            df = df.drop(columns=[col])

    # ✅ CORRECT LOGIC: A violation occurs when reading EXCEEDS limits
    # is_compliant should be TRUE (1) when reading <= limits
    # is_compliant should be FALSE (0) when reading > limits

    df['violation_numeric'] = (df['reading'] > df['limits']).astype(int)  # 1 = violation
    df['is_compliant_NEW'] = (df['reading'] <= df['limits']).astype(int)  # 1 = compliant
    df['violation'] = (df['reading'] > df['limits'])  # Boolean

    # ✅ Compare with existing column if it exists
    if 'is_compliant' in df.columns:
        with st.expander("🔍 Comparison: Old vs New Calculation"):
            comparison = df[['vegetable_english', 'pesticide', 'reading', 'limits', 
                            'is_compliant', 'is_compliant_NEW', 'violation_numeric']].head(20).copy()
            
            # Ensure old column is numeric for comparison
            comparison['is_compliant_old'] = pd.to_numeric(comparison['is_compliant'], errors='coerce')
            
            comparison['Match'] = comparison['is_compliant_old'] == comparison['is_compliant_NEW']
            
            st.dataframe(comparison, use_container_width=True)
            
            matches = comparison['Match'].sum()
            total = len(comparison)
            st.write(f"**Matching rows: {matches}/{total}**")
            
            if matches < total:
                st.warning(f"⚠️ Found {total - matches} mismatches! Using new calculation.")

    # Use the new calculation
    df['is_compliant'] = df['is_compliant_NEW']
    df = df.drop(columns=['is_compliant_NEW'])

    # ✅ Verify results
    total_violations = int(df['violation_numeric'].sum())
    total_samples = len(df)
    violation_rate = (total_violations / total_samples * 100) if total_samples > 0 else 0

    with st.expander("✅ Final Calculation Results"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Samples", total_samples)
        with col2:
            st.metric("Violations", total_violations)
        with col3:
            st.metric("Violation Rate", f"{violation_rate:.1f}%")
        
        # Show logic verification
        st.write("**Logic Verification (first 10 rows):**")
        verify = df[['vegetable_english', 'pesticide', 'reading', 'limits', 'violation_numeric']].head(10).copy()
        verify['Check'] = verify.apply(
            lambda x: '✅' if (x['violation_numeric'] == 1 and x['reading'] > x['limits']) or 
                            (x['violation_numeric'] == 0 and x['reading'] <= x['limits']) else '❌',
            axis=1
        )
        st.dataframe(verify, use_container_width=True)

    # Final validation
    if total_violations <= 0:
        st.error("❌ ERROR: No violations found or negative count!")
        st.info("Check if all your samples are truly compliant, or if there's a data issue.")
    else:
        st.success(f"✅ Successfully calculated {total_violations} violations ({violation_rate:.1f}% rate)")

    # Show final metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Samples", total_samples)
    with col2:
        st.metric("Total Violations", total_violations)
    with col3:
        st.metric("Violation Rate", f"{violation_rate:.1f}%")
    with col4:
        compliant = total_samples - total_violations
        st.metric("Compliant Samples", compliant)

    # Check if we have temporal data
    if 'year' in df.columns or 'month' in df.columns or 'date' in df.columns:
        
        # Time series by pesticide group
        if 'pesticide_group' in df.columns:
            st.subheader("📊 Violation Trends by Pesticide Group")
            
            # Assuming you have year and month
            if 'year' in df.columns and 'month' in df.columns:
                
                # --- START: ALL LOGIC INDENTED ---
                
                df['period'] = df['year'].astype(str) + '-' + df['month'].astype(str).str.zfill(2)
                
                # --- THIS IS THE FIX ---
                # This is your original code. DO NOT use '...' here.
                trend_data = df.groupby(['period', 'pesticide_group']).agg({
                    'violation': ['sum', 'count', 'mean']
                }).reset_index()
                # --- END FIX ---
                
                trend_data.columns = ['Period', 'Pesticide_Group', 'Violations', 'Tests', 'Violation_Rate']
                
                # Sort by group and time
                trend_data = trend_data.sort_values(by=['Pesticide_Group', 'Period'])

                # Create the cumulative column (for the "good" chart)
                trend_data['Cumulative_Violations'] = trend_data.groupby('Pesticide_Group')['Violations'].cumsum()

                # Plot the cumulative chart
                fig_trend = px.line(
                    trend_data,
                    x='Period',
                    y='Cumulative_Violations',  # <-- Plotting the total
                    color='Pesticide_Group',
                    title='Cumulative Violation Trends by Pesticide Group', 
                    markers=True
                )
                
                fig_trend.update_layout(
                    xaxis_title='Time Period',
                    yaxis_title='Total Violations', # <-- Updated label
                    height=500,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_trend, use_container_width=True)
            
            else:
                # This runs if 'year' or 'month' columns are missing
                st.warning("Trend chart skipped: Data does not contain 'year' and 'month' columns.")
    
    veg_violations = df.groupby('vegetable_english')['violation_numeric'].sum().nlargest(10).reset_index()
    veg_violations.columns = ['Vegetable', 'Total_Violations']
    
    
    pest_violations = df.groupby('pesticide')['violation_numeric'].sum().nlargest(10).reset_index()
    pest_violations.columns = ['Pesticide', 'Total_Violations']
    
    
    # ============================================================================
    # COMBINED COMPARISON VIEW (BONUS)
    # ============================================================================
    st.subheader("🔄 Side-by-Side Comparison")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Top 5 Vegetables - Radial/Polar Chart
        top5_veg = veg_violations.head(5)
        fig_veg_radar = go.Figure()
        
        fig_veg_radar.add_trace(go.Scatterpolar(
            r=top5_veg['Total_Violations'].tolist() + [top5_veg['Total_Violations'].iloc[0]],
            theta=top5_veg['Vegetable'].tolist() + [top5_veg['Vegetable'].iloc[0]],
            fill='toself',
            fillcolor='rgba(255, 99, 71, 0.3)',
            line=dict(color='tomato', width=2),
            name='Vegetables'
        ))
        
        fig_veg_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, top5_veg['Total_Violations'].max() * 1.2])
            ),
            title='Top 5 Vegetables - Polar View',
            height=400
        )
        st.plotly_chart(fig_veg_radar, use_container_width=True)
    
    with col2:
        # Top 5 Pesticides - Radial/Polar Chart
        top5_pest = pest_violations.head(5)
        fig_pest_radar = go.Figure()
        
        fig_pest_radar.add_trace(go.Scatterpolar(
            r=top5_pest['Total_Violations'].tolist() + [top5_pest['Total_Violations'].iloc[0]],
            theta=top5_pest['Pesticide'].tolist() + [top5_pest['Pesticide'].iloc[0]],
            fill='toself',
            fillcolor='rgba(255, 165, 0, 0.3)',
            line=dict(color='orange', width=2),
            name='Pesticides'
        ))
        
        fig_pest_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, top5_pest['Total_Violations'].max() * 1.2])
            ),
            title='Top 5 Pesticides - Polar View',
            height=400
        )
        st.plotly_chart(fig_pest_radar, use_container_width=True)

    # ============================================================================
    # KEY INSIGHTS & RECOMMENDATIONS
    # ============================================================================
    
    st.subheader("💡 Key Insights & Recommendations")
    
    # Calculate key metrics for insights
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Overall trend direction
        if 'year' in df.columns:
            current_year = df['year'].max()
            prev_year = current_year - 1
            current_violations = df[df['year'] == current_year]['violation_numeric'].mean()
            prev_violations = df[df['year'] == prev_year]['violation_numeric'].mean()
            trend_direction = "Improving" if current_violations < prev_violations else "Worsening"
            trend_pct = abs((current_violations - prev_violations) / prev_violations * 100)
            st.metric("Overall Trend", trend_direction, f"{trend_pct:.1f}%")
        else:
            st.metric("Violation Rate", f"{df['violation_numeric'].mean():.1%}", "")
    
    with col2:
        # Most problematic vegetable
        worst_veg = veg_violations.iloc[0]['Vegetable']
        worst_veg_count = veg_violations.iloc[0]['Total_Violations']
        st.metric("Highest Risk Vegetable", worst_veg, f"{worst_veg_count} violations")
    
    with col3:
        # Most problematic pesticide
        worst_pest = pest_violations.iloc[0]['Pesticide']
        worst_pest_count = pest_violations.iloc[0]['Total_Violations']
        st.metric("Highest Risk Pesticide", worst_pest, f"{worst_pest_count} violations")
    
    # Action recommendations
    st.warning("""
    **🎯 Recommended Actions:**
    1. **Immediate Focus**: Target {worst_veg} and {worst_pest} combinations
    2. **Testing Priority**: Increase sampling frequency for top 3 high-violation vegetables
    3. **Intervention**: Review application practices for {worst_pest} usage
    4. **Monitoring**: Track progress monthly to measure intervention effectiveness
    """.format(worst_veg=worst_veg, worst_pest=worst_pest))
    
    # Success stories (if any)
    if len(veg_violations) > 1:
        best_veg = veg_violations.iloc[-1]['Vegetable']
        best_veg_count = veg_violations.iloc[-1]['Total_Violations']
        
        st.success(f"""
        **✅ Success Story**: {best_veg} has the lowest violation count ({best_veg_count}). 
        Consider studying its cultivation practices for replication in other crops.
        """)

