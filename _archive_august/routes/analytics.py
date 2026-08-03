# In your FastAPI app (e.g., routes/analytics.py)
from fastapi import APIRouter
from typing import List, Dict
import pandas as pd
from services.statistical_analysis_service import generate_statistical_insights, mann_kendall_trend

analytics_router = APIRouter()

@analytics_router.get("/api/v1/analytics/statistical-insights")
async def get_statistical_insights():
    """Get statistical insights from data"""
    
    df = pd.read_excel('/app/data/processed_data_output.xlsx')
    df['document_date'] = pd.to_datetime(df['document_date'])
    
    insights = generate_statistical_insights(df)
    
    return {
        "insights": insights,
        "total_insights": len(insights),
        "high_severity_count": len([i for i in insights if i.get('severity') == 'high'])
    }

@analytics_router.get("/api/v1/analytics/trend/{pesticide_group}")
async def get_pesticide_trend(pesticide_group: str):
    """Get trend for specific pesticide group"""
    
    df = pd.read_csv('cleaned_data.csv')
    df['document_date'] = pd.to_datetime(df['document_date'])
    
    trend = mann_kendall_trend(df, pesticide_group=pesticide_group)
    
    return {
        "pesticide_group": pesticide_group,
        "trend_analysis": trend
    }