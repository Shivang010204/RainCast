import pytest
from app import app
from routes.main import generate_advice
from app import get_ai_prediction

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# --- Testing Advice Generator ---
def test_generate_advice_clear_standard():
    advice = generate_advice(temp=25, hum=50, wind=10, prediction="No Rain", mode="standard", weather_id=800, aqi=1)
    assert "no umbrella needed" in advice["dos"].lower()
    
def test_generate_advice_rain_farmer():
    advice = generate_advice(temp=20, hum=80, wind=15, prediction="Rain Expected", mode="farmer", weather_id=500, aqi=2)
    assert "drainage" in advice["dos"].lower()
    
def test_generate_advice_aqi_warning():
    advice = generate_advice(temp=30, hum=40, wind=5, prediction="No Rain", mode="construction", weather_id=800, aqi=4)
    assert "mask" in advice["dos"].lower()

# --- Testing App Routes Responses ---
def test_home_page_load(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"RAINCAST AI" in response.data

def test_admin_redirect_unauthorized(client):
    response = client.get("/admin_panel")
    assert response.status_code == 302 # Redirect to login

def test_p2p_missing_image(client):
    response = client.post("/report", data={"city": "London", "choice": "Rain"})
    assert response.json["status"] == "error"
    assert "Photo is required!" in response.json["message"]
