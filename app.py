from flask import Flask, render_template, request, redirect, url_for, flash, session
import joblib
import requests
import csv
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "raincast_secure_key_123" 

# ================= CONFIGURATION =================
API_KEY = "ad89b1ffcd8e32f477047bed964e118b"
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
MODEL_PATH = "model/raincast_model.pkl"
HISTORY_FILE = "data/prediction_history.csv"
JSON_HISTORY_FILE = "data/prediction_history.json" 
UPLOAD_FOLDER = 'static/uploads'

# Ensure directories exist
os.makedirs('model', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Load ML Model
try:
    model = joblib.load(MODEL_PATH)
except:
    print("Warning: Model file not found. Ensure raincast_model.pkl exists in model/ folder.")

# ================= HELPER FUNCTIONS =================

def sync_to_json():
    """Converts the CSV history to JSON format for web compatibility."""
    try:
        if os.path.exists(HISTORY_FILE):
            df = pd.read_csv(HISTORY_FILE)
            df.to_json(JSON_HISTORY_FILE, orient='records', indent=4)
    except Exception as e:
        print(f"Sync Error: {e}")

def generate_advice(temp, hum, wind, prediction, mode):
    """Generates professional sector-specific protocols."""
    advice = {
        "clothing": "Standard professional attire.",
        "activity": "Operational tasks normal.",
        "dos": "Monitor local sky conditions.",
        "donts": "Ignore sudden weather shifts.",
        "sector": "General Public"
    }
    
    if prediction == "Rain Expected":
        advice["clothing"] = "Carry weather-resistant gear/umbrella."
        advice["activity"] = "Prioritize indoor operations."

    if mode == "farmer":
        advice["sector"] = "Agricultural Sector"
        if wind > 10:
            advice["dos"], advice["donts"] = "Secure irrigation lines and nets.", "Do not apply chemical sprays."
        elif prediction == "Rain Expected":
            advice["dos"], advice["donts"] = "Clear drainage for field runoff.", "Do not apply nitrogen fertilizers."
        else:
            advice["dos"], advice["donts"] = "Ideal for sowing and harvesting.", "Do not over-irrigate unnecessarily."

    elif mode == "construction":
        advice["sector"] = "Infrastructure & Safety"
        if prediction == "Rain Expected":
            advice["dos"], advice["donts"] = "Cover cement stock and power tools.", "Do not perform concrete pouring."
        elif wind > 15:
            advice["dos"], advice["donts"] = "Ensure scaffolding is anchored.", "Suspend all high-altitude crane ops."
        else:
            advice["dos"], advice["donts"] = "Safe for external structural work.", "Verify integrity of electrical pits."
            
    return advice

# ================= ROUTES =================

@app.route("/", methods=["GET", "POST"])
def index():
    prediction, weather, error, community_report, advice = [None]*5
    records = []

    # Read records for community alerts
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))

    # Determine City and Mode from multiple sources
    current_mode = request.form.get("user_mode") or request.args.get("user_mode") or session.get('last_mode', 'standard')
    city = request.form.get("city") or request.args.get("city") or session.get('last_city')

    if city:
        city = city.strip()
        session['last_city'] = city
        session['last_mode'] = current_mode
        
        try:
            params = {"q": city, "appid": API_KEY, "units": "metric"}
            res = requests.get(WEATHER_URL, params=params).json()
            
            if res.get("cod") != 200: 
                error = "Operational Target: City not found."
                session.pop('last_city', None)
            else:
                # Weather Data Extraction
                temp, hum, press, wind = res["main"]["temp"], res["main"]["humidity"], res["main"]["pressure"], res["wind"]["speed"]
                lon, lat = res["coord"]["lon"], res["coord"]["lat"]
                
                # ML Inference Logic
                result = model.predict([[temp, hum, press, wind]])[0]
                prediction = "Rain Expected" if result == 1 else "No Rain"
                
                weather = {"city": city, "temp": temp, "hum": hum, "wind": wind, "lon": lon, "lat": lat}
                advice = generate_advice(temp, hum, wind, prediction, current_mode)

                # Check for Community Reports within last 60 mins
                for row in reversed(records):
                    if len(row) > 8 and row[1].lower() == city.lower() and row[8] != "":
                        try:
                            report_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                            if datetime.now() - report_time < timedelta(minutes=60):
                                community_report = row[8]
                                break
                        except: continue
                
                # Log search to History CSV
                file_exists = os.path.isfile(HISTORY_FILE)
                with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["Time", "City", "Temp", "Hum", "Press", "Wind", "ML", "API", "Report", "Mode", "Lat", "Lon", "Proof"])
                    writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), city, temp, hum, press, wind, prediction, "OK", "", current_mode, lat, lon, ""])
                
                sync_to_json() 
                
                # Refresh records for the map UI
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    records = list(csv.reader(f))

        except Exception as e: 
            error = f"System Error: API Connection Failure."

    return render_template("dashboard.html", prediction=prediction, weather=weather, error=error, 
                           community_report=community_report, advice=advice, 
                           current_mode=current_mode, records=records)

