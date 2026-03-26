import streamlit as st
import joblib
import pandas as pd
from datetime import datetime
import asyncio
import aiohttp
import requests
import os
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
API_KEY = os.getenv("API_KEY", "")

# --- Caching App Models ---
@st.cache_resource
def load_models():
    try:
        # These models are stored in the model/ directory of the project
        temp_model = joblib.load("model/temp_regressor.pkl")
        rain_model = joblib.load("model/rain_classifier.pkl")
        le_city = joblib.load("model/city_encoder.pkl")
        le_mode = joblib.load("model/mode_encoder.pkl")
        return temp_model, rain_model, le_city, le_mode
    except Exception as e:
        st.warning(f"Error loading models: {e}")
        return None, None, None, None

temp_model, rain_model, le_city, le_mode = load_models()

def get_ai_prediction(temp, hum, press, wind, city_name, mode_name):
    if not all([temp_model, rain_model, le_city, le_mode]):
        return "AI Offline", temp
    try:
        try: c_code = le_city.transform([city_name])[0]
        except: c_code = 0
        try: m_code = le_mode.transform([mode_name])[0]
        except: m_code = 0
            
        rain_features = [[temp, hum, press, wind, c_code]]
        is_rain = rain_model.predict(rain_features)[0]
        prediction_text = "Rain Expected" if is_rain == 1 else "No Rain"
        
        temp_features = [[hum, press, wind, c_code, m_code]]
        ml_guess = temp_model.predict(temp_features)[0]
        diff = ml_guess - temp
        max_correction = 3.5
        corrected_temp = temp + (max_correction if diff > 0 else -max_correction) if abs(diff) > max_correction else ml_guess

        return prediction_text, round(corrected_temp, 1)
    except:
        return "Prediction Error", temp

def generate_advice(temp, hum, wind, prediction, mode, weather_id):
    is_rainy = (200 <= weather_id <= 531) or ("rain expected" in str(prediction).lower())
    
    if is_rainy:
        if mode == "farmer":
            return "Moisture arriving; please check field drainage."
        elif mode == "construction":
            return "Precipitation expected; secure materials and pause pouring."
        else:
            return "Wet conditions ahead; consider taking an umbrella."
    else:
        if mode == "farmer":
             return "Dry weather expected; ideal for soil prep and harvest."
        elif mode == "construction":
             return "Clear conditions; optimum weather for structural work."
        else:
             return "Clear weather expected; no umbrella needed."

async def fetch_weather_data(lat, lon):
    async with aiohttp.ClientSession() as aio_session:
        w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
        g_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&timezone=auto"
        daily_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=14"
        
        # Dispatch concurrently
        responses = await asyncio.gather(
            aio_session.get(w_url),
            aio_session.get(g_url),
            aio_session.get(daily_url),
            return_exceptions=True
        )

        w_data = await responses[0].json() if not isinstance(responses[0], Exception) else {}
        g_data = await responses[1].json() if not isinstance(responses[1], Exception) else {}
        daily_data = await responses[2].json() if not isinstance(responses[2], Exception) else {}
        
        return w_data, g_data, daily_data

# --- WINDOWS EVENT LOOP FIX FOR ASYNCIO ---
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="RainCast AI", layout="wide", page_icon="🌤️")

st.title("🌧️ RainCast AI")
st.markdown("Your Intelligent Weather Profiler")

with st.sidebar:
    st.header("Settings")
    # Initialize session state for UI persistence
    if 'last_city' not in st.session_state:
        st.session_state['last_city'] = ""
    if 'last_mode' not in st.session_state:
        st.session_state['last_mode'] = "standard"
        
    city_input = st.text_input("Enter City", value=st.session_state['last_city'])
    
    modes = ["standard", "farmer", "construction"]
    idx = modes.index(st.session_state['last_mode']) if st.session_state['last_mode'] in modes else 0
    user_mode = st.selectbox("User Mode", options=modes, index=idx)
    
    fetch_btn = st.button("Get Forecast")

