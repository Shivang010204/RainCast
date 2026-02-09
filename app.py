from flask import Flask, render_template, request, redirect, url_for, flash, session
import joblib
import requests
import csv
import os
import json
import pandas as pd
import time
import shutil
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS

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
ADMIN_PASSWORD = "shivang" # Change this for your demo

os.makedirs('model', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

try:
    model = joblib.load(MODEL_PATH)
except:
    print("Warning: Model file not found.")

# ================= HELPER FUNCTIONS =================

def get_image_metadata(image_path):
    """ Extracts EXIF data to verify photo authenticity """
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if not exif_data:
                return None, False

            photo_time = None
            has_gps = False
            for tag, value in exif_data.items():
                decoded = TAGS.get(tag, tag)
                if decoded in ['DateTimeDigitized', 'DateTime']:
                    photo_time = value
                if decoded == 'GPSInfo':
                    has_gps = True
            return photo_time, has_gps
    except Exception as e:
        print(f"Metadata Error: {e}")
        return None, False

def sync_to_json():
    try:
        if os.path.exists(HISTORY_FILE):
            df = pd.read_csv(HISTORY_FILE)
            df.to_json(JSON_HISTORY_FILE, orient='records', indent=4)
    except Exception as e:
        print(f"Sync Error: {e}")
        
        
def generate_advice(temp, hum, wind, prediction, mode):
    """Generates professional sector-specific protocols based on ML and Weather data."""
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

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))

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
                temp, hum, press, wind = res["main"]["temp"], res["main"]["humidity"], res["main"]["pressure"], res["wind"]["speed"]
                lon, lat = res["coord"]["lon"], res["coord"]["lat"]
                
                result = model.predict([[temp, hum, press, wind]])[0]
                prediction = "Rain Expected" if result == 1 else "No Rain"
                
                weather = {"city": city, "temp": temp, "hum": hum, "wind": wind, "lon": lon, "lat": lat}
                advice = generate_advice(temp, hum, wind, prediction, current_mode)

                # Log search with empty columns for report and proof
                file_exists = os.path.isfile(HISTORY_FILE)
                with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["Time", "City", "Temp", "Hum", "Press", "Wind", "ML", "API", "Report", "Mode", "Lat", "Lon", "Proof", "Genuine_Status"])
                    writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), city, temp, hum, press, wind, prediction, "OK", "", current_mode, lat, lon, "", "Pending"])
                
                sync_to_json() 
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
    trust_status = "No Photo"

    if file and file.filename != '':
        ts = int(time.time())
        img_filename = secure_filename(f"{city}_{ts}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
        file.save(filepath)

        # OPTION 1: METADATA CHECK
        photo_time, has_gps = get_image_metadata(filepath)
        
        if photo_time:
            try:
                # EXIF dates use colons (2026:02:09)
                taken_at = datetime.strptime(photo_time[:10], '%Y:%m:%d')
                if taken_at.date() == datetime.now().date():
                    trust_status = "Genuine"
                else:
                    trust_status = "Old Photo"
            except:
                trust_status = "Metadata Error"
        else:
            trust_status = "Flagged (No Metadata)"
    
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = list(csv.reader(f))
            
            for i in range(len(records)-1, 0, -1):
                if records[i][1].lower() == city.lower() and records[i][8] == "":
                    while len(records[i]) < 14: records[i].append("")
                    records[i][8] = status
                    records[i][10] = lat
                    records[i][11] = lon
                    records[i][12] = img_filename
                    records[i][13] = trust_status # Genuine check
                    break
            
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(records)
            sync_to_json()
        flash(f"Report Verified as: {trust_status}")
    except:
        flash("Error saving verification data.")

    return redirect(url_for("index", city=city))

# ================= ADMIN PANEL LOGIC =================

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
        flash("Incorrect Password")
    return render_template("admin_login.html")

@app.route("/admin_panel")
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    records = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))
            if len(records) > 0:
                records.pop(0)  # Remove CSV header
                
    # FIX: Wrap reversed(records) in list() 
    # This turns it back into a list that has a length!
    return render_template("admin_panel.html", records=list(reversed(records)))

@app.route("/admin_logout")
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

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

@app.route("/delete_record/<int:index>")
def delete_record(index):
    # 1. Security Check: Only admins can delete
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    try:
        # 2. Read all existing records
        records = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = list(csv.reader(f))
            
            # Since admin_panel shows records in REVERSED order, 
            # we need to calculate the actual row index in the original file.
            # Header is at 0, data starts at 1.
            # Formula: (Total Length - 1) - index_from_ui
            header = records[0]
            data_rows = records[1:]
            
            # Remove the correct row from data_rows
            if 0 <= index < len(data_rows):
                # Reverse the index back to match original list
                actual_idx = (len(data_rows) - 1) - index
                
                # Optional: Delete physical image file
                img_file = data_rows[actual_idx][12]
                if img_file:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img_file))
                    except: pass
                
                del data_rows[actual_idx]
                
                # 3. Write back to CSV (Header + remaining Data)
                with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(data_rows)
                
                flash("Record successfully purged from system.")

    except Exception as e:
        flash(f"System Error: {str(e)}")
        
    return redirect(url_for('admin_panel'))

@app.route("/clear_all_data")
def clear_all_data():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    try:
        # 1. Reset the CSV File
        header = ["timestamp", "city", "temp", "hum", "wind", "desc", "prediction", "mode", "status", "advice", "lat", "lon", "image", "authenticity"]
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
        
        # 2. Clear the Uploads Folder
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for filename in os.listdir(app.config['UPLOAD_FOLDER']):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
        
        # 3. Clear JSON cache if you have one
        sync_to_json() 
        
        flash("System Reset Successful: All records and images purged.")
    except Exception as e:
        flash(f"Purge Failed: {str(e)}")
        
    return redirect(url_for('admin_panel'))

# (Keep your other routes: history, forecast, clear, generate_advice)

if __name__ == "__main__":
    app.run(debug=True)