import streamlit as st
import pandas as pd
import json
from datetime import datetime
from typing import Dict


def show_timeseries_page(api_client):
    """Time Series Forecasting page with embedded dashboard"""
    
    st.title("🚀 Time Series Forecasting Dashboard")
    
    st.markdown("""
    **Interactive Pesticide Forecasting**
    - 📊 View historical trends and future predictions
    - 📈 Multiple forecasting models (Prophet, ARIMA)
    - 🔮 Confidence intervals and uncertainty estimates
    - 📅 Different time horizons: Daily, Weekly, Monthly, Yearly
    """)
    
    # Dashboard URL
    dashboard_url = f"{api_client.base_url}/api/v1/timeseries/interactive-dashboard"
    
    # Display options
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info(f"📡 **Dashboard URL:** `{dashboard_url}`")
    
    with col2:
        if st.button("🔄 Refresh", key="refresh_timeseries", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # Access Dashboard Section
    st.subheader("🌐 Access Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <a href="{dashboard_url}" target="_blank">
            <button style="
                background: linear-gradient(135deg, #51CF66 0%, #40C057 100%);
                color: white;
                padding: 15px 30px;
                font-size: 18px;
                font-weight: bold;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                width: 100%;
                box-shadow: 0 4px 12px rgba(81, 207, 102, 0.3);
            ">
                🚀 Open Interactive Dashboard
            </button>
        </a>
        """, unsafe_allow_html=True)
    
    with col2:
        st.link_button(
            "📱 Open in New Tab",
            dashboard_url,
            use_container_width=True
        )
    
    st.markdown("---")
    
    # Embedded Dashboard
    st.subheader("📺 Embedded Dashboard")
    
    iframe_height = st.slider(
        "Adjust dashboard height:",
        min_value=400,
        max_value=1200,
        value=800,
        step=50
    )
    
    st.markdown(f"""
    <iframe 
        src="{dashboard_url}" 
        width="100%" 
        height="{iframe_height}"
        style="border: 2px solid #51CF66; border-radius: 10px;"
        sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
    ></iframe>
    """, unsafe_allow_html=True)

def show_predictions_page(api_client):
    """Predictions - Merged predictions and time series forecasting"""
    
    st.title("🔮 Predictions & Forecasting")
    
    # Create tabs for different prediction types
    tab1, tab2 = st.tabs(["🎯 Risk Assessment", "📈 Time Series Forecasting"])
    
    with tab1:
        st.header("Enhanced Risk Assessment")
        show_enhanced_risk_form(api_client)
    
    with tab2:
        st.header("Time Series Forecasting")
        show_timeseries_page(api_client)

def show_enhanced_risk_form(api_client):
    """Enhanced risk assessment form"""
    
    st.markdown("### Comprehensive Risk Analysis")
    st.write("""
    Uses advanced statistical methods:
    - **Monte Carlo Simulation**: Probabilistic exceedance estimation
    - **Bayesian Analysis**: Prior knowledge from pesticide group
    - **Hazard Modeling**: Vegetable-specific exposure multipliers
    - **Confidence Intervals**: Statistical uncertainty quantification
    """)
    
    # Create form
    with st.form("enhanced_risk_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            vegetable = st.text_input("Vegetable", value="parsley", help="Name of the vegetable/fruit being tested")
            # veg_category = st.selectbox("Vegetable Category",
            #     ["leafy_greens", "peppers", "herbs", "root_vegetables", "fruits", "berries", "cruciferous"],
            #     help="Category affects exposure multipliers")
            pesticide_group = st.selectbox("Pesticide Group",
                ["organophosphorus", "pyrethroid", "chitin_synthesis_inhibitor",
                 "neonicotinoid", "phenylpyrazoles", "carbamates", "triazoles"],
                help="Chemical group affects toxicity profile")
        
        with col2:
            reading = st.number_input("Reading (mg/kg)", value=50.0, min_value=0.0, step=0.1, 
                                    help="Measured pesticide concentration")
            limit = st.number_input("Limit (mg/kg)", value=20.0, min_value=0.0, step=0.1,
                                  help="Maximum residue limit (MRL)")
            
            # Real-time compliance check
            exceedance_ratio = reading / limit if limit > 0 else 0
            is_compliant = reading <= limit
            
            # Display compliance status immediately
            if is_compliant:
                st.success(f"✅ Compliant (Exceedance: {exceedance_ratio:.2f}x)")
            else:
                st.error(f"❌ Non-Compliant (Exceedance: {exceedance_ratio:.2f}x)")
        
        # Additional risk parameters
        st.markdown("---")
        st.markdown("#### 🔧 Advanced Parameters")
        
        col3, col4 = st.columns(2)
        
        with col3:
            population_type = st.selectbox(
                "Population Type",
                ["general", "vulnerable", "children", "pregnant_women"],
                help="Target population for risk assessment"
            )
            confidence_level = st.slider(
                "Confidence Level (%)",
                min_value=80,
                max_value=99,
                value=95,
                help="Statistical confidence level for intervals"
            )
        
        with col4:
            simulation_runs = st.selectbox(
                "Monte Carlo Simulations",
                [1000, 5000, 10000, 50000],
                index=1,
                help="Number of simulations for probabilistic analysis"
            )
            include_uncertainty = st.checkbox(
                "Include Measurement Uncertainty",
                value=True,
                help="Account for analytical measurement errors"
            )
        
        # Submit button
        submitted = st.form_submit_button("🎯 Run Comprehensive Risk Assessment", 
                                        type="primary", 
                                        use_container_width=True)
    
    # Handle form submission
    if submitted:
        risk_data = {
            "vegetable": vegetable,
            # "vegetable_category": veg_category,
            "pesticide_group": pesticide_group,
            "reading": reading,
            "limit": limit,
            "is_compliant": is_compliant,
            "exceedance_ratio": exceedance_ratio,
            "population_type": population_type,
            "confidence_level": confidence_level,
            "simulation_runs": simulation_runs,
            "include_uncertainty": include_uncertainty
        }
        
        with st.spinner("🔄 Performing comprehensive risk assessment..."):
            try:
                result = api_client.assess_risk(risk_data)
                
                if result and 'risk_score' in result:
                    st.success("✅ Risk assessment completed!")
                    display_enhanced_risk_result(result)
                elif result and result.get('success'):
                    st.success("✅ Risk assessment completed!")
                    display_enhanced_risk_result(result.get('data', {}))
                elif result:
                    st.error(f"❌ Assessment failed: {result.get('error', 'Unknown error')}")
                    with st.expander("API Response"):
                        st.json(result)
                else:
                    st.error("❌ No response from API. Check if the endpoint is available.")
                    st.info("💡 Make sure the API server is running and the risk assessment endpoint is configured.")
            
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                with st.expander("Error Details"):
                    st.exception(e)

def display_enhanced_risk_result(risk_result: Dict):
    """Display enhanced risk assessment results"""
    
    st.markdown("## 📊 Risk Assessment Results")
    
    # Risk Level Banner
    risk_level = risk_result.get('risk_level', 'UNKNOWN')
    risk_score = risk_result.get('risk_score', 0)
    exceedance_prob = risk_result.get('exceedance_probability', 0) * 100
    
    if risk_level == 'CRITICAL':
        st.error(f"""
        🔴 **CRITICAL RISK** 
        
        **Risk Score:** {risk_score}/5.0 | **Exceedance Probability:** {exceedance_prob:.1f}%
        
        ⚠️ **Immediate action required**: Do not distribute. Investigate contamination source immediately.
        """)
    elif risk_level == 'HIGH':
        st.warning(f"""
        🟠 **HIGH RISK**
        
        **Risk Score:** {risk_score}/5.0 | **Exceedance Probability:** {exceedance_prob:.1f}%
        
        ℹ️ **Recommendation**: Enhanced monitoring required. Consider retesting before distribution.
        """)
    elif risk_level == 'MEDIUM':
        st.info(f"""
        🟡 **MEDIUM RISK**
        
        **Risk Score:** {risk_score}/5.0 | **Exceedance Probability:** {exceedance_prob:.1f}%
        
        📋 **Recommendation**: Standard monitoring. Review sourcing practices.
        """)
    else:
        st.success(f"""
        🟢 **LOW RISK**
        
        **Risk Score:** {risk_score}/5.0 | **Exceedance Probability:** {exceedance_prob:.1f}%
        
        ✅ **Status**: Acceptable for distribution with routine monitoring.
        """)
    
    # Key Metrics
    st.markdown("### 📈 Key Risk Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        bayesian_risk = risk_result.get('bayesian_risk', 0)
        bayesian_confidence = risk_result.get('bayesian_confidence', (0, 0))
        st.metric(
            "Bayesian Risk Score",
            f"{bayesian_risk:.2f}",
            delta=f"×{risk_result.get('vegetable_multiplier', 1.0)} exposure"
        )
        st.write(f"**95% Credible Interval:** [{bayesian_confidence[0]:.4f}, {bayesian_confidence[1]:.4f}]")

    with col2:
        critical_threshold = risk_result.get('critical_threshold', 0)
        st.metric("Critical Threshold", f"{critical_threshold:.1f}")
    
    with col3:
        monte_carlo_est = risk_result.get('exceedance_probability', 0)
        st.metric("Monte Carlo Estimate", f"{monte_carlo_est:.3f}")
    
    with col4:
        confidence = risk_result.get('confidence_interval', 95)
        st.metric("Confidence Level", f"{confidence}%")
    
    # Confidence Interval
    ci = risk_result.get('confidence_interval', (0, 0))
    st.write(f"**{confidence}% Confidence Interval:** [{ci[0]:.4f}, {ci[1]:.4f}]")
    
    # Detailed Breakdown
    with st.expander("🔍 Detailed Risk Components"):
        components = risk_result.get('components', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📊 Risk Score Components")
            st.write(f"- **Base Risk (Exceedance):** {components.get('base_risk', 0):.3f}")
            st.write(f"- **Probabilistic Risk (Monte Carlo):** {components.get('probabilistic_risk', 0):.3f}")
            st.write(f"- **Bayesian Component:** {components.get('bayesian_component', 0):.3f}")
            st.write(f"- **Uncertainty Adjustment:** {components.get('uncertainty_adjustment', 0):.3f}")
        
        with col2:
            st.markdown("#### ⚖️ Risk Modifiers")
            st.write(f"- **Vegetable Hazard Multiplier:** {risk_result.get('vegetable_multiplier', 1.0)}×")
            st.write(f"- **Pesticide Group Factor:** {risk_result.get('pesticide_group_factor', 1.0)}×")
            st.write(f"- **Population Sensitivity:** {risk_result.get('population_sensitivity', 1.0)}×")
            st.write(f"- **Analytical Method:** {risk_result.get('method', 'LC-MS/MS')}")
    
    # Recommendations
    with st.expander("💡 Actionable Recommendations"):
        recommendations = risk_result.get('recommendations', [])
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                st.write(f"{i}. {rec}")
        else:
            st.write("1. **Immediate Testing**: Conduct confirmatory analysis")
            st.write("2. **Source Investigation**: Review supply chain and growing practices")
            st.write("3. **Enhanced Monitoring**: Increase sampling frequency")
            st.write("4. **Documentation**: Maintain detailed records for regulatory compliance")
    
    # Export Options
    st.markdown("---")
    st.markdown("### 📤 Export Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # JSON export
        json_data = json.dumps(risk_result, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Download JSON Report",
            data=json_data,
            file_name=f"risk_assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        # CSV export for key metrics
        key_metrics = {
            'Risk_Level': risk_level,
            'Risk_Score': risk_score,
            'Exceedance_Probability': exceedance_prob,
            'Bayesian_Risk': bayesian_risk,
            'Critical_Threshold': critical_threshold
        }
        csv_data = pd.DataFrame([key_metrics]).to_csv(index=False)
        st.download_button(
            label="📥 Download CSV Summary",
            data=csv_data,
            file_name=f"risk_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )


