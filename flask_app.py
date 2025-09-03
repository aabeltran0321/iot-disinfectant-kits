from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime, timedelta
import pytz
import smtplib
from email.mime.text import MIMEText
from threading import Timer

app = Flask(__name__)
extension = "./"
iotdisinfectant_DB_NAME = f"{extension}iotdisinfectant_schedule.db"

GMAIL_USER = 'info.bbautomation@gmail.com'
GMAIL_PASSWORD = 'fzvd tysn qikk iydx'

# Track tank empty notifications
tank_empty_notified = {1: False, 2: False}


def iot_disinfectant_send_email(subject, message):
    # --- Email Config ---
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    EMAIL_ADDRESS = GMAIL_USER
    EMAIL_PASSWORD = GMAIL_PASSWORD
    NOTIFY_TO = "garcia.johnjosef.d@gmail.com"

    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = NOTIFY_TO

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[EMAIL SENT] {subject}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


def iotdisinfectant_init_db():
    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tank INTEGER,
                activation_time TEXT,
                duration_seconds INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tank_levels (
                tank INTEGER PRIMARY KEY,
                level INTEGER
            )
        """)
        for tank in [1, 2]:
            cursor.execute("INSERT OR IGNORE INTO tank_levels (tank, level) VALUES (?, ?)", (tank, 1))
        conn.commit()


@app.route("/iotdisinfectant")
def iotdisinfectant_index():
    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules ORDER BY activation_time")
        schedules = cursor.fetchall()
        cursor.execute("SELECT * FROM tank_levels")
        tank_levels = cursor.fetchall()
    return render_template("iotdisinfectant_index.html", schedules=schedules, tank_levels=tank_levels)


@app.route("/iotdisinfectant/schedule", methods=["POST"])
def iotdisinfectant_schedule():
    tank = int(request.form["tank"])
    activation_time = request.form["time"]
    minutes = int(request.form["minutes"] or 0)
    seconds = int(request.form["seconds"] or 0)
    duration_seconds = minutes * 60 + seconds

    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO schedules (tank, activation_time, duration_seconds) VALUES (?, ?, ?)",
                       (tank, activation_time, duration_seconds))
        conn.commit()
    return redirect(url_for("iotdisinfectant_index"))


@app.route("/iotdisinfectant/delete_schedule/<int:id>")
def iotdisinfectant_delete_schedule(id):
    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE id=?", (id,))
        conn.commit()
    return redirect(url_for("iotdisinfectant_index"))


# --- API Endpoints (for ESP32s) ---
@app.route("/iotdisinfectant/get_schedule/<int:tank>", methods=["GET"])
def iotdisinfectant_get_schedule(tank):
    gmt8 = pytz.timezone("Asia/Manila")
    now = datetime.now(gmt8).strftime("%H:%M")
    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, duration_seconds FROM schedules WHERE tank=? AND activation_time=?", (tank, now))
        row = cursor.fetchone()
        if row:
            schedule_id, duration = row
            cursor.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            conn.commit()

            # Send START notification
            iot_disinfectant_send_email(f"Tank {tank} Activated",
                       f"Tank {tank} started activation at {now} for {duration} seconds.")

            # Schedule END notification
            Timer(duration, lambda: iot_disinfectant_send_email(f"Tank {tank} Deactivated",
                                               f"Tank {tank} finished activation at {datetime.now(gmt8).strftime('%H:%M')}")).start()

            return jsonify({"activate": True, "duration": duration})
    return jsonify({"activate": False})


@app.route("/iotdisinfectant/update_level", methods=["POST"])
def iotdisinfectant_update_level():
    global tank_empty_notified
    data = request.json
    tank = data.get("tank")
    level = data.get("level")

    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tank_levels SET level=? WHERE tank=?", (level, tank))
        conn.commit()

    # Notify if empty (level == 0)
    if level == 0 and not tank_empty_notified[tank]:
        iot_disinfectant_send_email(f"Tank {tank} Empty", f"Tank {tank} is empty. Please refill.")
        tank_empty_notified[tank] = True

    # Reset notification flag when refilled
    elif level > 0 and tank_empty_notified[tank]:
        tank_empty_notified[tank] = False

    return jsonify({"status": "updated"})


@app.route("/iotdisinfectant/tank_levels")
def get_tank_levels():
    with sqlite3.connect(iotdisinfectant_DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tank_levels")
        tank_levels = cursor.fetchall()
    return jsonify(tank_levels)


if __name__ == "__main__":
    iotdisinfectant_init_db()
    app.run(host="0.0.0.0", port=5000)
