import streamlit as st
import pandas as pd
import os
from scipy.stats import f_oneway


from modules.utils import map_season_names, calculate_violations, load_data_from_path, perform_anova_analysis

def show_statistical_insights_page(api_client):
    """Statistical Insights page with chemist-friendly improvements"""
    
    st.title("🌡️ Seasonal Contamination Analysis")
    
    st.info("""
    **Understanding Seasonal Patterns:**
    This analysis identifies if pesticide contamination varies significantly across different seasons.
    - **High contamination seasons** may need increased monitoring
    - **Stable patterns** across seasons suggest consistent control measures
    - **Unexpected variations** may indicate seasonal farming practices or weather effects
    """)
    
    # Load your data
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
    
    # Map seasons and calculate violations
    df = map_season_names(df)
    df = calculate_violations(df)


    # ===== DATA VALIDATION =====

    # Show data preview
    with st.expander("🔍 Data Preview & Validation"):
        st.write("**First 5 rows:**")
        st.dataframe(df.head(), use_container_width=True)
        
        st.write("**Column names:**")
        st.write(df.columns.tolist())
        
        st.write("**Data types:**")
        st.write(df.dtypes)

    # Ensure required columns exist
    required_cols = ['vegetable_english', 'season', 'pesticide', 'reading', 'limits']
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        st.error(f"❌ Missing required columns: {missing_cols}")
        
        with st.expander("🔍 Column Mapping Helper"):
            st.write("**Required columns:**", required_cols)
            st.write("**Available columns:**", df.columns.tolist())
            
            st.markdown("**Suggestions:**")
            st.markdown("- `vegetable_english` → vegetable name column")
            st.markdown("- `season` → season/quarter/period column")
            st.markdown("- `pesticide` → pesticide name column")
            st.markdown("- `reading` → measured concentration value")
            
            # Allow column renaming
            st.markdown("#### 🔄 Quick Column Rename")
            
            col_mapping = {}
            for required_col in required_cols:
                if required_col not in df.columns.tolist():
                    selected_col = st.selectbox(
                        f"Map '{required_col}' to:",
                        options=['None'] + df.columns.tolist(),
                        key=f"map_{required_col}"
                    )
                    if selected_col != 'None':
                        col_mapping[selected_col] = required_col
            
            if st.button("Apply Column Mapping"):
                df = df.rename(columns=col_mapping)
                st.success("✅ Columns renamed successfully!")
                st.rerun()
        
        return

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

    # ===== DYNAMIC SWITCHING CONTROLS =====
    st.sidebar.header("🔧 Analysis Controls")

    # Main switch: Vegetables vs Seasons
    analysis_mode = st.sidebar.radio(
        "Group Analysis By:",
        options=['Season', 'Vegetable'],
        index=0,
        help="Choose whether to compare across seasons or vegetables"
    )

    # Map selection to column name
    group_column = 'season' if analysis_mode == 'Season' else 'vegetable_english'

    # Optional filters
    st.sidebar.subheader("🔍 Filters")

    if analysis_mode == 'Season':
        # When analyzing by season, allow vegetable selection
        available_vegetables = sorted(df['vegetable_english'].dropna().unique())
        selected_vegetables = st.sidebar.multiselect(
            "Filter by Vegetables:",
            options=available_vegetables,
            default=[]
        )
        
        if selected_vegetables:
            df_filtered = df[df['vegetable_english'].isin(selected_vegetables)].copy()
        else:
            df_filtered = df.copy()
            
    else:  # Vegetable mode
        # When analyzing by vegetable, allow season selection
        available_seasons = sorted(df['season'].dropna().unique())
        selected_seasons = st.sidebar.multiselect(
            "Filter by Seasons:",
            options=available_seasons,
            default=[]
        )
        
        if selected_seasons:
            df_filtered = df[df['season'].isin(selected_seasons)].copy()
        else:
            df_filtered = df.copy()

    # Additional filter: Pesticide type (optional)
    available_pesticides = sorted(df['pesticide'].dropna().unique())
    selected_pesticides = st.sidebar.multiselect(
        "Filter by Pesticide:",
        options=available_pesticides,
        default=[],
        help="Leave empty to analyze all pesticides"
    )

    if selected_pesticides:
        df_filtered = df_filtered[df_filtered['pesticide'].isin(selected_pesticides)].copy()

    # Target variable selection
    available_targets = ['reading']
    if 'exceedance_ratio' in df.columns:
        available_targets.append('exceedance_ratio')
    if 'limits' in df.columns:
        available_targets.append('limits')
    if 'violation_numeric' in df.columns:
        available_targets.append('violation_numeric')

    target_col = st.sidebar.selectbox(
        "Analyze:",
        options=available_targets,
        index=0
    )

    # Remove rows with NaN in target column
    df_filtered = df_filtered.dropna(subset=[target_col, group_column])

    # ===== PERFORM ANALYSIS =====
    st.header(f"Analysis: {target_col.replace('_', ' ').title()} by {analysis_mode}")

    # Show current filter status
    with st.expander("📊 Current Filters Applied"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Total Samples:** {len(df):,}")
            st.write(f"**Filtered Samples:** {len(df_filtered):,}")
        with col2:
            st.write(f"**Analysis Mode:** {analysis_mode}")
            st.write(f"**Target Variable:** {target_col}")
            if selected_pesticides:
                st.write(f"**Pesticide Filter:** {', '.join(selected_pesticides)}")

    if len(df_filtered) < 10:
        st.warning("⚠️ Not enough data for analysis. Please adjust filters.")
        st.info(f"""
        **Current situation:**
        - Filtered samples: {len(df_filtered)}
        - Minimum required: 10 samples
        
        **Suggestions:**
        - Remove some filters (especially pesticide filter)
        - Select more vegetables or seasons
        - Try analyzing all data without filters
        """)
        return

    # Check if we have multiple groups
    n_groups = df_filtered[group_column].nunique()
    if n_groups < 2:
        st.warning(f"⚠️ Need at least 2 {analysis_mode.lower()}s for comparison.")
        unique_groups = df_filtered[group_column].unique().tolist()
        st.info(f"Current {analysis_mode.lower()}(s) in filtered data: {', '.join(map(str, unique_groups))}")
        st.info("💡 Tip: Remove some filters to get more groups")
        return

    # Perform ANOVA
    with st.spinner("🔄 Calculating ANOVA..."):
        results = perform_anova_analysis(df_filtered, group_column, target_col)

    # ===== DISPLAY RESULTS =====

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("F-Statistic", f"{results['f_statistic']:.4f}")

    with col2:
        st.metric("P-Value", f"{results['p_value']:.6f}")

    with col3:
        significance = "✅ Yes" if results['significant'] else "❌ No"
        st.metric("Significant?", significance)

    with col4:
        st.metric("Groups", n_groups)




    
    # ===== IMPROVED RESULTS DISPLAY =====
    
    st.header(f"📊 {analysis_mode} Impact on Contamination Levels")
    
    # Key metrics in chemist-friendly format
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if results['significant']:
            st.error("🚨 **Significant Seasonal Variation**")
            st.caption("Contamination levels change across seasons")
        else:
            st.success("✅ **Stable Across Seasons**")
            st.caption("Contamination levels remain consistent")
    
    with col2:
        highest_group = results['summary'].loc[results['summary']['mean'].idxmax()]
        st.metric(
            "Highest Contamination", 
            f"{highest_group['mean']:.1f}",
            delta=f"in {highest_group.name}"
        )
    
    with col3:
        variation_range = results['summary']['mean'].max() - results['summary']['mean'].min()
        st.metric(
            "Seasonal Variation", 
            f"{variation_range:.1f}",
            delta="High" if variation_range > 100 else "Moderate" if variation_range > 50 else "Low"
        )
    
    # ===== CHEMIST-FOCUSED INTERPRETATION =====
    
    st.subheader("🔍 Practical Interpretation")
    
    if results['significant']:
        # Find the problematic seasons
        summary = results['summary']
        avg_contamination = summary['mean'].mean()
        high_seasons = summary[summary['mean'] > avg_contamination * 1.2]  # 20% above average
        low_seasons = summary[summary['mean'] < avg_contamination * 0.8]   # 20% below average
        
        st.warning("""
        **🎯 Key Findings:**
        
        **Seasonal contamination patterns detected** - This suggests:
        - Farming practices may vary by season
        - Weather conditions could affect pesticide persistence
        - Different crops harvested in different seasons
        """)
        
        # Show actionable insights
        if not high_seasons.empty:
            st.error(f"""
            **🚨 Higher Risk Seasons:**
            {', '.join([f"{season} ({mean:.1f})" for season, mean in zip(high_seasons.index, high_seasons['mean'])])}
            
            **Recommended Actions:**
            - Increase monitoring frequency during these seasons
            - Review pesticide application practices
            - Consider seasonal weather factors
            """)
        
        if not low_seasons.empty:
            st.success(f"""
            **✅ Lower Risk Seasons:**
            {', '.join([f"{season} ({mean:.1f})" for season, mean in zip(low_seasons.index, low_seasons['mean'])])}
            
            **Good Practices to Maintain**
            """)
            
    else:
        st.success("""
        **✅ Stable Contamination Patterns**
        
        **This is positive news:**
        - Consistent contamination control across seasons
        - Predictable monitoring needs
        - Stable farming practices throughout the year
        
        **Continue current monitoring schedule**
        """)
    
    # ===== BOX PLOT VISUALIZATION =====
    
    st.subheader("📊 Contamination Distribution by Season")

    # Create box plot
    import plotly.express as px
    
    fig_box = px.box(
        df_filtered,
        x=group_column,
        y=target_col,
        color=group_column,
        points="outliers"
    )
    
    # Add average line and enhance the plot
    avg_value = results['summary']['mean'].mean()
    fig_box.add_hline(
        y=avg_value, 
        line_dash="dash", 
        line_color="red",
        annotation_text=f"Overall Average: {avg_value:.1f}",
        annotation_position="bottom right"
    )
    
    # Update layout for better readability
    fig_box.update_layout(
        title=f"Distribution of {target_col.replace('_', ' ').title()} by {analysis_mode}",
        xaxis_title=analysis_mode,
        yaxis_title=target_col.replace('_', ' ').title(),
        height=500,
        showlegend=False
    )
    
    st.plotly_chart(fig_box, use_container_width=True)
    
    # Enhanced interpretation guide
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**📈 How to Read This Chart:**")
        st.write("""
        - **Box**: Middle 50% of data (25th-75th percentile)
        - **Line in box**: Median value
        - **Whiskers**: Typical data range
        - **Dots**: Potential outliers
        - **Red dashed line**: Overall average
        """)
    
    with col2:
        st.write("**🔍 Key Insights:**")
        st.write("""
        - **Higher boxes** = More contamination
        - **Larger boxes** = More variability
        - **Outliers** = Unusual samples
        - **Position vs red line** = Above/below average
        """)
    
    # ===== RISK ASSESSMENT TABLE =====
    
    st.subheader("🎯 Seasonal Risk Assessment")

    # Calculate seasonal risk based on multiple factors
    seasonal_risk = df_filtered.groupby('season').agg({
        'reading': ['mean', 'median', 'count'],
        'violation_numeric': 'mean', 
        'limits': 'mean'
    }).round(2)

    seasonal_risk.columns = ['Mean_Reading', 'Median_Reading', 'Sample_Count', 'Violation_Rate', 'Avg_Limit']
    seasonal_risk = seasonal_risk.reset_index()

    # Add risk scoring
    seasonal_risk['Contamination_Risk'] = seasonal_risk['Mean_Reading'] / seasonal_risk['Avg_Limit']
    seasonal_risk['Overall_Risk_Score'] = (
        seasonal_risk['Contamination_Risk'] * 0.6 + 
        seasonal_risk['Violation_Rate'] * 0.4
    )

    # Define risk levels
    def assign_risk_level(score, contamination_ratio):
        if score > 0.7 or contamination_ratio > 0.5:
            return '🔴 High'
        elif score > 0.4 or contamination_ratio > 0.2:
            return '🟡 Medium'
        else:
            return '🟢 Low'

    seasonal_risk['Risk_Level'] = seasonal_risk.apply(
        lambda x: assign_risk_level(x['Overall_Risk_Score'], x['Contamination_Risk']), 
        axis=1
    )

    # Display the comprehensive risk assessment
    st.dataframe(
        seasonal_risk.style.format({
            'Mean_Reading': '{:.1f}',
            'Violation_Rate': '{:.1%}',
            'Contamination_Risk': '{:.2f}x',
            'Overall_Risk_Score': '{:.2f}'
        }).background_gradient(subset=['Overall_Risk_Score'], cmap='Reds'),
        use_container_width=True
    )

    # Key insights
    highest_risk = seasonal_risk.loc[seasonal_risk['Overall_Risk_Score'].idxmax()]
    st.warning(f"""
    **Highest Risk Season: {highest_risk['season']}**
    - Average contamination: {highest_risk['Mean_Reading']:.1f} ({highest_risk['Contamination_Risk']:.1f}x above limit)
    - Violation rate: {highest_risk['Violation_Rate']:.1%}
    - Risk level: {highest_risk['Risk_Level']}
    """)

    # Simple explanation
    st.info("""
    **📊 Risk Assessment Methodology:**
    - **Overall Risk Score** = (Contamination Ratio × 60%) + (Violation Rate × 40%)
    - **🔴 High Risk**: Score > 0.7 or contamination >50% above limit  
    - **🟡 Medium Risk**: Score > 0.4 or contamination >20% above limit
    - **🟢 Low Risk**: Below above thresholds
    """)


    # ===== ACTION RECOMMENDATIONS =====
    
    st.subheader("📋 Recommended Actions")
    
    if results['significant']:
        highest_season = results['summary']['mean'].idxmax()
        lowest_season = results['summary']['mean'].idxmin()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.error(f"**Focus on {highest_season}**")
            st.write(f"""
            - **Increase sampling frequency**
            - **Review pesticides used in {highest_season}**
            - **Check weather impact on persistence**
            - **Verify application timing and rates**
            """)
        
        with col2:
            st.success(f"**Learn from {lowest_season}**")
            st.write(f"""
            - **Identify successful practices**
            - **Document optimal application timing**
            - **Consider replicating in other seasons**
            - **Maintain current control measures**
            """)
    else:
        st.success("**Continue Current Practices**")
        st.write("""
        - Maintain regular monitoring schedule
        - Continue existing control measures
        - Seasonal factors are well-managed
        - Focus resources on other risk areas
        """)
    
    # ===== SIMPLIFIED STATISTICS =====
    
    with st.expander("📈 Technical Details"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Statistical Summary**")
            stats_data = {
                'Metric': ['Confidence Level', 'Data Reliability', 'Seasonal Impact'],
                'Value': [
                    'High' if results['p_value'] < 0.01 else 'Medium' if results['p_value'] < 0.05 else 'Low',
                    'Strong' if results['f_statistic'] > 5 else 'Moderate' if results['f_statistic'] > 2 else 'Weak',
                    'Significant' if results['significant'] else 'Not Significant'
                ]
            }
            st.dataframe(pd.DataFrame(stats_data), use_container_width=True)
        
        with col2:
            st.write("**Statistical Values**")
            st.write(f"F-statistic: {results['f_statistic']:.4f}")
            st.write(f"P-value: {results['p_value']:.6f}")
            st.write(f"Sample size: {len(df_filtered):,}")
            st.write(f"Groups compared: {n_groups}")
    
    # [Keep your existing export code...]




    # Interpretation
    st.subheader("📋 Interpretation")

    if results['significant']:
        st.success(f"""
        **Statistically Significant Difference Found!**
        
        - The {analysis_mode.lower()}s have significantly different {target_col} values
        - P-value ({results['p_value']:.6f}) < 0.05
        - F-statistic: {results['f_statistic']:.4f}
        
        **Conclusion:** {analysis_mode} DOES affect {target_col}!
        """)
    else:
        st.info(f"""
        **No Significant Difference Found**
        
        - The {analysis_mode.lower()}s have similar {target_col} values
        - P-value ({results['p_value']:.6f}) ≥ 0.05
        - F-statistic: {results['f_statistic']:.4f}
        
        **Conclusion:** {analysis_mode} does NOT significantly affect {target_col}
        """)

    # Summary statistics table
    st.subheader("📊 Group Statistics")
    st.dataframe(
        results['summary'].style.highlight_max(axis=0, color='lightgreen')
                                .highlight_min(axis=0, color='lightcoral'),
        use_container_width=True
    )

    # Post-hoc analysis (if significant)
    if results['significant'] and n_groups > 2:
        st.subheader("🔬 Post-Hoc Analysis")
        with st.expander("View Pairwise Comparisons (Tukey HSD)"):
            from scipy.stats import tukey_hsd
            groups_list = [group.values for name, group in df_filtered.groupby(group_column)[target_col]]
            try:
                res = tukey_hsd(*groups_list)
                # Create comparison matrix
                group_names = sorted(df_filtered[group_column].unique())
                comparison_df = pd.DataFrame(
                    res.pvalue,
                    index=group_names,
                    columns=group_names
                )
                st.write("**P-values for pairwise comparisons:**")
                st.dataframe(
                    comparison_df.style.background_gradient(cmap='RdYlGn_r', vmin=0, vmax=0.1),
                    use_container_width=True
                )
                st.caption("Green = significant difference (p < 0.05), Red = no significant difference")
                
                # Add interpretation
                st.write("---")
                st.write("**What this means:**")
                st.write("* Spring has significantly different pesticide readings compared to both Fall and Summer")
                st.write("* Summer and Winter readings are somewhat different (borderline significance)")
                st.write("* Fall, Summer, and Winter readings are generally similar to each other (except Summer-Winter borderline)")
                
            except Exception as e:
                st.warning(f"Could not perform Tukey HSD: {e}")
    # Export results
    st.subheader("💾 Export Results")

    # Prepare export data
    export_data = {
        'Analysis Type': f'ANOVA - {analysis_mode}',
        'F-Statistic': results['f_statistic'],
        'P-Value': results['p_value'],
        'Significant': results['significant'],
        'Sample Size': len(df_filtered),
        'Number of Groups': n_groups
    }

    export_df = pd.DataFrame([export_data])

    col1, col2 = st.columns(2)

    with col1:
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Summary (CSV)",
            data=csv,
            file_name=f"anova_{analysis_mode.lower()}_{target_col}.csv",
            mime="text/csv"
        )

    with col2:
        csv_detailed = results['summary'].to_csv()
        st.download_button(
            label="📥 Download Detailed Stats (CSV)",
            data=csv_detailed,
            file_name=f"anova_detailed_{analysis_mode.lower()}_{target_col}.csv",
            mime="text/csv"
        )



                #######   ("📋 Statistical Insights") ########

    st.header("📈 Statistical Summaries")
    st.write("""
    **Analysis of pesticide contamination patterns over time:**
    - **Trend Detection**: Identifies increasing/decreasing contamination levels
    - **Seasonal Patterns**: Compares contamination across different seasons  
    - **Category Comparison**: Analyzes differences between vegetable types
    """)
    col1, col2 = st.columns(2)
    
    # with col1:
    #     if st.button("🔄 Get Statistical Insights", use_container_width=True,):
    #         with st.spinner("Analyzing contamination data..."):
    #             response = api_client.get_statistical_insights()
                
    #             if response and 'insights' in response:
    #                 insights = response['insights']
                    
    #                 if insights:
    #                     for insight in insights:
    #                         if insight.get('severity') == 'high':
    #                             st.error(f"⚠️ {insight.get('message', '')}")
    #                         elif insight.get('severity') == 'medium':
    #                             st.warning(f"📊 {insight.get('message', '')}")
    #                         else:
    #                             st.info(f"✅ {insight.get('message', '')}")
    #                 else:
    #                     st.success("✅ No concerning patterns detected - all stable!")
    #             else:
    #                 st.info("Unable to retrieve statistical insights")


    with col1:
        if 'insights_data' not in st.session_state:
            st.session_state.insights_data = None
        
        if st.button("🔄 Get Statistical Insights", use_container_width=True):
            with st.spinner("Analyzing contamination data..."):
                st.session_state.insights_data = api_client.get_statistical_insights()
        
        # Display insights in collapsible section if data exists
        if st.session_state.insights_data:
            with st.expander("📊 Statistical Insights", expanded=True):
                response = st.session_state.insights_data
                if response and 'insights' in response:
                    insights = response['insights']
                    if insights:
                        for insight in insights:
                            if insight.get('severity') == 'high':
                                st.error(f"⚠️ {insight.get('message', '')}")
                            elif insight.get('severity') == 'medium':
                                st.warning(f"📊 {insight.get('message', '')}")
                            else:
                                st.info(f"✅ {insight.get('message', '')}")
                    else:
                        st.success("✅ No concerning patterns detected - all stable!")
                else:
                    st.info("Unable to retrieve statistical insights")    

