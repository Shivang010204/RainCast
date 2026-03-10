from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from PIL import Image
from models import db, P2PReport
import os

api_bp = Blueprint('api', __name__)

@api_bp.route("/report", methods=["POST"])
def handle_report():
    try:
        file = request.files.get('photo')
        city = request.form.get('city')
        user_choice = request.form.get('choice') 
        
        if not file: return jsonify({"status": "error", "message": "Photo is required!"})
        if not city: return jsonify({"status": "error", "message": "City is required!"})
        
        # Fraud Check
        img = Image.open(file)
        exif_data = img._getexif()
        if not exif_data: return jsonify({"status": "error", "message": "Anti-Fraud: No EXIF found."})
        
        img_time_str = exif_data.get(36867) or exif_data.get(306)
        if not img_time_str: return jsonify({"status": "error", "message": "Metadata empty."})
        
        img_time = datetime.strptime(img_time_str.strip(), '%Y:%m:%d %H:%M:%S')
        if datetime.now() - img_time > timedelta(minutes=10):
            return jsonify({"status": "error", "message": "Verification Failed: Photo older than 10 mins."})

        # Save to DB instead of memory dictionary
        new_report = P2PReport(city=city, report_type=user_choice)
        db.session.add(new_report)
        db.session.commit()
        
        # Count recent reports for the city
        recent_threshold = datetime.utcnow() - timedelta(hours=1)
        count = P2PReport.query.filter(
            P2PReport.city == city,
            P2PReport.timestamp >= recent_threshold
        ).count()

        return jsonify({"status": "success", "message": f"Verified! {count}/5 confirms."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@api_bp.route("/check_status/<city>")
def check_status(city):
    recent_threshold = datetime.utcnow() - timedelta(hours=1)
    reports = P2PReport.query.filter(
        P2PReport.city == city,
        P2PReport.timestamp >= recent_threshold
    ).order_by(P2PReport.timestamp.desc()).all()
    
    if reports and len(reports) >= 5:
        # Simplistic consensus: take the type of the last report if we have >= 5
        last_type = reports[0].report_type
        return jsonify({"status": f"Verified {last_type} (Peer Consensus)"})
        
    return jsonify({"status": "Clear"})
