from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import joblib, requests, csv, os, time, pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "raincast_secure_key_123" 

# ================= CONFIGURATION =================
HISTORY_FILE = "data/prediction_history.csv"
UPLOAD_FOLDER = 'static/uploads'
ADMIN_PASSWORD = "shivang" 

# ML Model Paths
MODEL_REG_PATH = "model/temp_regressor.pkl"
MODEL_CLF_PATH = "model/rain_classifier.pkl"
LE_CITY_PATH = "model/city_encoder.pkl"
LE_MODE_PATH = "model/mode_encoder.pkl"

os.makedirs('model', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize CSV if not exists
if not os.path.exists(HISTORY_FILE):
    header = ["Time", "City", "Temp", "Hum", "Press", "Wind", "Prediction", "Status", "Report", "Mode", "Lat", "Lon", "Proof", "Trust", "Votes_Yes", "Votes_No"]
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(header)

# Load Models Safely
try:
    temp_model = joblib.load(MODEL_REG_PATH)
    rain_model = joblib.load(MODEL_CLF_PATH)
    le_city = joblib.load(LE_CITY_PATH)
    le_mode = joblib.load(LE_MODE_PATH)
    models_loaded = True
except:
    models_loaded = False
    print("Warning: One or more ML models/encoders not found.")

# ================= HELPERS =================

def get_image_metadata(image_path):
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if not exif_data: return None, False
            photo_time = None
            for tag, value in exif_data.items():
                decoded = TAGS.get(tag, tag)
                if decoded in ['DateTimeDigitized', 'DateTime']: photo_time = value
            return photo_time, True
    except: return None, False

def get_ai_prediction(temp, hum, press, wind, city_name, mode_name):
    if not models_loaded: return "AI Offline", temp
    try:
        # 1. Encode inputs for ML model
        try: c_code = le_city.transform([city_name])[0]
        except: c_code = 0
        try: m_code = le_mode.transform([mode_name])[0]
        except: m_code = 0
            
        features = [[hum, press, wind, c_code, m_code]]
        
        # 2. Run Classification (Rain/No Rain)
        is_rain = rain_model.predict(features)[0]
        prediction_text = "Rain Expected" if is_rain == 1 else "No Rain"
        
        # 3. Run Regression (Temperature)
        # We get the raw ML guess
        ml_guess = temp_model.predict(features)[0]
        
        # --- THE FIX: NORMALIZATION LAYER ---
        # If the ML guess is wildly different from the actual temp (like 41 vs 34),
        # we pull it back toward the real temp to create a "Correction" instead of a "Guess".
        
        # Rule: The AI can only adjust the temperature by +/- 15% of the current temp.
        diff = ml_guess - temp
        max_correction = 3.5  # Maximum allowed degrees to change
        
        if abs(diff) > max_correction:
            # If it's too high, we cap the correction
            corrected_temp = temp + (max_correction if diff > 0 else -max_correction)
        else:
            corrected_temp = ml_guess

        # Final Polish: If humidity is low (< 30%), don't let the heat index spike too high
        if hum < 30 and corrected_temp > (temp + 2.5):
            corrected_temp = temp + 2.0

        return prediction_text, round(corrected_temp, 1)

    except Exception as e:
        print(f"ML Error: {e}")
        return "Prediction Error", temp
def generate_advice(temp, hum, wind, prediction, mode, weather_code):
    advice = {"dos": "System scanning conditions..."}
    is_rainy = weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]
    is_clear = weather_code == 0
    
    if mode == "farmer":
        advice["dos"] = "Rain detected. Check drainage." if is_rainy else "Optimal for soil testing."
    elif mode == "construction":
        advice["dos"] = "Halt exterior work." if is_rainy else "Safe for structural work."
    else:
        advice["dos"] = "Carry an umbrella." if is_rainy else "Perfect for travel."
    return advice

# ================= ROUTES =================

@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize variables
    prediction, weather, advice, ai_temp = [None]*4
    hourly_data, records = [], []

    # Load History
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))[1:]

    # Get mode and city logic
    # We prioritize POST (user typing) over session to ensure we can catch new errors
    current_mode = request.form.get("user_mode") or request.args.get("user_mode") or session.get('last_mode', 'standard')
    city = request.form.get("city") or request.args.get("city") or session.get('last_city')

    if city and city.strip():
        city = city.strip()
        try:
            # 1. GEOCODING CALL
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
            geo_res = requests.get(geo_url).json()
            
            # --- BREAK THE REDIRECT LOOP ---
            if not geo_res.get("results"):
                # Remove bad city from session immediately so it doesn't loop
                session.pop('last_city', None) 
                flash(f"SATELLITE LINK FAILED: City '{city}' not found.", "error")
                return redirect(url_for('index'))
            
            # City is valid, save it to session
            session['last_city'], session['last_mode'] = city, current_mode
            
            loc = geo_res["results"][0]
            lat, lon, full_name = loc["latitude"], loc["longitude"], loc["name"]
            session['last_lat'], session['last_lon'] = lat, lon

            # 2. WEATHER API CALL
            w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code&hourly=temperature_2m,weather_code&timezone=auto"
            res = requests.get(w_url).json()
            
            if "current" not in res:
                session.pop('last_city', None)
                flash("TELEMETRY ERROR: Station data unavailable.", "error")
                return redirect(url_for('index'))

            curr = res["current"]
            t, h, p, w = round(curr["temperature_2m"]), curr["relative_humidity_2m"], curr["surface_pressure"], round(curr["wind_speed_10m"], 1)

            # ML PREDICTION CALL
            prediction, ai_temp = get_ai_prediction(t, h, p, w, city, current_mode)
            
            weather = {"city": full_name, "temp": t, "hum": h, "wind": w, "lat": lat, "lon": lon, "ai_temp": ai_temp}
            advice = generate_advice(t, h, w, prediction, current_mode, curr["weather_code"])

            # Sync Hourly Data
            api_times = res["hourly"]["time"]
            try:
                start_idx = api_times.index(curr["time"])
            except (ValueError, KeyError):
                start_idx = 0

            for i in range(start_idx, start_idx + 8):
                if i < len(api_times):
                    hourly_data.append({
                        "time": api_times[i].split("T")[1], 
                        "temp": round(res["hourly"]["temperature_2m"][i]), 
                        "code": res["hourly"]["weather_code"][i]
                    })

            # Log to History
            with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().strftime("%H:%M"), full_name, t, h, p, w, prediction, "OK", "", current_mode, lat, lon, "", "Pending", 0, 0])

        except Exception as e:
            print(f"Core Error: {e}")
            session.pop('last_city', None) # Clear bad state
            flash("CORE SYSTEM ERROR: Connection failure.", "error")
            return redirect(url_for('index'))

    return render_template("dashboard.html", 
                           prediction=prediction, 
                           weather=weather, 
                           advice=advice, 
                           current_mode=current_mode, 
                           records=records, 
                           hourly_data=hourly_data)
    
