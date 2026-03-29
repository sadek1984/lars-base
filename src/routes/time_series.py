
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import os
import logging
import pandas as pd
import traceback
import numpy as np
from typing import Optional, Literal
import base64
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

timeseries_router = APIRouter(
    prefix="/api/v1/timeseries",
    tags=["api_v1", "timeseries"],
)

CACHED_FORECASTERS = {}
SEQUENCE_LENGTH = 10

POSSIBLE_FILE_PATHS = [
    "/app/data/processed_data_output.xlsx",
    "/Users/a12/mini-rag/src/data/processed_data_output.xlsx", 
    "./data/processed_data_output.xlsx",
    "./src/data/processed_data_output.xlsx",
    "/data/processed_data_output.xlsx",
    "processed_data_output.xlsx",
]

def find_data_file():
    for path in POSSIBLE_FILE_PATHS:
        if os.path.exists(path):
            return path
    return None

# ENHANCED REQUEST MODELS
class PredictionRequest(BaseModel):
    pesticide_name: str
    n_steps: int = 30
    frequency: Literal["daily", "weekly", "monthly", "yearly"] = "daily"
    include_plot: bool = False

class ForecastPlotRequest(BaseModel):
    pesticide_name: str
    forecast_type: Literal["short", "medium", "long"] = "medium"  # short=30 days, medium=1 year, long=3 years
    frequency: Literal["daily", "weekly", "monthly"] = "daily"

def smart_date_conversion(df):
    """Smart date conversion that handles different date formats"""
    print(f"📅 Processing dates...")
    
    if 'document_date' in df.columns:
        if df['document_date'].dtype == 'datetime64[ns]':
            print(f"   ✅ Already datetime format")
            df['date'] = df['document_date']
        elif pd.api.types.is_numeric_dtype(df['document_date']):
            print(f"   🔄 Converting from Excel serial numbers")
            df['date'] = pd.to_datetime(df['document_date'], origin='1899-12-30', unit='D', errors='coerce')
        else:
            print(f"   🔄 Converting from string format")
            df['date'] = pd.to_datetime(df['document_date'], errors='coerce')
    elif 'date' in df.columns:
        print(f"   Using existing 'date' column")
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
    else:
        raise ValueError("No date column found")
    
    valid_dates = df['date'].notna().sum()
    print(f"   ✅ Valid dates: {valid_dates}/{len(df)}")
    
    if valid_dates == 0:
        raise ValueError("No valid dates after conversion")
    
    return df