if fetch_btn and city_input:
    st.session_state['last_city'] = city_input
    st.session_state['last_mode'] = user_mode
    
    with st.spinner(f"Fetching data for {city_input}..."):
        try:
            # 1. Fetch Geo Location
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_input}&limit=1&appid={API_KEY}"
            geo_data = requests.get(geo_url).json()

            if geo_data:
                lat, lon, full_name = geo_data[0]['lat'], geo_data[0]['lon'], geo_data[0]['name']
                
                # 2. Fetch Data Concurrently
                w_data, g_data, daily_data = asyncio.run(fetch_weather_data(lat, lon))
                
                # 3. Parse Responses
                t = round(w_data["main"]["temp"])
                h = w_data["main"]["humidity"]
                p = w_data["main"]["pressure"]
                w = round(w_data["wind"]["speed"] * 3.6, 1)
                vis = round(w_data.get("visibility", 0) / 1000, 1)
                fl = round(w_data["main"].get("feels_like", t))
                condition_id = w_data["weather"][0]["id"]

                from datetime import timezone, timedelta
                hourly_data = []
                
                utc_dt = datetime.fromtimestamp(w_data["dt"], timezone.utc)
                city_time = utc_dt + timedelta(seconds=w_data.get("timezone", 0))
                curr_hour_str = city_time.strftime("%Y-%m-%dT%H:00")
                
                start_idx = 0
                if "hourly" in g_data and "time" in g_data["hourly"]:
                    for idx, time_str in enumerate(g_data["hourly"]["time"]):
                        if time_str >= curr_hour_str:
                            start_idx = idx
                            break

                    for i in range(start_idx, start_idx + 8):
                        if i < len(g_data["hourly"]["time"]):
                            hourly_data.append({
                                "Time": g_data["hourly"]["time"][i].split("T")[1],
                                "Temperature": round(g_data["hourly"]["temperature_2m"][i], 1)
                            })


                # 4. Perform AI logic
                prediction, ai_temp = get_ai_prediction(t, h, p, w, full_name, user_mode)
                
                advice = generate_advice(t, h, w, prediction, user_mode, condition_id)
                
                # Render using Streamlit components
                st.subheader(f"Current Weather in {full_name}")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Temperature", f"{t} °C", f"Feels like {fl} °C", help=f"AI corrected: {ai_temp} °C")
                col2.metric("Humidity", f"{h} %")
                col3.metric("Wind Speed", f"{w} km/h")
                col4.metric("Pressure", f"{p} hPa")

                st.markdown(f"**🤖 AI Analysis:** {prediction} — {advice}")

                st.divider()

                cols = st.columns(2)
                with cols[0]:
                    st.subheader("Hourly Forecast")
                    if hourly_data:
                        df_hourly = pd.DataFrame(hourly_data)
                        df_hourly.set_index("Time", inplace=True)
                        st.line_chart(df_hourly, use_container_width=True)
                    else:
                        st.write("No hourly data available.")

                with cols[1]:
                    st.subheader("14-Day Forecast")
                    if "daily" in daily_data:
                        fourteen_day = [{"Date": datetime.strptime(daily_data['daily']['time'][i], '%Y-%m-%d').strftime('%d %b'), 
                                         "Max Temp.": round(daily_data['daily']['temperature_2m_max'][i]), 
                                         "Min Temp.": round(daily_data['daily']['temperature_2m_min'][i])} 
                                        for i in range(14)]
                        df_daily = pd.DataFrame(fourteen_day)
                        df_daily.set_index("Date", inplace=True)
                        st.line_chart(df_daily, use_container_width=True)
                    else:
                        st.write("No daily data available.")

            else:
                st.error(f"City '{city_input}' not found. Please try a different location.")
        except Exception as e:
            st.error(f"Error fetching weather data: {e}")
