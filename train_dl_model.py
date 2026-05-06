import pandas as pd
import numpy as np
import joblib
import os
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder

# Set random seeds for reproducibility
np.random.seed(42)
tf.random.set_seed(42)

def build_and_train_dl_model():
    print("1. Loading Data...")
    df = pd.read_csv('data/prediction_history.csv')

    # Data Cleaning (matching original logic)
    df['Time'] = pd.to_datetime(df['Time'], format='mixed', errors='coerce')
    df['Hour'] = df['Time'].dt.hour
    df = df.drop_duplicates(subset=['Time', 'City'])
    df['Report'] = df['Report'].fillna('Normal')
    df['Mode'] = df['Mode'].fillna('standard')
    df['Status'] = df['Status'].replace('Pending', 'No Report')
    df = df.dropna(subset=['Temp', 'Hum', 'Press', 'Wind'])

    # City Encoding
    le_city = LabelEncoder()
    df['City_Code'] = le_city.fit_transform(df['City'])

    # Feature & Target Selection
    # Features: [Temp, Hum, Press, Wind, City_Code]
    X = df[['Temp', 'Hum', 'Press', 'Wind', 'City_Code']]
    y = df['Report'].apply(lambda x: 1 if 'Rain' in str(x) else 0)

    # Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Deep Learning scaling requires standardized inputs for fast/stable convergence
    print("2. Normalizing Feedforward Features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Build the Neural Network
    print("3. Building the Neural Network...")
    model = Sequential([
        Dense(32, activation='relu', input_shape=(X_train_scaled.shape[1],)),
        Dropout(0.2), # Prevent overfitting
        Dense(16, activation='relu'),
        Dropout(0.2),
        Dense(8, activation='relu'),
        Dense(1, activation='sigmoid') # Sigmoid strictly outputs 0 to 1 probability
    ])

    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    # Train the Neural Network
    print("4. Training Deep Learning Engine...")
    history = model.fit(
        X_train_scaled, y_train, 
        epochs=100, 
        batch_size=16, 
        validation_data=(X_test_scaled, y_test),
        verbose=1
    )

    # Evaluate Model
    loss, accuracy = model.evaluate(X_test_scaled, y_test, verbose=0)
    print(f"\nTraining Complete. Validation Accuracy: {accuracy*100:.2f}%")

    # Save Deep Learning Artifacts
    print("5. Saving Artifacts to 'model/' directory...")
    os.makedirs('model', exist_ok=True)
    
    model.save('model/rain_dl_model.keras')
    joblib.dump(scaler, 'model/dl_scaler.pkl')
    
    # Only creating a new city encoder if requested/needed, but better to keep the old one consistent
    # if it's identical. Still, saving it safely just in case.
    joblib.dump(le_city, 'model/dl_city_encoder.pkl')

    print("Success! App is ready to convert to DL inference.")

if __name__ == "__main__":
    build_and_train_dl_model()