class EnhancedProphetForecaster:
    """Enhanced Prophet forecaster with multiple time frequencies"""
    
    def __init__(self):
        self.model = None
        self.all_readings = None
        self.logger = logging.getLogger(__name__)
        
    def prepare_data_for_pesticide(self, file_path, pesticide_name):
        """Prepare data for Prophet model"""
        df = pd.read_excel(file_path)
        df = smart_date_conversion(df)
        df = df.dropna(subset=["date", "reading"])
        df = df[df['reading'] > 0]
        
        if 'pesticide_standardized' in df.columns:
            df['pesticide'] = df['pesticide_standardized'].fillna(df.get('pesticide', ''))
        
        pesticide_data = df[df['pesticide'] == pesticide_name].copy()
        if pesticide_data.empty:
            available = df['pesticide'].unique()[:5]
            raise ValueError(f"Pesticide '{pesticide_name}' not found. Available: {available}")
        
        # Prophet format
        self.all_readings = pesticide_data[['date', 'reading']].copy()
        self.all_readings.rename(columns={'date': 'ds', 'reading': 'y'}, inplace=True)
        self.all_readings = self.all_readings.sort_values('ds').reset_index(drop=True)
        
        if len(self.all_readings) < 5:
            raise ValueError(f"Not enough data for {pesticide_name}")
    
    def train_model(self):
        """Train Prophet model with enhanced seasonality"""
        if self.all_readings is None or len(self.all_readings) == 0:
            raise RuntimeError("Data must be prepared before training.")
            
        try:
            from prophet import Prophet
            
            # Enhanced Prophet configuration
            self.model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=True,
                seasonality_mode='multiplicative',
                changepoint_prior_scale=0.05,  # More conservative trend changes
                seasonality_prior_scale=10.0,  # Stronger seasonality
                holidays_prior_scale=10.0,
                interval_width=0.95
            )
            
            # Add custom seasonalities
            self.model.add_seasonality(name='monthly', period=30.5, fourier_order=5)
            self.model.add_seasonality(name='quarterly', period=91.25, fourier_order=8)
            
            # Suppress Prophet output
            import logging
            logging.getLogger('prophet').setLevel(logging.WARNING)
            
            self.model.fit(self.all_readings)
            self.logger.info("Enhanced Prophet model trained successfully.")
            
        except ImportError:
            raise RuntimeError("Prophet is not installed. Install with: pip install prophet")
        except Exception as e:
            self.logger.error(f"Error training Prophet model: {str(e)}")
            raise
    
    def predict_future(self, n_steps=30, frequency="daily"):
        """Enhanced prediction with different frequencies"""
        if self.model is None:
            raise RuntimeError("Model must be trained first.")
        
        try:
            # Calculate the appropriate frequency for Prophet
            freq_map = {
                "daily": "D",
                "weekly": "W", 
                "monthly": "M",
                "yearly": "Y"
            }
            
            freq_code = freq_map.get(frequency, "D")
            
            # Create future dataframe with specified frequency
            if frequency == "daily":
                future = self.model.make_future_dataframe(periods=n_steps, freq=freq_code)
            elif frequency == "weekly":
                future = self.model.make_future_dataframe(periods=n_steps, freq=freq_code)
            elif frequency == "monthly":
                future = self.model.make_future_dataframe(periods=n_steps, freq=freq_code)
            elif frequency == "yearly":
                future = self.model.make_future_dataframe(periods=n_steps, freq=freq_code)
            
            # Make predictions
            forecast = self.model.predict(future)
            
            # Extract future predictions
            future_predictions_df = forecast.iloc[-n_steps:]
            
            predictions = future_predictions_df['yhat'].values.tolist()
            confidence_lower = future_predictions_df['yhat_lower'].values.tolist()
            confidence_upper = future_predictions_df['yhat_upper'].values.tolist()
            dates = future_predictions_df['ds'].dt.strftime('%Y-%m-%d').tolist()
            
            return {
                "predictions": [float(max(1.0, pred)) for pred in predictions],
                "confidence_lower": [float(max(1.0, pred)) for pred in confidence_lower],
                "confidence_upper": [float(max(1.0, pred)) for pred in confidence_upper],
                "dates": dates,
                "frequency": frequency
            }
            
        except Exception as e:
            self.logger.error(f"Error predicting future values: {str(e)}")
            raise
    
    def create_forecast_plot(self, n_steps=30, frequency="daily"):
        """Create forecast plot with historical and predicted data"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Use non-interactive backend
            import matplotlib.pyplot as plt
            from datetime import datetime, timedelta
            
            # Get predictions
            forecast_data = self.predict_future(n_steps, frequency)
            
            # Create figure
            plt.figure(figsize=(14, 8))
            
            # Plot historical data
            historical_dates = pd.to_datetime(self.all_readings['ds'])
            plt.plot(historical_dates, self.all_readings['y'], 
                    'b-', label='Historical Data', linewidth=2, alpha=0.8)
            
            # Plot predictions
            future_dates = pd.to_datetime(forecast_data['dates'])
            plt.plot(future_dates, forecast_data['predictions'], 
                    'r-', label=f'{frequency.capitalize()} Forecast', linewidth=2.5)
            
            # Plot confidence intervals
            plt.fill_between(future_dates, 
                           forecast_data['confidence_lower'], 
                           forecast_data['confidence_upper'],
                           alpha=0.3, color='red', label='Confidence Interval')
            
            # Formatting
            plt.title(f'Pesticide Forecast - {frequency.capitalize()} Predictions ({n_steps} steps)', 
                     fontsize=16, fontweight='bold')
            plt.xlabel('Date', fontsize=12)
            plt.ylabel('Reading Value', fontsize=12)
            plt.legend(fontsize=11)
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            buffer.seek(0)
            plot_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return plot_base64
            
        except Exception as e:
            self.logger.error(f"Error creating plot: {str(e)}")
            raise

# Keep the existing SimplePesticideForecaster but enhance it
class EnhancedSimpleForecaster:
    """Enhanced simple forecaster with frequency support"""
    
    def __init__(self):
        self.all_readings = None
        self.trend = None
        self.seasonal_pattern = None
        self.mean_value = None
        self.dates = None
        
    def prepare_data_for_pesticide(self, file_path, pesticide_name):
        """Prepare data"""
        df = pd.read_excel(file_path)
        df = smart_date_conversion(df)
        df = df.dropna(subset=["date", "reading"])
        df = df[df['reading'] > 0]
        
        if 'pesticide_standardized' in df.columns:
            df['pesticide'] = df['pesticide_standardized'].fillna(df.get('pesticide', ''))
        
        pesticide_data = df[df['pesticide'] == pesticide_name].copy()
        if pesticide_data.empty:
            available = df['pesticide'].unique()[:5]
            raise ValueError(f"Pesticide '{pesticide_name}' not found. Available: {available}")
        
        pesticide_data = pesticide_data.sort_values('date')
        
        if len(pesticide_data) < 5:
            raise ValueError(f"Not enough data for {pesticide_name}")
        
        self.all_readings = pesticide_data['reading'].values
        self.dates = pesticide_data['date'].values
    
    def train_model(self):
        """Enhanced training"""
        if self.all_readings is None:
            raise RuntimeError("Data must be prepared first")
        
        # Calculate trend
        if len(self.all_readings) > 1:
            self.trend = np.mean(np.diff(self.all_readings))
        else:
            self.trend = 0
        
        self.mean_value = np.mean(self.all_readings)
        
        # Enhanced seasonal patterns
        if len(self.all_readings) >= 12:
            self.seasonal_pattern = self.all_readings[-12:]
        else:
            self.seasonal_pattern = self.all_readings
    
    def predict_future(self, n_steps=30, frequency="daily"):
        """Enhanced prediction with frequency support"""
        if self.all_readings is None:
            raise RuntimeError("Model must be trained first")
        
        # Frequency multipliers
        freq_multipliers = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
            "yearly": 365
        }
        
        step_multiplier = freq_multipliers.get(frequency, 1)
        
        predictions = []
        dates = []
        last_date = pd.to_datetime(self.dates[-1])
        
        for i in range(n_steps):
            # Calculate next date based on frequency
            if frequency == "daily":
                next_date = last_date + pd.Timedelta(days=i+1)
            elif frequency == "weekly":
                next_date = last_date + pd.Timedelta(weeks=i+1)
            elif frequency == "monthly":
                next_date = last_date + pd.DateOffset(months=i+1)
            elif frequency == "yearly":
                next_date = last_date + pd.DateOffset(years=i+1)
            
            # Simple prediction logic
            last_value = self.all_readings[-1]
            trend_component = last_value + (self.trend * (i + 1) * step_multiplier)
            seasonal_idx = i % len(self.seasonal_pattern)
            seasonal_factor = self.seasonal_pattern[seasonal_idx] / np.mean(self.seasonal_pattern)
            
            prediction = trend_component * seasonal_factor * 0.9
            predictions.append(float(max(1.0, prediction)))
            dates.append(next_date.strftime('%Y-%m-%d'))
        
        return {
            "predictions": predictions,
            "dates": dates,
            "frequency": frequency
        }

def load_and_train_models():
    """Enhanced training with new forecasters"""
    global CACHED_FORECASTERS
    
    print("\n" + "="*80)
    print("🚀 STARTING ENHANCED MODEL TRAINING")
    print("="*80)
    
    file_path = find_data_file()
    if not file_path:
        print("❌ No data file found")
        return
    
    print(f"✅ Using: {file_path}")
    
    try:
        df = pd.read_excel(file_path)
        print(f"✅ Loaded {len(df)} rows")
        
        df = smart_date_conversion(df)
        df_clean = df.dropna(subset=["date", "reading"])
        df_clean = df_clean[df_clean['reading'] > 0]
        print(f"✅ After cleaning: {len(df_clean)} rows")
        
        if 'pesticide_standardized' in df.columns:
            df_clean['pesticide'] = df_clean['pesticide_standardized'].fillna(df_clean.get('pesticide', ''))
        elif 'pesticide' not in df.columns:
            print("❌ No pesticide column found")
            return
        
        pesticide_counts = df_clean['pesticide'].value_counts()
        target_pesticides = [pest for pest, count in pesticide_counts.items() if count >= 15][:5]
        
        print(f"🎯 Training: {target_pesticides}")
        
        successful_count = 0
        for pesticide in target_pesticides:
            count = pesticide_counts[pesticide]
            print(f"\n🔄 Training {pesticide} ({count} readings)...")
            
            # Try Enhanced Prophet first
            try:
                print(f"   🔮 Trying Enhanced Prophet...")
                forecaster = EnhancedProphetForecaster()
                forecaster.prepare_data_for_pesticide(file_path, pesticide)
                forecaster.train_model()
                
                CACHED_FORECASTERS[pesticide] = forecaster
                successful_count += 1
                print(f"   ✅ Enhanced Prophet SUCCESS!")
                
            except Exception as prophet_error:
                print(f"   ⚠️  Prophet failed: {str(prophet_error)}")
                print(f"   🔄 Falling back to Enhanced Simple...")
                
                try:
                    forecaster = EnhancedSimpleForecaster()
                    forecaster.prepare_data_for_pesticide(file_path, pesticide)
                    forecaster.train_model()
                    
                    CACHED_FORECASTERS[pesticide] = forecaster
                    successful_count += 1
                    print(f"   ✅ Enhanced Simple SUCCESS!")
                    
                except Exception as simple_error:
                    print(f"   ❌ Both forecasters failed: {str(simple_error)}")
        
        print(f"\n🎉 TRAINING COMPLETE!")
        print(f"   Successfully trained: {successful_count}/{len(target_pesticides)}")
        print(f"   Available models: {list(CACHED_FORECASTERS.keys())}")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        traceback.print_exc()

# ENHANCED ENDPOINTS

@timeseries_router.post("/predict")
def get_future_predictions(request: PredictionRequest):
    """Enhanced prediction with frequency and plotting support"""
    pesticide_name = request.pesticide_name
    n_steps = request.n_steps
    frequency = request.frequency
    include_plot = request.include_plot
    
    if pesticide_name not in CACHED_FORECASTERS:
        available_models = list(CACHED_FORECASTERS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Pesticide '{pesticide_name}' not available. Available: {available_models}"
        )
    
    try:
        forecaster = CACHED_FORECASTERS[pesticide_name]
        
        # Get predictions
        if hasattr(forecaster, 'predict_future'):
            forecast_result = forecaster.predict_future(n_steps, frequency)
        else:
            # Fallback for old forecasters
            predictions = forecaster.predict_future(n_steps)
            forecast_result = {"predictions": predictions, "frequency": frequency}
        
        # Model type
        model_type = "Enhanced Prophet" if isinstance(forecaster, EnhancedProphetForecaster) else "Enhanced Simple"
        
        result = {
            "pesticide": pesticide_name,
            "n_steps": n_steps,
            "frequency": frequency,
            "model_type": model_type,
            "forecast": forecast_result,
            "status": "success"
        }
        
        # Add plot if requested
        if include_plot and isinstance(forecaster, EnhancedProphetForecaster):
            try:
                plot_base64 = forecaster.create_forecast_plot(n_steps, frequency)
                result["plot"] = f"data:image/png;base64,{plot_base64}"
            except Exception as e:
                result["plot_error"] = str(e)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

@timeseries_router.post("/forecast-plot")
def create_forecast_plot(request: ForecastPlotRequest):
    """Create detailed forecast plots"""
    pesticide_name = request.pesticide_name
    forecast_type = request.forecast_type
    frequency = request.frequency
    
    if pesticide_name not in CACHED_FORECASTERS:
        available_models = list(CACHED_FORECASTERS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Pesticide '{pesticide_name}' not available. Available: {available_models}"
        )
    
    forecaster = CACHED_FORECASTERS[pesticide_name]
    
    if not isinstance(forecaster, EnhancedProphetForecaster):
        raise HTTPException(
            status_code=400,
            detail="Plotting is only available for Prophet models"
        )
    
    # Determine n_steps based on forecast type
    steps_map = {
        "short": {"daily": 30, "weekly": 12, "monthly": 6},
        "medium": {"daily": 365, "weekly": 52, "monthly": 12}, 
        "long": {"daily": 1095, "weekly": 156, "monthly": 36}  # 3 years
    }
    
    n_steps = steps_map[forecast_type][frequency]
    
    try:
        plot_base64 = forecaster.create_forecast_plot(n_steps, frequency)
        forecast_data = forecaster.predict_future(n_steps, frequency)
        
        return {
            "pesticide": pesticide_name,
            "forecast_type": forecast_type,
            "frequency": frequency,
            "n_steps": n_steps,
            "plot": f"data:image/png;base64,{plot_base64}",
            "forecast_summary": {
                "mean_prediction": float(np.mean(forecast_data["predictions"])),
                "max_prediction": float(np.max(forecast_data["predictions"])),
                "min_prediction": float(np.min(forecast_data["predictions"]))
            },
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plot creation error: {str(e)}")

# QUICK FORECAST ENDPOINTS
@timeseries_router.get("/quick-forecast/{pesticide_name}")
def quick_forecast(
    pesticide_name: str,
    frequency: Literal["daily", "weekly", "monthly", "yearly"] = Query(default="daily"),
    steps: int = Query(default=30, ge=1, le=365)
):
    """Quick forecast endpoint with query parameters"""
    if pesticide_name not in CACHED_FORECASTERS:
        available_models = list(CACHED_FORECASTERS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Available models: {available_models}"
        )
    
    try:
        forecaster = CACHED_FORECASTERS[pesticide_name]
        forecast_result = forecaster.predict_future(steps, frequency)
        
        return {
            "pesticide": pesticide_name,
            "frequency": frequency,
            "steps": steps,
            "forecast": forecast_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Keep existing endpoints (debug, retrain, models) unchanged
@timeseries_router.get("/debug")
def debug_training():
    """Debug endpoint (unchanged)"""
    try:
        file_path = find_data_file()
        if not file_path:
            return {"error": "No data file found"}
        
        df = pd.read_excel(file_path)
        
        info = {
            "file_path": file_path,
            "total_rows": len(df),
            "columns": df.columns.tolist(),
            "cached_models": list(CACHED_FORECASTERS.keys()),
        }
        
        if 'document_date' in df.columns:
            info["document_date_dtype"] = str(df['document_date'].dtype)
        
        if 'pesticide_standardized' in df.columns:
            pesticides = df['pesticide_standardized'].value_counts().head(5).to_dict()
        elif 'pesticide' in df.columns:
            pesticides = df['pesticide'].value_counts().head(5).to_dict()
        else:
            pesticides = {}
        
        info["top_pesticides"] = pesticides
        return info
        
    except Exception as e:
        return {"error": str(e)}

@timeseries_router.post("/retrain")
def retrain_models():
    """Force retrain (unchanged)"""
    global CACHED_FORECASTERS
    CACHED_FORECASTERS = {}
    load_and_train_models()
    return {
        "message": "Retraining completed",
        "available_models": list(CACHED_FORECASTERS.keys()),
        "total_models": len(CACHED_FORECASTERS)
    }

@timeseries_router.get("/models")
def get_available_models():
    """Check available models (unchanged)"""
    file_path = find_data_file()
    return {
        "available_models": list(CACHED_FORECASTERS.keys()),
        "total_models": len(CACHED_FORECASTERS),
        "data_file_found": file_path is not None,
        "data_file_path": file_path
    }



                        ########    Plotting Dashboard    ########

# Add these endpoints to your routes/time_series.py

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse
import base64
import io

# ADD THESE NEW ENDPOINTS TO YOUR EXISTING FILE:

@timeseries_router.get("/plot-viewer/{pesticide_name}", response_class=HTMLResponse)
def view_forecast_plot(
    pesticide_name: str,
    frequency: str = "daily",
    steps: int = 30,
    forecast_type: str = "medium"
):
    """
    Returns an HTML page that displays the forecast plot directly in browser
    """
    
    if pesticide_name not in CACHED_FORECASTERS:
        available_models = list(CACHED_FORECASTERS.keys())
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Error: Pesticide not found</h2>
                <p>Available models: {', '.join(available_models)}</p>
            </body>
        </html>
        """)
    
    forecaster = CACHED_FORECASTERS[pesticide_name]
    
    if not isinstance(forecaster, EnhancedProphetForecaster):
        return HTMLResponse("""
        <html>
            <body>
                <h2>Error: Plotting only available for Prophet models</h2>
                <p>This pesticide was trained with Simple forecaster</p>
            </body>
        </html>
        """)
    
    try:
        # Generate plot
        plot_base64 = forecaster.create_forecast_plot(steps, frequency)
        forecast_data = forecaster.predict_future(steps, frequency)
        
        # Create HTML with embedded plot
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Forecast Plot - {pesticide_name}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    color: #333;
                }}
                .plot-container {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .plot-container img {{
                    max-width: 100%;
                    height: auto;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .stats {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-top: 30px;
                }}
                .stat-card {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    border-left: 4px solid #007bff;
                }}
                .stat-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #007bff;
                }}
                .stat-label {{
                    color: #666;
                    margin-top: 5px;
                }}
                .controls {{
                    text-align: center;
                    margin: 20px 0;
                }}
                .btn {{
                    background: #007bff;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 0 10px;
                    display: inline-block;
                }}
                .btn:hover {{
                    background: #0056b3;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Pesticide Forecast Analysis</h1>
                    <h2>{pesticide_name} - {frequency.capitalize()} Predictions</h2>
                    <p><strong>Forecast Steps:</strong> {steps} | <strong>Type:</strong> {forecast_type}</p>
                </div>
                
                <div class="plot-container">
                    <img src="data:image/png;base64,{plot_base64}" alt="Forecast Plot">
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">{len(forecast_data.get('predictions', []))}</div>
                        <div class="stat-label">Forecast Points</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{forecast_data.get('predictions', [0])[0]:.1f}</div>
                        <div class="stat-label">First Prediction</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{max(forecast_data.get('predictions', [0])):.1f}</div>
                        <div class="stat-label">Maximum Value</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{min(forecast_data.get('predictions', [0])):.1f}</div>
                        <div class="stat-label">Minimum Value</div>
                    </div>
                </div>
                
                <div class="controls">
                    <h3>🔗 Try Different Views:</h3>
                    <a href="/api/v1/timeseries/plot-viewer/{pesticide_name}?frequency=daily&steps=30" class="btn">30 Days</a>
                    <a href="/api/v1/timeseries/plot-viewer/{pesticide_name}?frequency=weekly&steps=52" class="btn">52 Weeks</a>
                    <a href="/api/v1/timeseries/plot-viewer/{pesticide_name}?frequency=monthly&steps=12" class="btn">12 Months</a>
                    <a href="/api/v1/timeseries/plot-viewer/{pesticide_name}?frequency=yearly&steps=3" class="btn">3 Years</a>
                </div>
                
                <div style="margin-top: 30px; padding: 20px; background: #e9ecef; border-radius: 8px;">
                    <h4>📈 Forecast Data Summary:</h4>
                    <p><strong>Date Range:</strong> {forecast_data.get('dates', ['N/A'])[0]} to {forecast_data.get('dates', ['N/A'])[-1]}</p>
                    <p><strong>Model Type:</strong> Enhanced Prophet with seasonality detection</p>
                    <p><strong>Confidence Intervals:</strong> Included (95% prediction interval)</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        return HTMLResponse(f"""
        <html>
            <body>
                <h2>Error generating plot</h2>
                <p>{str(e)}</p>
            </body>
        </html>
        """)

@timeseries_router.get("/download-plot/{pesticide_name}")
def download_forecast_plot(
    pesticide_name: str,
    frequency: str = "daily",
    steps: int = 30
):
    """
    Downloads the plot as a PNG file
    """
    
    if pesticide_name not in CACHED_FORECASTERS:
        raise HTTPException(status_code=404, detail="Pesticide not found")
    
    forecaster = CACHED_FORECASTERS[pesticide_name]
    
    if not isinstance(forecaster, EnhancedProphetForecaster):
        raise HTTPException(status_code=400, detail="Plotting only available for Prophet models")
    
    try:
        # Generate plot
        plot_base64 = forecaster.create_forecast_plot(steps, frequency)
        plot_data = base64.b64decode(plot_base64)
        
        # Create filename
        filename = f"{pesticide_name}_{frequency}_{steps}steps_forecast.png"
        
        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(plot_data),
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating plot: {str(e)}")

@timeseries_router.get("/interactive-dashboard", response_class=HTMLResponse)
def interactive_dashboard():
    """
    Interactive dashboard to view all available models and their plots
    """
    
    available_models = list(CACHED_FORECASTERS.keys())
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pesticide Forecasting Dashboard</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
                color: #333;
            }}
            .models-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 25px;
                margin-bottom: 40px;
            }}
            .model-card {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                border: 2px solid #e9ecef;
                transition: all 0.3s ease;
            }}
            .model-card:hover {{
                border-color: #007bff;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,123,255,0.2);
            }}
            .model-name {{
                font-size: 20px;
                font-weight: bold;
                color: #007bff;
                margin-bottom: 15px;
            }}
            .freq-buttons {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: 15px;
            }}
            .freq-btn {{
                background: #007bff;
                color: white;
                padding: 8px 12px;
                text-decoration: none;
                border-radius: 5px;
                text-align: center;
                font-size: 12px;
                transition: background 0.3s ease;
            }}
            .freq-btn:hover {{
                background: #0056b3;
            }}
            .instructions {{
                background: #e7f3ff;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #007bff;
                margin-bottom: 30px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Pesticide Forecasting Dashboard</h1>
                <p>Interactive visualization for time series predictions</p>
            </div>
            
            <div class="instructions">
                <h3>📋 How to Use:</h3>
                <ul>
                    <li><strong>Click any button below</strong> to view forecast plots in your browser</li>
                    <li><strong>Different frequencies:</strong> Daily (short-term), Weekly (medium-term), Monthly/Yearly (long-term)</li>
                    <li><strong>Interactive plots:</strong> Shows historical data + future predictions + confidence intervals</li>
                </ul>
            </div>
            
            <div class="models-grid">
    """
    
    # Add model cards
    for model in available_models:
        forecaster = CACHED_FORECASTERS[model]
        model_type = "Prophet" if isinstance(forecaster, EnhancedProphetForecaster) else "Simple"
        
        html_content += f"""
                <div class="model-card">
                    <div class="model-name">📊 {model}</div>
                    <p><strong>Model Type:</strong> {model_type}</p>
                    <p><strong>Status:</strong> ✅ Ready for prediction</p>
                    
                    <div class="freq-buttons">
                        <a href="/api/v1/timeseries/plot-viewer/{model}?frequency=daily&steps=30" class="freq-btn">
                            📅 30 Days
                        </a>
                        <a href="/api/v1/timeseries/plot-viewer/{model}?frequency=weekly&steps=52" class="freq-btn">
                            📊 52 Weeks  
                        </a>
                        <a href="/api/v1/timeseries/plot-viewer/{model}?frequency=monthly&steps=12" class="freq-btn">
                            📈 12 Months
                        </a>
                        <a href="/api/v1/timeseries/plot-viewer/{model}?frequency=yearly&steps=3" class="freq-btn">
                            🎯 3 Years
                        </a>
                    </div>
                </div>
        """
    
    html_content += f"""
            </div>
            
            <div style="text-align: center; margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                <h3>🔗 API Endpoints</h3>
                <p><strong>Available Models:</strong> {len(available_models)}</p>
                <p><strong>Base URL:</strong> /api/v1/timeseries/</p>
                <p><strong>Formats:</strong> JSON data + Base64 plots + Interactive HTML</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

# SIMPLE BASE64 TO HTML CONVERTER ENDPOINT
@timeseries_router.post("/view-plot", response_class=HTMLResponse)
def view_base64_plot(request: dict):
    """
    Convert base64 plot data to viewable HTML
    Use this if you already have base64 data from other endpoints
    """
    
    if "plot" not in request:
        return HTMLResponse("<html><body><h2>Error: No plot data provided</h2></body></html>")
    
    plot_data = request["plot"]
    
    # Remove data URL prefix if present
    if plot_data.startswith("data:image/png;base64,"):
        plot_data = plot_data.replace("data:image/png;base64,", "")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Forecast Plot Viewer</title>
        <style>
            body {{
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
                font-family: Arial, sans-serif;
                text-align: center;
            }}
            .plot-container {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                display: inline-block;
            }}
            img {{
                max-width: 100%;
                height: auto;
                border: 1px solid #ddd;
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="plot-container">
            <h1>📊 Forecast Plot</h1>
            <img src="data:image/png;base64,{plot_data}" alt="Forecast Plot">
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)