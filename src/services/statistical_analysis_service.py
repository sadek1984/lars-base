import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import f_oneway
import pymannkendall as mk

# Load your data
df = pd.read_excel('./data/processed_data_output.xlsx')
df['document_date'] = pd.to_datetime(df['document_date'])

# ====================
# Mann-Kendall Trend Test (Time Series)
# ====================
def mann_kendall_trend(df, pesticide_group=None):
    """Detect trends in readings over time"""

    if pesticide_group:
        data = df[df['pesticide_group'] == pesticide_group].copy()
    else:
        data = df.copy()
    
    # Aggregate by month
    monthly = data.groupby([data['document_date'].dt.to_period('M')])['reading'].mean()
    
    # ✅ Check if we have enough data
    if len(monthly) < 3:
        return {
            'trend': 'insufficient_data',
            'p_value': None,
            'tau': None,
            'significant': False,
            'message': f'Only {len(monthly)} month(s) of data - need at least 3',
            'data_points': len(monthly)
        }
    
    # Run Mann-Kendall test
    result = mk.original_test(monthly.values)
    
    return {
        'trend': result.trend,  # 'increasing', 'decreasing', or 'no trend'
        'p_value': result.p,
        'tau': result.Tau,
        'significant': result.p < 0.05,
        'data_points': len(monthly),
        'message': f'Analyzed {len(monthly)} months of data'
    }

# Test for pyrethroids
pyrethroid_trend = mann_kendall_trend(df, pesticide_group='pyrethroid')
print(f"Pyrethroid Trend: {pyrethroid_trend}")

# ====================
# ANOVA - Seasonal Comparison
# ====================
def seasonal_anova(df, pesticide_group=None):
    """Compare readings across seasons"""
    
    if pesticide_group:
        data = df[df['pesticide_group'] == pesticide_group].copy()
    else:
        data = df.copy()
    
    # Group by season
    seasons = [data[data['season'] == s]['reading'].dropna() for s in data['season'].unique()]
    
    # Run ANOVA
    f_stat, p_value = f_oneway(*seasons)
    
    # Get means per season
    season_means = data.groupby('season')['reading'].mean().to_dict()
    
    return {
        'f_statistic': f_stat,
        'p_value': p_value,
        'significant': p_value < 0.05,
        'season_means': season_means
    }

# Test seasonal differences
seasonal_results = seasonal_anova(df)
print(f"\nSeasonal ANOVA: {seasonal_results}")

# ====================
# ANOVA - Vegetable Category Comparison
# ====================
def vegetable_category_anova(df):
    """Compare readings across vegetable categories"""
    
    categories = [df[df['vegetable_category'] == cat]['reading'].dropna() 
                  for cat in df['vegetable_category'].unique()]
    
    f_stat, p_value = f_oneway(*categories)
    
    category_means = df.groupby('vegetable_category')['reading'].mean().to_dict()
    
    return {
        'f_statistic': f_stat,
        'p_value': p_value,
        'significant': p_value < 0.01,
        'category_means': category_means
    }

veg_results = vegetable_category_anova(df)
print(f"\nVegetable Category ANOVA: {veg_results}")

# ====================
# Generate Insights for App
# ====================

def generate_statistical_insights(df):
    """Generate statistical insights for pesticide readings"""

    insights = []
    
    # Test all pesticide groups for trends
    for group in df['pesticide_group'].unique():
        trend = mann_kendall_trend(df, pesticide_group=group)
        
        if trend and trend.get('trend') == 'insufficient_data':
            # ⚠️ Not enough data
            insights.append({
                'type': 'trend',
                'pesticide_group': group,
                'message': f"ℹ️ {group}: {trend['message']}",
                'severity': 'low'
            })
        elif trend and trend['significant']:
            # ✅ Significant trend found
            direction = "increasing" if trend['trend'] == 'increasing' else "decreasing"
            insights.append({
                'type': 'trend',
                'pesticide_group': group,
                'message': f"⚠️ Significant {direction} trend in {group} (p={trend['p_value']:.3f}, {trend['data_points']} months)",
                'severity': 'high' if direction == 'increasing' else 'medium'
            })
        elif trend:
            # ✅ Test ran, but no significant trend (STABLE - good!)
            insights.append({
                'type': 'trend',
                'pesticide_group': group,
                'message': f"✅ {group}: Stable over time (no significant trend, {trend['data_points']} months analyzed)",
                'severity': 'low'
            })
    
    # Seasonal analysis
    seasonal = seasonal_anova(df)
    if seasonal and seasonal['significant']:
        highest_season = max(seasonal['season_means'], key=seasonal['season_means'].get)
        insights.append({
            'type': 'seasonal',
            'message': f"📊 Significant seasonal variation (p={seasonal['p_value']:.3f}). Highest in season {highest_season}",
            'severity': 'medium',
            'season_data': seasonal['season_means']
        })
    
    return insights


# === Example execution ===
insights = generate_statistical_insights(df)
for insight in insights:
    print(f"\n{insight['message']}")



