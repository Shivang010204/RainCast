from flask import Flask, render_template, request, redirect, url_for, flash, session
import joblib
import requests
import csv
import os
import json
import pandas as pd  # <--- Added Pandas for easy conversion
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "raincast_secure_key_123" 

# ================= CONFIG =================
API_KEY = "ad89b1ffcd8e32f477047bed964e118b"
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
MODEL_PATH = "model/raincast_model.pkl"
HISTORY_FILE = "data/prediction_history.csv"
JSON_HISTORY_FILE = "data/prediction_history.json" # <--- Added JSON Path

# Load ML Model
model = joblib.load(MODEL_PATH)

# ================= HELPER FUNCTIONS =================

def sync_to_json():
    """Converts the CSV history to JSON format automatically."""
    try:
        if os.path.exists(HISTORY_FILE):
            df = pd.read_csv(HISTORY_FILE)
            # orient='records' makes it a list of dictionaries (perfect for JS/Web)
            df.to_json(JSON_HISTORY_FILE, orient='records', indent=4)
    except Exception as e:
        print(f"Sync Error: {e}")

def generate_advice(temp, hum, wind, prediction, mode):
    advice = {
        "clothing": "Standard daily wear.",
        "activity": "Outdoor plans are fine.",
        "dos": "Check local sky conditions.",
        "donts": "Don't ignore sudden clouds.",
        "sector": None
    }
    if prediction == "Rain Expected":
        advice["clothing"] = "Carry an umbrella/raincoat."
        advice["activity"] = "Indoor activities recommended."

    if mode == "farmer":
        advice["sector"] = "🚜 Farmer Guidelines"
        if wind > 10:
            advice["dos"], advice["donts"] = "Secure loose nets/plastic.", "Do not spray pesticides."
        elif prediction == "Rain Expected":
            advice["dos"], advice["donts"] = "Clear drainage channels.", "Do not apply fertilizer."
        else:
            advice["dos"], advice["donts"] = "Optimal sowing conditions.", "Don't over-irrigate."

    elif mode == "construction":
        advice["sector"] = "🏗️ Construction Safety"
        if prediction == "Rain Expected":
            advice["dos"], advice["donts"] = "Cover cement & tools.", "Do not pour concrete."
        elif wind > 15:
            advice["dos"], advice["donts"] = "Secure scaffolding.", "No crane operations."
        else:
            advice["dos"], advice["donts"] = "Safe for structural work.", "Check electrical pits."
    return advice

@app.route("/", methods=["GET", "POST"])
def index():
    prediction, weather, error, community_report, advice = [None]*5
    records = []

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))

    city = None
    current_mode = request.form.get("user_mode") or request.args.get("user_mode") or session.get('last_mode', 'standard')
    
    if request.method == "POST":
        city = request.form.get("city").strip()
    elif request.args.get("city"):
        city = request.args.get("city")
    else:
        city = session.get('last_city')

    if city:
        session['last_city'] = city
        session['last_mode'] = current_mode
        
        try:
            res = requests.get(WEATHER_URL, params={"q": city, "appid": API_KEY, "units": "metric"}).json()
            if res.get("cod") != 200: 
                error = "City not found"
                session.pop('last_city', None)
            else:
                temp, hum, press, wind = res["main"]["temp"], res["main"]["humidity"], res["main"]["pressure"], res["wind"]["speed"]
                lon, lat = res["coord"]["lon"], res["coord"]["lat"]
                
                result = model.predict([[temp, hum, press, wind]])[0]
                prediction = "Rain Expected" if result == 1 else "No Rain"
                
                weather = {"city": city, "temp": temp, "hum": hum, "wind": wind, "lon": lon, "lat": lat}
                advice = generate_advice(temp, hum, wind, prediction, current_mode)

                for row in reversed(records):
                    if len(row) > 8 and row[1].lower() == city.lower() and row[8] != "":
                        try:
                            report_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                            if datetime.now() - report_time < timedelta(minutes=60):
                                community_report = row[8]
                                break
                        except: continue
                
                if not os.path.exists("data"): os.makedirs("data")
                file_exists = os.path.isfile(HISTORY_FILE)
                with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["Time", "City", "Temp", "Hum", "Press", "Wind", "ML", "API", "Report", "Mode", "Lat", "Lon"])
                    writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), city, temp, hum, press, wind, prediction, "OK", "", current_mode, lat, lon])
                
                # --- AUTO SYNC TO JSON ---
                sync_to_json() 

                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    records = list(csv.reader(f))

        except Exception as e: 
            error = "Connection Error"

    return render_template("dashboard.html", prediction=prediction, weather=weather, error=error, 
                           community_report=community_report, advice=advice, 
                           current_mode=current_mode, records=records)

@app.route('/report', methods=['POST'])
def save_report():
    city = request.form.get('city')
    status = request.form.get('status')
    lat = request.form.get('lat', "")
    lon = request.form.get('lon', "")
    
    try:
        records = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = list(csv.reader(f))
            
            for i in range(len(records)-1, 0, -1):
                if records[i][1].lower() == city.lower() and records[i][8] == "":
                    while len(records[i]) < 12: records[i].append("")
                    records[i][8] = status
                    records[i][10] = lat
                    records[i][11] = lon
                    break
            
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(records)
            
            # --- AUTO SYNC TO JSON ---
            sync_to_json()

        flash(f"Success! Your {status} report for {city} is now live on the map.")
    except Exception as e:
        flash("Error saving report.")

    return redirect(url_for("index", city=city))

# ... [Rest of the persona routes remain same] ...

@app.route("/clear")
def clear_search():
    session.pop('last_city', None)
    return redirect(url_for('index'))

@app.route("/history")
def history():
    records = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            records = list(reader)
    return render_template("history.html", records=reversed(records))

if __name__ == "__main__":
    app.run(debug=True)