@app.route("/forecast")
def detailed_forecast():
    city, lat, lon = session.get('last_city'), session.get('last_lat'), session.get('last_lon')
    if not lat: return redirect(url_for('index'))
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=14"
    res = requests.get(url).json()
    daily_data = []
    for i in range(14):
        daily_data.append({
            "day": datetime.strptime(res['daily']['time'][i], '%Y-%m-%d').strftime('%a'),
            "date": datetime.strptime(res['daily']['time'][i], '%Y-%m-%d').strftime('%d %b'),
            "temp_max": round(res['daily']['temperature_2m_max'][i]),
            "temp_min": round(res['daily']['temperature_2m_min'][i]),
            "condition": "Forecast Data"
        })
    return render_template("forecast.html", city=city, daily=daily_data)

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
    return render_template("admin_login.html")

@app.route("/admin_panel")
def admin_panel():
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        recs = list(csv.reader(f))[1:]
    return render_template("admin_panel.html", records=recs)

@app.route("/delete_record/<int:index>")
def delete_record(index):
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if 0 < (index + 1) < len(rows):
        rows.pop(index + 1)
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    return redirect(url_for('admin_panel'))

@app.route("/admin_logout")
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route("/clear")
def clear():
    session.clear()
    return redirect(url_for('index'))

@app.route("/report_rain", methods=["POST"])
def report_rain():
    data = request.get_json()
    city = data.get('city')
    
    # Logic to update your CSV or Database
    # This shows the user that their 'Human Intelligence' is being recorded
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%H:%M"), city, "N/A", "N/A", "N/A", "N/A", "Rain Reported", "USER_REPORT"])
        
    return jsonify({"status": "success", "message": "Report logged"})



# Global dictionary to track pending peer-to-peer reports
# Key: City Name | Value: {'count': int, 'type': str, 'timestamp': datetime}
pending_reports = {}

@app.route("/report", methods=["POST"])
def handle_report():
    try:
        file = request.files.get('photo')
        city = request.form.get('city')
        user_choice = request.form.get('choice') 

        if not file:
            return jsonify({"status": "error", "message": "Photo is required for validation!"})

        # 1. EXIF EXTRACTION
        img = Image.open(file)
        exif_data = img._getexif()
        
        if not exif_data:
            return jsonify({"status": "error", "message": "Anti-Fraud: No EXIF metadata found. Use an original photo."})

        # Standard EXIF tags: 36867 (DateTimeOriginal), 306 (DateTime)
        img_time_str = exif_data.get(36867) or exif_data.get(306)
        
        if not img_time_str:
            return jsonify({"status": "error", "message": "Metadata empty: No timestamp detected."})

        # 2. TIME VALIDATION (10 Minute Rule)
        # We strip any extra spaces to prevent parsing errors
        img_time = datetime.strptime(img_time_str.strip(), '%Y:%m:%d %H:%M:%S')
        
        if datetime.now() - img_time > timedelta(minutes=10):
            return jsonify({"status": "error", "message": "Verification Failed: Photo is older than 10 minutes."})

        # 3. CONFORMITY & CONSENSUS LOGIC
        if city not in pending_reports:
            pending_reports[city] = {
                'count': 1, 
                'type': user_choice, 
                'timestamp': datetime.now()
            }
        else:
            pending_reports[city]['count'] += 1
            pending_reports[city]['timestamp'] = datetime.now() # Refresh the TTL

        return jsonify({
            "status": "success", 
            "message": f"Verified via EXIF! {pending_reports[city]['count']}/5 confirms for Red Zone alert."
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"System Error: {str(e)}"})

@app.route("/check_status/<city>")
def check_status(city):
    """Signals the frontend to trigger the 'Red Zone' UI"""
    if city in pending_reports:
        report = pending_reports[city]
        # Auto-expire reports older than 1 hour
        if datetime.now() - report['timestamp'] > timedelta(hours=1):
            del pending_reports[city]
            return jsonify({"status": "Clear"})
            
        if report['count'] >= 5:
            return jsonify({"status": f"Verified {report['type']} (Peer Consensus)"})
            
    return jsonify({"status": "Clear"})

@app.route("/get_broadcast/<city>")
def get_broadcast(city):
    """P2P Channel: Notifies other users in the same city to verify"""
    if city in pending_reports:
        report = pending_reports[city]
        if report['count'] < 5:
            return jsonify({
                "active": True,
                "type": report['type'],
                "count": report['count']
            })
    return jsonify({"active": False})


if __name__ == "__main__":
    app.run(debug=True)