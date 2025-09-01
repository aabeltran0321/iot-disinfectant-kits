from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_NAME = "schedule.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tank INTEGER,
                activation_time TEXT
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

@app.route("/")
def index():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules")
        schedules = cursor.fetchall()
        cursor.execute("SELECT * FROM tank_levels")
        tank_levels = cursor.fetchall()
    return {
        "schedules": schedules,
        "tank_levels": tank_levels
    }

# ESP32 polls this endpoint
@app.route("/get_schedule/<int:tank>", methods=["GET"])
def get_schedule(tank):
    now = datetime.now().strftime("%H:%M")
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM schedules WHERE tank=? AND activation_time=?", (tank, now))
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM schedules WHERE id=?", (row[0],))
            conn.commit()
            return jsonify({"activate": True})
    return jsonify({"activate": False})

# ESP32 sends level updates
@app.route("/update_level", methods=["POST"])
def update_level():
    data = request.json
    tank = data.get("tank")
    level = data.get("level")
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tank_levels SET level=? WHERE tank=?", (level, tank))
        conn.commit()
    return jsonify({"status": "updated"})

@app.route("/schedule", methods=["POST"])
def schedule():
    tank = int(request.form["tank"])
    activation_time = request.form["time"]
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO schedules (tank, activation_time) VALUES (?, ?)", (tank, activation_time))
        conn.commit()
    return jsonify({"status": "scheduled"})

if __name__ == "__main__":
    init_db()
    app.run()
