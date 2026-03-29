import streamlit as st
import pandas as pd
import numpy as np
import os
import duckdb
from scipy.stats import f_oneway
from modules.data_access import (
    load_dataframe as load_data_from_path,
    get_duckdb_read as get_duckdb_connection,
    get_duckdb_write as get_duckdb_connection_write,
)

def map_season_names(df):
    """
    Standardize season names in the dataframe.
    """
    season_mapping = {
        0: 'Winter', 1: 'Spring', 2: 'Summer', 3: 'Fall',
        '0': 'Winter', '1': 'Spring', '2': 'Summer', '3': 'Fall',
        'winter': 'Winter', 'spring': 'Spring', 'summer': 'Summer', 'fall': 'Fall', 'autumn': 'Fall'
    }
    
    if 'season' in df.columns:
        # Create a copy to avoid SettingWithCopyWarning if it's a slice
        df = df.copy()
        df['season_name'] = df['season'].map(season_mapping).fillna(df['season'])
        df['season'] = df['season_name']
    return df

def calculate_violations(df):
    """
    Ensure the 'is_violation' column exists and is correctly populated.
    """
    df = df.copy()
    if 'is_violation' not in df.columns:
        if 'is_compliant' in df.columns:
            # Handle cases where is_compliant might be string 'TRUE'/'FALSE' or boolean
            if df['is_compliant'].dtype == object:
                df['is_violation'] = df['is_compliant'].astype(str).str.upper() != 'TRUE'
            else:
                df['is_violation'] = ~df['is_compliant'].astype(bool)
        elif 'reading' in df.columns and 'limits' in df.columns:
            df['is_violation'] = df['reading'] > df['limits']
        else:
            # Try to find any column that might indicate compliance
            comp_cols = [c for c in df.columns if 'compliant' in c.lower() or 'compliance' in c.lower()]
            if comp_cols:
                if df[comp_cols[0]].dtype == object:
                    df['is_violation'] = df[comp_cols[0]].astype(str).str.upper() != 'TRUE'
                else:
                    df['is_violation'] = ~df[comp_cols[0]].astype(bool)
            else:
                df['is_violation'] = False
    
    # Ensure it's boolean or int
    if 'is_violation' in df.columns:
        df['is_violation_numeric'] = df['is_violation'].astype(int)
        
    return df

def perform_anova_analysis(df, group_by, target_col='reading'):
    """
    Perform one-way ANOVA analysis.
    """
    # Filter out NaNs
    df_clean = df.dropna(subset=[group_by, target_col])
    
    # Get groups with at least 2 samples
    groups = df_clean.groupby(group_by)[target_col].apply(list)
    groups = groups[groups.apply(len) >= 2]
    
    if len(groups) < 2:
        return {
            'success': False,
            'error': "Not enough data for ANOVA (need at least 2 groups with 2+ samples each)"
        }
    
    try:
        f_stat, p_value = f_oneway(*groups.values)
        
        summary = df_clean.groupby(group_by)[target_col].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('min', 'min'),
            ('max', 'max')
        ]).round(4)
        
        return {
            'success': True,
            'f_statistic': f_stat,
            'p_value': p_value,
            'groups_data': groups,
            'summary': summary,
            'significant': p_value < 0.05
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
