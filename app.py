from flask import Flask
from dotenv import load_dotenv
import os, joblib
from models import db

load_dotenv()

# We keep the ML models globally available or attached to the app context.
# In a true enterprise layout, these would be spun up in a separate Microservice,
# but for this scale, attaching to the global namespace is acceptable.
models_loaded = False
temp_model = None
rain_model = None
le_city = None
le_mode = None

MODEL_REG_PATH = "model/temp_regressor.pkl"
MODEL_CLF_PATH = "model/rain_classifier.pkl"
LE_CITY_PATH = "model/city_encoder.pkl"
LE_MODE_PATH = "model/mode_encoder.pkl"

try:
    temp_model = joblib.load(MODEL_REG_PATH)
    rain_model = joblib.load(MODEL_CLF_PATH)
    le_city = joblib.load(LE_CITY_PATH)
    le_mode = joblib.load(LE_MODE_PATH)
    models_loaded = True
except Exception as e:
    print(f"Model Load Warning: {e}")

def get_ai_prediction(temp, hum, press, wind, city_name, mode_name):
    if not models_loaded: return "AI Offline", temp
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


def create_app():
    app = Flask(__name__)
    app.secret_key = "raincast_secure_key_123"
    
    # Configure Database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather_intelligence.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        # Create Tables if they don't exist
        db.create_all()

    # Register Blueprints
    from routes import register_blueprints
    register_blueprints(app)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)