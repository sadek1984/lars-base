import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import logging

class PesticideTimeSeriesForecaster:
    def __init__(self, sequence_length=10):
        self.sequence_length = sequence_length
        self.model = None
        self.scaler = None
        self.all_readings = None
        self.logger = logging.getLogger(__name__)
        
        # TensorFlow components will be loaded lazily
        self._tf_loaded = False

    def _load_tensorflow(self):
        """Lazy load TensorFlow components only when needed"""
        if self._tf_loaded:
            return
            
        try:
            # Import TensorFlow components only when actually training
            global Sequential, LSTM, Dense, Dropout, EarlyStopping
            
            from keras.models import Sequential
            from keras.layers import LSTM, Dense, Dropout
            from keras.callbacks import EarlyStopping
            
            self._tf_loaded = True
            self.logger.info("TensorFlow components loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load TensorFlow: {e}")
            raise RuntimeError(f"TensorFlow loading failed: {e}")

    def prepare_data_for_pesticide(self, file_path, pesticide_name, split_ratio=0.8):
        """
        Load, clean, and split data for a specific pesticide.
        (No TensorFlow needed for this step)
        """
        try:
            # Read Excel file - handle both date formats
            df = pd.read_excel(file_path)
            
            # Debug: Print available columns
            self.logger.info(f"Available columns: {df.columns.tolist()}")
            
            # Handle date conversion properly
            if 'document_date' in df.columns:
                # Convert Excel serial date to datetime
                df['date'] = pd.to_datetime(df['document_date'], origin='1899-12-30', unit='D', errors='coerce')
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            else:
                raise ValueError("No date column found in data")
            
            # Clean data
            df = df.dropna(subset=["date", "reading"])
            
            # Handle pesticide column name variations
            pesticide_col = None
            if 'pesticide_standardized' in df.columns:
                df['pesticide'] = df['pesticide_standardized'].fillna(df.get('pesticide', ''))
                pesticide_col = 'pesticide'
            elif 'pesticide' in df.columns:
                pesticide_col = 'pesticide'
            else:
                raise ValueError("No pesticide column found in data")
            
            # Filter for specific pesticide
            pesticide_data = df[df[pesticide_col] == pesticide_name].copy()
            
            if pesticide_data.empty:
                available_pesticides = df[pesticide_col].unique()[:10]  # Show first 10
                raise ValueError(f"Pesticide '{pesticide_name}' not found. Available: {available_pesticides}")
            
            # Sort by date and prepare data
            pesticide_data = pesticide_data.sort_values('date')
            
            # Remove outliers and invalid readings
            pesticide_data = pesticide_data[pesticide_data['reading'] > 0]
            
            if len(pesticide_data) < self.sequence_length + 1:
                raise ValueError(f"Not enough data for {pesticide_name}. Found {len(pesticide_data)} readings, need at least {self.sequence_length + 1}")
            
            self.all_readings = pesticide_data['reading'].values.reshape(-1, 1)
            
            # Split data chronologically
            split_size = int(len(self.all_readings) * split_ratio)
            train_data = self.all_readings[:split_size]
            test_data = self.all_readings[split_size:]
            
            self.logger.info(f"Data prepared for {pesticide_name}: {len(train_data)} train, {len(test_data)} test")
            return train_data, test_data
            
        except Exception as e:
            self.logger.error(f"Error preparing data for {pesticide_name}: {str(e)}")
            raise

    def _create_lstm_sequences(self, data):
        """Helper method to create sequences."""
        X, y = [], []
        for i in range(len(data) - self.sequence_length):
            X.append(data[i:(i + self.sequence_length), 0])
            y.append(data[i + self.sequence_length, 0])
        return np.array(X), np.array(y)

    def train_model(self, train_data):
        """
        Build and train the model and scaler.
        TensorFlow is loaded only at this point.
        """
        try:
            # Load TensorFlow components NOW (not at import time)
            self._load_tensorflow()
            
            # Scale the data
            self.scaler = MinMaxScaler(feature_range=(0, 1))
            scaled_train_data = self.scaler.fit_transform(train_data)
            
            # Create sequences
            X_train, y_train = self._create_lstm_sequences(scaled_train_data)
            
            if X_train.shape[0] == 0:
                raise ValueError(f"Not enough training data to create sequences of length {self.sequence_length}.")
            
            # Reshape for LSTM
            X_train = np.reshape(X_train, (X_train.shape[0], X_train.shape[1], 1))
            
            # Build model (TensorFlow components are now available)
            self.model = Sequential([
                LSTM(50, return_sequences=True, input_shape=(self.sequence_length, 1)),
                Dropout(0.2),
                LSTM(50, return_sequences=False),
                Dropout(0.2),
                Dense(25),
                Dense(1)
            ])
            
            self.model.compile(optimizer='adam', loss='mean_squared_error', learning_rate=0.001)
            
            # Train with early stopping
            early_stop = EarlyStopping(monitor='loss', patience=10, verbose=0, restore_best_weights=True)
            
            self.model.fit(
                X_train, y_train, 
                batch_size=min(32, len(X_train)), 
                epochs=100, 
                callbacks=[early_stop], 
                verbose=0
            )
            
            self.logger.info(f"Model trained successfully with {len(X_train)} samples")
            
        except Exception as e:
            self.logger.error(f"Error training model: {str(e)}")
            raise

    def predict_future(self, n_steps=30):
        """
        Use the trained model to predict future values.
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model and scaler must be trained before predicting.")
        
        try:
            future_predictions = []
            
            # Start with the last sequence from all readings
            last_sequence = self.all_readings[-self.sequence_length:]
            current_sequence = self.scaler.transform(last_sequence)
            
            # Generate predictions
            for _ in range(n_steps):
                input_sequence = np.reshape(current_sequence, (1, self.sequence_length, 1))
                next_pred_scaled = self.model.predict(input_sequence, verbose=0)
                
                # Inverse transform to get actual value
                next_pred = self.scaler.inverse_transform(next_pred_scaled)[0, 0]
                future_predictions.append(float(next_pred))  # Ensure JSON serializable
                
                # Update sequence for next prediction
                current_sequence = np.append(current_sequence[1:], next_pred_scaled, axis=0)
            
            return future_predictions
            
        except Exception as e:
            self.logger.error(f"Error predicting future values: {str(e)}")
            raise



