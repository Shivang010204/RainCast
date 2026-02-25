import pandas as pd

# Load your data
df = pd.read_csv('prediction_history.csv')

# 1. Convert Time to datetime and extract Hour
df['Time'] = pd.to_datetime(df['Time'])
df['Hour'] = df['Time'].dt.hour

# 2. Handle duplicates (Keep the first search of that minute)
df = df.drop_duplicates(subset=['Time', 'City'])

# 3. Fill empty reports
df['Report'] = df['Report'].fillna('Normal')
df['Status'] = df['Status'].replace('Pending', 'No Report')

# 4. Filter for ML training (only keep rows with numeric weather data)
clean_data = df.dropna(subset=['Temp', 'Hum', 'Press', 'Wind'])

print(f"Cleaned data saved. Rows reduced from {len(df)} to {len(clean_data)} unique entries.")