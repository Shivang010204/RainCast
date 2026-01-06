from flask import Flask, render_template, request, jsonify
import joblib
import requests
import csv
import os
from datetime import datetime

app = Flask(__name__)

# ================= PATHS =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "raincast_model.pkl")
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "prediction_history.csv")

# ================= CONFIG =================
API_KEY = os.getenv("OPENWEATHER_API_KEY", "ad89b1ffcd8e32f477047bed964e118b")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# ================= LOAD MODEL =================
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError("❌ Model file not found")

model = joblib.load(MODEL_PATH)
print("✅ Model loaded successfully")

# ================= CREATE HISTORY FILE =================
os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "datetime",
            "city",
            "temperature",
            "humidity",
            "pressure",
            "wind_speed",
            "ml_prediction",
            "api_weather"
        ])

# ================= HOME =================
@app.route("/", methods=["GET", "POST"])
def index():
    prediction = None
    api_rain = None
    weather = None
    error = None

    if request.method == "POST":
        city = request.form.get("city")

        params = {
            "q": city,
            "appid": API_KEY,
            "units": "metric"
        }

        response = requests.get(WEATHER_URL, params=params)
        data = response.json()

        if data.get("cod") != 200:
            error = "City not found"
            return render_template("index.html", error=error)

        # Weather data
        temperature = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        wind_speed = data["wind"]["speed"]

        api_rain = "Rain" if "rain" in data else "Clear"

        # ML Prediction
        features = [[temperature, humidity, pressure, wind_speed]]
        result = model.predict(features)[0]
        prediction = "Rain Expected" if result == 1 else "No Rain"

        weather = {
            "city": city,
            "temperature": temperature,
            "humidity": humidity,
            "pressure": pressure,
            "wind_speed": wind_speed
        }

        # Save to history
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                city,
                temperature,
                humidity,
                pressure,
                wind_speed,
                prediction,
                api_rain
            ])

    return render_template(
        "index.html",
        prediction=prediction,
        api_rain=api_rain,
        weather=weather,
        error=error
    )

# ================= JSON API =================
@app.route("/predict", methods=["POST"])
def predict_api():
    data = request.json
    features = [[
        data["temperature"],
        data["humidity"],
        data["pressure"],
        data["wind_speed"]
    ]]
    result = model.predict(features)[0]
    return jsonify({"prediction": int(result)})

# ================= HISTORY PAGE =================
@app.route("/history")
def history():
    records = []
    with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        records = list(reader)

    return render_template("history.html", records=records)

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
