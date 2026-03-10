from flask import Blueprint, render_template, request, session, flash, redirect, url_for
import requests, os, asyncio, aiohttp
from datetime import datetime

main_bp = Blueprint('main', __name__)

API_KEY = os.getenv("API_KEY", "")
HISTORY_FILE = "data/prediction_history.csv" # Deprecated location for old code ref

# --- Core ML dependencies mapped directly from the Flask app Context ---
# We use deferred imports or app.extensions to avoid circulatory issues usually,
# however for simplicity, we pass predictions back to the app context here.
# Since ML models are loaded in app.py, we will import the app instance lazily.

def generate_advice(temp, hum, wind, prediction, mode, weather_id, aqi=1):
    is_rainy = (200 <= weather_id <= 531) or ("rain expected" in str(prediction).lower())
    advice_map = {
        "standard": {
            "rain": "Wet conditions. Grab an umbrella.",
            "clear": "Clear weather. No umbrella needed."
        },
        "farmer": {
            "rain": "Moisture arriving. Check field drainage.",
            "clear": "Dry spell. Ideal for soil prep/harvest."
        },
        "construction": {
            "rain": "Precipitation. Secure materials, pause pouring.",
            "clear": "Clear conditions. Good for structural work."
        }
    }
    key = "rain" if is_rainy else "clear"
    selected_mode = mode if mode in advice_map else "standard"
    
    aqi_warning = ""
    if aqi >= 4:
        aqi_warning = f" ⚠️ Poor AQI ({aqi}). Limit exposure."
        if selected_mode == "construction":
            aqi_warning += " Wear masks."
    elif aqi == 3:
        aqi_warning = f" ℹ️ Moderate AQI ({aqi}). Sensitive groups take care."

    return {"dos": advice_map[selected_mode][key] + aqi_warning}


async def fetch_weather_data(lat, lon):
    async with aiohttp.ClientSession() as aio_session:
        w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
        g_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&timezone=auto"
        aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={API_KEY}"
        
        # Dispatch concurrently
        responses = await asyncio.gather(
            aio_session.get(w_url),
            aio_session.get(g_url),
            aio_session.get(aqi_url),
            return_exceptions=True
        )

        w_data = await responses[0].json() if not isinstance(responses[0], Exception) else {}
        g_data = await responses[1].json() if not isinstance(responses[1], Exception) else {}
        aqi_data = await responses[2].json() if not isinstance(responses[2], Exception) else {}
        
        return w_data, g_data, aqi_data


@main_bp.route("/", methods=["GET", "POST"])
async def index():
    prediction, weather, advice, hourly_data = None, None, None, []
    current_mode = (request.form.get("user_mode") or request.args.get("user_mode") or session.get('last_mode') or 'standard')
    session['last_mode'] = current_mode
    city = request.form.get("city") or request.args.get("city") or session.get('last_city')

    if city and city.strip():
        city = city.strip()
        try:
            # 1. Fetch Geo Location (Synchronous because it dictates the next async steps)
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={API_KEY}"
            geo_data = requests.get(geo_url).json()

            if geo_data:
                lat, lon, full_name = geo_data[0]['lat'], geo_data[0]['lon'], geo_data[0]['name']
                
                # 2. Fetch Data Concurrently
                w_data, g_data, aqi_data = await fetch_weather_data(lat, lon)
                
                # 3. Parse Responses
                t = round(w_data["main"]["temp"])
                h = w_data["main"]["humidity"]
                p = w_data["main"]["pressure"]
                w = round(w_data["wind"]["speed"] * 3.6, 1)
                vis = round(w_data.get("visibility", 0) / 1000, 1)
                condition_id = w_data["weather"][0]["id"]

                curr_hour_str = datetime.now().strftime("%Y-%m-%dT%H:00")
                try: 
                    start_idx = g_data["hourly"]["time"].index(curr_hour_str)
                except: 
                    start_idx = datetime.now().hour

                for i in range(start_idx, start_idx + 8):
                    if i < len(g_data["hourly"]["time"]):
                        hourly_data.append({
                            "time": g_data["hourly"]["time"][i].split("T")[1],
                            "temp": round(g_data["hourly"]["temperature_2m"][i])
                        })

                aqi = 1
                if "list" in aqi_data and len(aqi_data["list"]) > 0:
                    aqi = aqi_data["list"][0]["main"]["aqi"]


                # 4. Perform AI logic
                from app import get_ai_prediction
                prediction, ai_temp = get_ai_prediction(t, h, p, w, full_name, current_mode)
                
                weather = {"city": full_name, "temp": t, "hum": h, "wind": w, "pressure": p, "visibility": vis, "lat": lat, "lon": lon, "ai_temp": ai_temp, "aqi": aqi}
                advice = generate_advice(t, h, w, prediction, current_mode, condition_id, aqi)
                
                session['last_city'], session['last_lat'], session['last_lon'] = full_name, lat, lon
            else:
                flash(f"City '{city}' not found.", "error")
        except Exception as e:
            print(f"Sync Error: {e}")

    return render_template("dashboard.html", prediction=prediction or "", weather=weather, advice=advice, current_mode=current_mode, hourly_data=hourly_data, city=city)

@main_bp.route("/forecast")
def detailed_forecast():
    city, lat, lon = session.get('last_city'), session.get('last_lat'), session.get('last_lon')
    if not lat: return redirect(url_for('main.index'))
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=14"
    res = requests.get(url).json()
    daily_data = [{"day": datetime.strptime(res['daily']['time'][i], '%Y-%m-%d').strftime('%a'), "date": datetime.strptime(res['daily']['time'][i], '%Y-%m-%d').strftime('%d %b'), "temp_max": round(res['daily']['temperature_2m_max'][i]), "temp_min": round(res['daily']['temperature_2m_min'][i]), "condition": "Scan Complete"} for i in range(14)]
    return render_template("forecast.html", city=city, daily=daily_data)

@main_bp.route("/clear")
def clear():
    session.clear()
    return redirect(url_for('main.index'))
