import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, r2_score, mean_absolute_error

# --- STEP 1 & 2: LOAD DATA ---
df = pd.read_csv('prediction_history.csv')

# --- STEP 3: DATA CLEANING ---
df['Time'] = pd.to_datetime(df['Time'])
df['Hour'] = df['Time'].dt.hour
df = df.drop_duplicates(subset=['Time', 'City'])
df['Report'] = df['Report'].fillna('Normal')
df['Mode'] = df['Mode'].fillna('standard')
df['Status'] = df['Status'].replace('Pending', 'No Report')

# Remove rows with missing critical weather data
df = df.dropna(subset=['Temp', 'Hum', 'Press', 'Wind'])

# --- STEP 6: FEATURE ENCODING ---
le_city = LabelEncoder()
le_mode = LabelEncoder()

df['City_Code'] = le_city.fit_transform(df['City'])
df['Mode_Code'] = le_mode.fit_transform(df['Mode'])

# --- STEP 7: MACHINE LEARNING MODELS ---

# A. CLASSIFICATION: Predict "Rain" vs "No Rain"
# Target: 1 if user reported rain, else 0
X_clf = df[['Temp', 'Hum', 'Press', 'Wind', 'City_Code']]
y_clf = df['Report'].apply(lambda x: 1 if 'Rain' in str(x) else 0)

X_train_c, X_test_c, y_train_c, y_test_c = train_test_split(X_clf, y_clf, test_size=0.2, random_state=42)

clf_model = RandomForestClassifier(n_estimators=100, random_state=42)
clf_model.fit(X_train_c, y_train_c) # Corrected: Train with Train

# B. REGRESSION: Predict Temperature
# Features exclude Temp to avoid data leakage
X_reg = df[['Hum', 'Press', 'Wind', 'City_Code', 'Mode_Code']]
y_reg = df['Temp']

X_train_r, X_test_r, y_train_r, y_test_r = train_test_split(X_reg, y_reg, test_size=0.2, random_state=42)

# Linear Regression
lin_reg = LinearRegression()
lin_reg.fit(X_train_r, y_train_r) # Corrected: Train with Train

# Decision Tree (For Comparison)
dt_reg = DecisionTreeRegressor(random_state=42)
dt_reg.fit(X_train_r, y_train_r)

# --- STEP 8: COMPARATIVE ANALYSIS ---
print(f"--- Classification Results ---")
print(f"Accuracy: {accuracy_score(y_test_c, clf_model.predict(X_test_c)):.4f}\n")

print(f"--- Regression Results (Linear) ---")
print(f"R2 Score: {r2_score(y_test_r, lin_reg.predict(X_test_r)):.4f}")
print(f"MAE: {mean_absolute_error(y_test_r, lin_reg.predict(X_test_r)):.4f}\n")

print(f"--- Regression Results (Decision Tree) ---")
print(f"R2 Score: {r2_score(y_test_r, dt_reg.predict(X_test_r)):.4f}")
print(f"MAE: {mean_absolute_error(y_test_r, dt_reg.predict(X_test_r)):.4f}\n")

# --- SAVE MODELS FOR FLASK ---
joblib.dump(clf_model, 'rain_classifier.pkl')
joblib.dump(lin_reg, 'temp_regressor.pkl')
joblib.dump(le_city, 'city_encoder.pkl')
joblib.dump(le_mode, 'mode_encoder.pkl')

print("✅ All models and encoders saved successfully!")