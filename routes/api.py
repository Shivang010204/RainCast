from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from PIL import Image, ImageStat
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
        
        # Fraud Check: Image metadata
        img = Image.open(file)
        exif_data = img._getexif()
        if not exif_data: return jsonify({"status": "error", "message": "Anti-Fraud: No EXIF found."})
        
        img_time_str = exif_data.get(36867) or exif_data.get(306)
        if not img_time_str: return jsonify({"status": "error", "message": "Metadata empty."})
        
        img_time = datetime.strptime(img_time_str.strip(), '%Y:%m:%d %H:%M:%S')
        if datetime.now() - img_time > timedelta(minutes=10):
            return jsonify({"status": "error", "message": "Verification Failed: Photo older than 10 mins."})

        # Heuristic Analysis: Check if image has details (not fully black/white)
        gray_img = img.convert("L")
        stat = ImageStat.Stat(gray_img)
        if stat.stddev[0] < 5.0:
            return jsonify({"status": "error", "message": "Quality Failed: Image details too low or blank."})

        # Save to DB as 'pending'
        new_report = P2PReport(city=city, report_type=user_choice, status="pending")
        db.session.add(new_report)
        db.session.commit()

        return jsonify({"status": "success", "message": "Report logged! Waiting for peer verification."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@api_bp.route("/check_status/<city>")
def check_status(city):
    recent_threshold = datetime.utcnow() - timedelta(hours=1)
    report = P2PReport.query.filter(
        P2PReport.city == city,
        P2PReport.status == "verified",
        P2PReport.timestamp >= recent_threshold
    ).order_by(P2PReport.timestamp.desc()).first()
    
    if report:
        return jsonify({"status": f"Verified {report.report_type} (Peer Consensus)"})
        
    return jsonify({"status": "Clear"})

@api_bp.route("/pending_report/<city>")
def pending_report(city):
    recent_threshold = datetime.utcnow() - timedelta(hours=1)
    report = P2PReport.query.filter(
        P2PReport.city == city,
        P2PReport.status == "pending",
        P2PReport.timestamp >= recent_threshold
    ).order_by(P2PReport.timestamp.desc()).first()
    
    if report:
        return jsonify({"exists": True, "id": report.id, "report_type": report.report_type})
    return jsonify({"exists": False})

@api_bp.route("/vote/<int:report_id>", methods=["POST"])
def submit_vote(report_id):
    vote = request.json.get("vote") # 'yes' or 'no'
    report = P2PReport.query.get(report_id)
    if not report or report.status != "pending":
        return jsonify({"status": "error", "message": "Report unavailable."})

    if vote == "yes":
        report.votes_yes += 1
    elif vote == "no":
        report.votes_no += 1

    # Check for consensus threshold
    if report.votes_yes >= 5:
        report.status = "verified"
    elif report.votes_no >= 3:
        report.status = "rejected"
        
    db.session.commit()
    return jsonify({"status": "success", "message": "Vote accepted."})
