from flask import Blueprint, render_template, request, session, redirect, url_for
import csv
from models import PredictionHistory
from .main import HISTORY_FILE

admin_bp = Blueprint('admin', __name__)
import os

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "shivang")

@admin_bp.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST" and request.form.get("password") == ADMIN_PASSWORD:
        session['is_admin'] = True
        return redirect(url_for('admin.admin_panel'))
    return render_template("admin_login.html")

@admin_bp.route("/admin_panel")
def admin_panel():
    if not session.get('is_admin'): return redirect(url_for('admin.admin_login'))
    
    # Temporarily read the CSV to avoid breaking existing history
    # Later we will read from HistoryDB Model
    recs = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            if len(reader) > 1:
                recs = reader[1:]
    return render_template("admin_panel.html", records=recs)

@admin_bp.route("/delete_record/<int:index>")
def delete_record(index):
    if not session.get('is_admin'): return redirect(url_for('admin.admin_login'))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if 0 < (index + 1) < len(rows):
            rows.pop(index + 1)
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
    return redirect(url_for('admin.admin_panel'))

@admin_bp.route("/admin_logout")
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('main.index'))
