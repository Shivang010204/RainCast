from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class P2PReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    report_type = db.Column(db.String(50), nullable=False) # 'Rain' or 'Clear'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="pending") # 'pending', 'verified', 'rejected'
    votes_yes = db.Column(db.Integer, default=0)
    votes_no = db.Column(db.Integer, default=0)

class PredictionHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.DateTime, default=datetime.utcnow)
    city = db.Column(db.String(100), nullable=False)
    temp = db.Column(db.Float)
    hum = db.Column(db.Float)
    press = db.Column(db.Float)
    wind = db.Column(db.Float)
    prediction = db.Column(db.String(50))
    status = db.Column(db.String(50))
    report = db.Column(db.String(50))
    mode = db.Column(db.String(50))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    proof_filename = db.Column(db.String(200))
    trust_score = db.Column(db.Float)
    votes_yes = db.Column(db.Integer, default=0)
    votes_no = db.Column(db.Integer, default=0)
