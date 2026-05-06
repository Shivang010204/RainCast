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
        le_city = joblib.load("model/city_encoder.pkl")
        le_mode = joblib.load("model/mode_encoder.pkl")
        
        dl_scaler = None
        dl_loaded = False
        if os.path.exists("model/rain_dl_model.keras"):
            try:
                from tensorflow.keras.models import load_model
                rain_model = load_model("model/rain_dl_model.keras")
                dl_scaler = joblib.load("model/dl_scaler.pkl")
                dl_loaded = True
            except Exception:
                pass  # TF not available – fall back to sklearn below

        if not dl_loaded:
            rain_model = joblib.load("model/rain_classifier.pkl")
            
        return temp_model, rain_model, le_city, le_mode, dl_scaler
    except Exception as e:
        st.warning(f"Error loading models: {e}")
        return None, None, None, None, None

temp_model, rain_model, le_city, le_mode, dl_scaler = load_models()

def get_ai_prediction(temp, hum, press, wind, city_name, mode_name):
    if not all([temp_model, rain_model, le_city, le_mode]):
        return "AI Offline", temp
    try:
        try: c_code = le_city.transform([city_name])[0]
        except: c_code = 0
        try: m_code = le_mode.transform([mode_name])[0]
        except: m_code = 0
            
        if dl_scaler is not None:
            raw_features = [[temp, hum, press, wind, c_code]]
            scaled_features = dl_scaler.transform(raw_features)
            dl_prob = rain_model.predict(scaled_features, verbose=0)[0][0]
            prediction_text = "Rain Expected" if dl_prob > 0.50 else "No Rain"
        else:
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

def render_dashboard(full_name, user_mode, t, h, p, w, fl, condition_id, hourly_data, daily_data):
    prediction, ai_temp = get_ai_prediction(t, h, p, w, full_name, user_mode)
    advice = generate_advice(t, h, w, prediction, user_mode, condition_id)
    
    st.subheader(f"Weather in {full_name}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Temperature", f"{t} °C", f"Feels like {fl} °C", help=f"AI corrected: {ai_temp} °C")
    col2.metric("Humidity", f"{h} %")
    col3.metric("Wind Speed", f"{w} km/h")
    col4.metric("Pressure", f"{p} hPa")

    st.markdown(f"**🤖 AI Analysis:** {prediction} — {advice}")

    st.divider()

    cols = st.columns(2)
    import altair as alt
    with cols[0]:
        st.subheader("Hourly Forecast")
        if hourly_data:
            df_hourly = pd.DataFrame(hourly_data)
            if "Time" in df_hourly.columns:
                min_t = df_hourly['Temperature'].min() - 2
                max_t = df_hourly['Temperature'].max() + 2
                chart_hr = alt.Chart(df_hourly).mark_line(point=True).encode(
                    x=alt.X('Time', sort=None),
                    y=alt.Y('Temperature', scale=alt.Scale(domain=[min_t, max_t]))
                )
                st.altair_chart(chart_hr, use_container_width=True)
            else:
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
            
            # Melt the dataframe so Altair can plot multiple lines easily
            df_melted = df_daily.melt('Date', var_name='Temp Type', value_name='Temperature')
            min_td = df_melted['Temperature'].min() - 2
            max_td = df_melted['Temperature'].max() + 2
            chart_daily = alt.Chart(df_melted).mark_line(point=True).encode(
                x=alt.X('Date', sort=None),
                y=alt.Y('Temperature', scale=alt.Scale(domain=[min_td, max_td])),
                color='Temp Type'
            )
            st.altair_chart(chart_daily, use_container_width=True)
        else:
            st.write("No daily data available.")

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
    
    st.divider()
    st.subheader("Process from Dataset")
    uploaded_file = st.file_uploader("Upload Dataset (CSV/JSON)", type=["csv", "json"])
    
    dataset_city_search = ""
    process_dataset = False
    
    if uploaded_file is not None:
        dataset_city_search = st.text_input("Enter City Name from Dataset")
        process_dataset = st.button("Search Dataset")

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


                # 4. Perform AI logic and render
                render_dashboard(full_name, user_mode, t, h, p, w, fl, condition_id, hourly_data, daily_data)

            else:
                st.error(f"City '{city_input}' not found. Please try a different location.")
        except Exception as e:
            st.error(f"Error fetching weather data: {e}")

elif process_dataset and uploaded_file is not None and dataset_city_search:
    st.session_state['last_mode'] = user_mode
    import numpy as np
    from datetime import timedelta
    
    with st.spinner(f"Searching for {dataset_city_search} in dataset..."):
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_json(uploaded_file)
                
            def find_col(dataframe, possible_names):
                for col in dataframe.columns:
                    if col.lower() in possible_names: return col
                return None
                
            city_col = find_col(df, ['city', 'location', 'name', 'place', 'district', 'subdivision', 'state_ut_name', 'state'])
            temp_col = find_col(df, ['temp', 'temperature', 't', 'avgtemp'])
            hum_col = find_col(df, ['humidity', 'hum', 'h'])
            press_col = find_col(df, ['pressure', 'press', 'p'])
            wind_col = find_col(df, ['wind', 'windspeed', 'wind_speed', 'w'])
            
            if city_col is None: df['city'] = [f"Location {i+1}" for i in range(len(df))]
            else: df['city'] = df[city_col]
            
            # Filter dataset
            search_mask = pd.Series(False, index=df.index)
            for col in df.select_dtypes(include=['object', 'string']).columns:
                search_mask = search_mask | df[col].astype(str).str.contains(dataset_city_search, case=False, na=False)
            
            df_filtered = df[search_mask]
            
            if df_filtered.empty:
                st.warning(f"Could not find '{dataset_city_search}' in the uploaded dataset.")
            else:
                # Take just the first match
                row = df_filtered.iloc[0]
                
                c_name = str(row['city'])
                t = float(row[temp_col]) if temp_col and pd.notnull(row[temp_col]) else 25.0
                h = float(row[hum_col]) if hum_col and pd.notnull(row[hum_col]) else 60.0
                p = float(row[press_col]) if press_col and pd.notnull(row[press_col]) else 1013.0
                w = float(row[wind_col]) if wind_col and pd.notnull(row[wind_col]) else 10.0
                
                fl = round(t + np.random.uniform(-1, 1))
                condition_id = 500 if h > 80 else 800
                
                # synthetic graphical data around dataset row
                base_t = t
                hourly_data = []
                now = datetime.now()
                for i in range(8):
                    hr_time = (now + timedelta(hours=i)).strftime("%H:00")
                    variation = np.sin((now.hour + i)/24.0 * np.pi) * 3 + np.random.uniform(-1,1)
                    hourly_data.append({"Time": hr_time, "Temperature": round(base_t + variation, 1)})
                    
                daily_data = {"daily": {"time": [], "temperature_2m_max": [], "temperature_2m_min": []}}
                for i in range(14):
                    day_str = (now + timedelta(days=i)).strftime("%Y-%m-%d")
                    daily_data["daily"]["time"].append(day_str)
                    base_max = base_t + np.random.uniform(2, 5)
                    base_min = base_t - np.random.uniform(2, 5)
                    trend = np.sin(i/14.0 * np.pi * 2) * 2
                    daily_data["daily"]["temperature_2m_max"].append(round(base_max + trend))
                    daily_data["daily"]["temperature_2m_min"].append(round(base_min + trend))

                render_dashboard(c_name, user_mode, t, h, p, w, fl, condition_id, hourly_data, daily_data)
                    
        except Exception as e:
            st.error(f"Error processing document: {e}")