@app.route('/report', methods=['POST'])
def save_report():
    city = request.form.get('city')
    status = request.form.get('status')
    lat, lon = request.form.get('lat', ""), request.form.get('lon', "")
    
    file = request.files.get('proof_img')
    img_filename = ""
    
    if file and file.filename != '':
        ts = datetime.now().strftime("%H%M%S")
        img_filename = secure_filename(f"{city}_{ts}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))
    
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = list(csv.reader(f))
            
            # Find the last empty report for this city and update it
            for i in range(len(records)-1, 0, -1):
                if records[i][1].lower() == city.lower() and records[i][8] == "":
                    while len(records[i]) < 13: records[i].append("")
                    records[i][8] = status
                    records[i][10] = lat
                    records[i][11] = lon
                    records[i][12] = img_filename
                    break
            
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(records)
            
            sync_to_json()
        flash(f"Verified {status} report for {city} synchronized successfully.")
    except:
        flash("Error saving verification data.")

    return redirect(url_for("index", city=city))

@app.route("/forecast")
def get_forecast():
    city = session.get('last_city')
    if not city: return redirect(url_for('index'))

    res = requests.get(FORECAST_URL, params={"q": city, "appid": API_KEY, "units": "metric"}).json()
    
    predictions = []
    if res.get("cod") == "200":
        for item in res['list'][::8]: # Take one reading per day
            temp, hum, press, wind = item['main']['temp'], item['main']['humidity'], item['main']['pressure'], item['wind']['speed']
            
            result = model.predict([[temp, hum, press, wind]])[0]
            status = "Rain Expected" if result == 1 else "Clear Skies"
            
            predictions.append({
                "date": item['dt_txt'].split(" ")[0], 
                "temp": temp, 
                "status": status
            })
    
    return render_template("forecast.html", city=city, predictions=predictions)

@app.route("/standard")
def standard_portal():
    city = request.args.get('city')
    if not city: 
        return redirect(url_for('index'))
    
    # Fetch fresh data for the detailed view
    res = requests.get(WEATHER_URL, params={"q": city, "appid": API_KEY, "units": "metric"}).json()
    
    if res.get("cod") != 200: 
        flash("City data unavailable for detailed analysis.")
        return redirect(url_for('index'))
    
    # Logic for Standard Persona (Heat Index / Comfort)
    temp = res["main"]["temp"]
    hum = res["main"]["humidity"]
    feels_like = temp + 2 if hum > 60 else temp
    
    return render_template("standard.html", city=city, temp=temp, hum=hum, feels_like=feels_like)

@app.route("/history")
def history():
    records = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader) # skip header
            records = list(reader)
    return render_template("history.html", records=reversed(records))

@app.route("/clear")
def clear_search():
    session.pop('last_city', None)
    flash("Session cache cleared.")
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)