from flask import Flask, render_template, request, redirect, url_for, flash, session
import joblib
import requests
import csv
import os
import json
import pandas as pd
import time
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS

app = Flask(__name__)
app.secret_key = "raincast_secure_key_123" 

# ================= CONFIGURATION =================
API_KEY = "ad89b1ffcd8e32f477047bed964e118b"
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
MODEL_PATH = "model/raincast_model.pkl"
HISTORY_FILE = "data/prediction_history.csv"
JSON_HISTORY_FILE = "data/prediction_history.json" 
UPLOAD_FOLDER = 'static/uploads'
ADMIN_PASSWORD = "shivang" 

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
    except: pass

def generate_advice(temp, hum, wind, prediction, mode):
    advice = {"clothing": "Standard professional attire.", "activity": "Normal operations.", "dos": "Monitor sky.", "donts": "No shifts.", "sector": "General"}
    if prediction == "Rain Expected":
        advice["clothing"] = "Carry umbrella."
        advice["activity"] = "Indoor tasks."
    if mode == "farmer":
        advice["sector"] = "Agriculture"
        advice["dos"] = "Secure irrigation." if wind > 10 else "Drainage check."
    elif mode == "construction":
        advice["sector"] = "Infrastructure"
        advice["dos"] = "Cover cement." if prediction == "Rain Expected" else "Anchor scaffolding."
    return advice

# ================= USER ROUTES =================

@app.route("/", methods=["GET", "POST"])
def index():
    prediction, weather, error, advice, pending_report = [None]*5
    records = []

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            all_rows = list(csv.reader(f))
            records = all_rows[1:] if len(all_rows) > 1 else []

    current_mode = request.form.get("user_mode") or request.args.get("user_mode") or session.get('last_mode', 'standard')
    city = request.form.get("city") or request.args.get("city") or session.get('last_city')

    if city:
        city = city.strip()
        session['last_city'] = city
        session['last_mode'] = current_mode
        try:
            res = requests.get(WEATHER_URL, params={"q": city, "appid": API_KEY, "units": "metric"}).json()
            if res.get("cod") != 200:
                error = "City not found."
                session.pop('last_city', None)
            else:
                temp, hum, press, wind = res["main"]["temp"], res["main"]["humidity"], res["main"]["pressure"], res["wind"]["speed"]
                lon, lat = res["coord"]["lon"], res["coord"]["lat"]
                result = model.predict([[temp, hum, press, wind]])[0]
                prediction = "Rain Expected" if result == 1 else "No Rain"
                weather = {"city": city, "temp": temp, "hum": hum, "wind": wind, "lon": lon, "lat": lat}
                advice = generate_advice(temp, hum, wind, prediction, current_mode)

                for row in reversed(records):
                    if row[1].lower() == city.lower() and row[8] != "" and row[8] != row[6]:
                        pending_report = {"report": row[8], "ai_pred": row[6]}
                        break 

                with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if os.path.getsize(HISTORY_FILE) == 0:
                        writer.writerow(["Time", "City", "Temp", "Hum", "Press", "Wind", "ML", "API", "Report", "Mode", "Lat", "Lon", "Proof", "Status", "Yes_Votes", "No_Votes"])
                    writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), city, temp, hum, press, wind, prediction, "OK", "", current_mode, lat, lon, "", "Pending", 0, 0])
                sync_to_json()
        except: error = "API Connection Failure."

    return render_template("dashboard.html", prediction=prediction, weather=weather, error=error, advice=advice, current_mode=current_mode, records=records, pending_report=pending_report)

@app.route('/report', methods=['POST'])
def report():
    city = request.form.get('city')
    status = request.form.get('user_report') or request.form.get('status')
    file = request.files.get('proof_img')
    
    if not file or file.filename == '':
        flash("Action Blocked: Visual evidence is mandatory.")
        return redirect(url_for("index", city=city))

    ts = int(time.time())
    img_filename = secure_filename(f"{city}_{ts}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
    file.save(filepath)
    
    photo_time, _ = get_image_metadata(filepath)
    if not photo_time:
        os.remove(filepath)
        flash("Rejection: Photo lacks timestamp metadata. Use a live camera shot.")
        return redirect(url_for("index", city=city))

    try:
        taken_at = datetime.strptime(photo_time[:10], '%Y:%m:%d')
        trust_status = "Genuine" if taken_at.date() == datetime.now().date() else "Old Photo"
    except: trust_status = "Metadata Error"
    
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))
        for i in range(len(records)-1, 0, -1):
            if records[i][1].lower() == city.lower() and records[i][8] == "":
                while len(records[i]) < 16: records[i].append("")
                records[i][8], records[i][12], records[i][13] = status, img_filename, trust_status
                break
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(records)
        sync_to_json()
        flash(f"Report Logged: {trust_status}")
    return redirect(url_for("index", city=city))

@app.route("/vote/<city>/<choice>")
def vote(city, choice):
    if os.path.exists(HISTORY_FILE):
        rows = []
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        
        updated = False
        # Search from bottom (newest) to top
        for i in range(len(rows) - 1, 0, -1):
            # 1. Match city
            # 2. Match rows that HAVE a user report (index 8)
            if rows[i][1].lower() == city.lower() and rows[i][8].strip() != "":
                
                # Ensure columns 14 and 15 exist for Yes/No votes
                while len(rows[i]) < 16:
                    rows[i].append("0")
                
                # Update the count
                if choice == 'yes':
                    current_val = int(rows[i][14] if rows[i][14] else 0)
                    rows[i][14] = str(current_val + 1)
                else:
                    current_val = int(rows[i][15] if rows[i][15] else 0)
                    rows[i][15] = str(current_val + 1)
                
                # Logic to upgrade status based on community consensus
                y_count = int(rows[i][14])
                n_count = int(rows[i][15])
                
                if y_count >= 3:
                    rows[i][13] = "Community Verified"
                elif n_count >= 3:
                    rows[i][13] = "Consensus: False Report"
                
                updated = True
                break 

        if updated:
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
            sync_to_json()
            # This is the key: set the session so the HTML {% if %} block hides the card
            session[f'voted_{city}'] = True
            flash("Consensus data updated!")
        else:
            flash("Could not find an active report to vote on.")

    return redirect(url_for('index', city=city))

@app.route("/clear")
def clear():
    session.pop('last_city', None)
    return redirect(url_for('index'))

# ================= ADMIN ROUTES =================

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
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    records = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))[1:]
    return render_template("admin_panel.html", records=list(reversed(records)))

@app.route("/delete_record/<int:index>")
def delete_record(index):
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            records = list(csv.reader(f))
        header, data = records[0], records[1:]
        actual_idx = (len(data) - 1) - index
        if 0 <= actual_idx < len(data):
            img = data[actual_idx][12]
            if img:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img))
                except: pass
            del data[actual_idx]
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header); writer.writerows(data)
            sync_to_json()
            flash("Record Purged.")
    return redirect(url_for('admin_panel'))

@app.route("/clear_all_data")
def clear_all_data():
    if not session.get('is_admin'): return redirect(url_for('admin_login'))
    header = ["Time", "City", "Temp", "Hum", "Press", "Wind", "ML", "API", "Report", "Mode", "Lat", "Lon", "Proof", "Status", "Yes_Votes", "No_Votes"]
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(header)
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f))
    sync_to_json()
    flash("System Reset Successful.")
    return redirect(url_for('admin_panel'))

@app.route("/admin_logout")
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)