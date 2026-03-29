import streamlit as st

def show_dashboard_overview(api_client):
    """Enhanced dashboard overview with key metrics"""
    
    st.title("🏠 Dashboard Overview")
    
    # Enhanced metric cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div style="background: white; padding: 25px; border-radius: 15px; 
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-left: 5px solid #4caf50;">
            <div style="font-size: 40px; margin-bottom: 10px;">📊</div>
            <h3 style="color: #2e7d32;">1,234</h3>
            <p style="color: #666;">Total Samples</p>
            <p style="color: #4caf50; font-weight: 600;">↑ 12% this month</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: white; padding: 25px; border-radius: 15px; 
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-left: 5px solid #ff9800;">
            <div style="font-size: 40px; margin-bottom: 10px;">⚠️</div>
            <h3 style="color: #f57c00;">Medium</h3>
            <p style="color: #666;">Risk Level</p>
            <p style="color: #f57c00; font-weight: 600;">↓ 3% improvement</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: white; padding: 25px; border-radius: 15px; 
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-left: 5px solid #2196f3;">
            <div style="font-size: 40px; margin-bottom: 10px;">✅</div>
            <h3 style="color: #1976d2;">89%</h3>
            <p style="color: #666;">Completed Analysis</p>
            <p style="color: #2196f3; font-weight: 600;">↑ 4% progress</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Quick insights
    st.subheader("📌 Quick Insights")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        **🎯 Priority Actions:**
        - Review high-risk vegetable-pesticide combinations
        - Monitor seasonal contamination patterns
        - Update forecasting models with latest data
        """)
    
    with col2:
        st.success("""
        **✅ Recent Achievements:**
        - 15% reduction in violations this quarter
        - 3 new vegetables added to monitoring program
        - AI assistant accuracy improved to 94%
        """)
