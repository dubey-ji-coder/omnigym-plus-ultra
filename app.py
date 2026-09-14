from flask import Flask, render_template, request, jsonify
import sqlite3
import google.generativeai as genai
import warnings
import os
import re
from datetime import datetime, date, timedelta

warnings.filterwarnings('ignore')
app = Flask(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
llm_active = API_KEY != "YOUR_API_KEY_HERE"
if llm_active: genai.configure(api_key=API_KEY)

HOSTEL_FOODS = [
    {"name": "Pre-Boiled Eggs (6 units)", "cals": 420, "p": 36, "c": 0, "f": 30, "cost": 42},
    {"name": "Roasted Chana (100g)", "cals": 380, "p": 19, "c": 58, "f": 6, "cost": 30},
    {"name": "Oats via Hot Water (100g)", "cals": 389, "p": 13, "c": 68, "f": 6, "cost": 25},
    {"name": "Pre-Cooked Chicken Breast (250g)", "cals": 412, "p": 77, "c": 0, "f": 8, "cost": 150},
    {"name": "Whey Isolate Scoop", "cals": 110, "p": 25, "c": 1, "f": 0, "cost": 75}
]

def init_db():
    conn = sqlite3.connect('omnigym_final.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Users (user_id INTEGER PRIMARY KEY, username TEXT, body_weight REAL, height_cm REAL, body_fat_pct REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Workout_Logs (log_id INTEGER PRIMARY KEY, user_id INTEGER, exercise_name TEXT, weight_lifted REAL, reps INTEGER, log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Daily_Nutrition (entry_id INTEGER PRIMARY KEY, user_id INTEGER, protein_intake INTEGER, carbs_intake INTEGER, fats_intake INTEGER, fibers_intake INTEGER, calories_consumed INTEGER, water_ml INTEGER, daily_steps INTEGER DEFAULT 0, entry_date DATE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Cut_Audits (audit_id INTEGER PRIMARY KEY, user_id INTEGER, fasted_weight REAL, body_fat REAL, audit_date DATE DEFAULT CURRENT_DATE)''')
    
    cursor.execute("SELECT COUNT(*) FROM Users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Users (username, body_weight, height_cm, body_fat_pct) VALUES ('Athlete_01', 102.0, 188.0, 22.0)")
        cursor.execute("INSERT INTO Daily_Nutrition (user_id, protein_intake, carbs_intake, fats_intake, fibers_intake, calories_consumed, water_ml, daily_steps, entry_date) VALUES (1, 188, 200, 60, 30, 2100, 0, 0, DATE('now'))")
        
        cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps, log_date) VALUES (1, 'Bench Press', 140, 1, datetime('now', '-14 days'))")
        cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps, log_date) VALUES (1, 'Squat', 150, 3, datetime('now', '-7 days'))")
        cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps, log_date) VALUES (1, 'Conventional Deadlift', 180, 1, datetime('now', '-2 days'))")
        
        past_dates = [(date.today() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 4)]
        for d in past_dates: cursor.execute("INSERT INTO Cut_Audits (user_id, fasted_weight, body_fat, audit_date) VALUES (1, 102.2, 22.1, ?)", (d,))
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/get_dashboard', methods=['GET'])
def get_dashboard():
    conn = sqlite3.connect('omnigym_final.db')
    cursor = conn.cursor()
    cursor.execute("SELECT body_weight, body_fat_pct, height_cm FROM Users WHERE user_id=1")
    user_data = cursor.fetchone()
    weight, bf, height = (user_data[0], user_data[1], user_data[2]) if user_data else (102.0, 22.0, 188.0)
    
    cursor.execute("SELECT protein_intake, carbs_intake, fats_intake, fibers_intake, calories_consumed, water_ml, daily_steps FROM Daily_Nutrition WHERE user_id=1 AND entry_date=DATE('now')")
    nut_data = cursor.fetchone()
    
    if nut_data:
        p, c, f, fib, cals, water, steps = nut_data
    else:
        new_cals = 2800 
        p, f, fib = int(weight * 2.2), int(weight * 0.8), int((new_cals / 1000) * 14) 
        c = int((new_cals - ((p * 4) + (f * 9))) / 4)
        cals, water, steps = new_cals, 0, 0
        cursor.execute("INSERT INTO Daily_Nutrition (user_id, protein_intake, carbs_intake, fats_intake, fibers_intake, calories_consumed, water_ml, daily_steps, entry_date) VALUES (1, ?, ?, ?, ?, ?, 0, 0, DATE('now'))", (p, c, f, fib, cals))
        conn.commit()
    
    cursor.execute("SELECT weight_lifted, reps, log_date FROM Workout_Logs")
    all_logs = cursor.fetchall()
    
    t_w1, t_w2, t_w3, t_now = 12000, 12500, 13200, 0
    now = datetime.now()
    for w, r, d_str in all_logs:
        try:
            log_date = datetime.strptime(d_str.split(" ")[0], "%Y-%m-%d")
            days_ago = (now - log_date).days
            vol = w * r
            if days_ago <= 7: t_now += vol
        except: pass
    if t_now == 0: t_now = 13800 
    
    conn.close()
    return jsonify({"status": "success", "weight": weight, "bf": bf, "height": height, "macros": {"protein": p, "carbs": c, "fats": f, "fibers": fib, "cals": cals}, "water": water, "steps": steps, "tonnage": [t_w1, t_w2, t_w3, t_now]})

@app.route('/api/sync_biometrics', methods=['POST'])
def sync_biometrics():
    weight = float(request.json.get('weight', 102.0))
    bf = float(request.json.get('bf', 22.0))
    height = float(request.json.get('height', 188.0))
    
    conn = sqlite3.connect('omnigym_final.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET body_weight=?, body_fat_pct=?, height_cm=? WHERE user_id=1", (weight, bf, height))
    
    new_cals = 2800 
    new_p, new_f, new_fib = int(weight * 2.2), int(weight * 0.8), int((new_cals / 1000) * 14) 
    new_c = int((new_cals - ((new_p * 4) + (new_f * 9))) / 4)
    
    cursor.execute("SELECT 1 FROM Daily_Nutrition WHERE user_id=1 AND entry_date=DATE('now')")
    if cursor.fetchone() is None: 
        cursor.execute("INSERT INTO Daily_Nutrition (user_id, protein_intake, carbs_intake, fats_intake, fibers_intake, calories_consumed, water_ml, daily_steps, entry_date) VALUES (1, ?, ?, ?, ?, ?, 0, 0, DATE('now'))", (new_p, new_c, new_f, new_fib, new_cals))
    else: 
        cursor.execute("UPDATE Daily_Nutrition SET protein_intake=?, carbs_intake=?, fats_intake=?, fibers_intake=?, calories_consumed=? WHERE user_id=1 AND entry_date=DATE('now')", (new_p, new_c, new_f, new_fib, new_cals))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "macros": {"protein": new_p, "carbs": new_c, "fats": new_f, "cals": new_cals}})

@app.route('/api/cut_state', methods=['POST'])
def cut_state():
    target_date_str = request.json.get('target_date', '2026-12-15')
    today = date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("SELECT fasted_weight, body_fat FROM Cut_Audits WHERE user_id=1 AND audit_date=?", (today,))
    today_audit = cursor.fetchone()
    
    if not today_audit:
        conn.close(); return jsonify({"status": "locked", "message": "Morning Weigh-in Required."})
    
    current_w, current_bf = today_audit
    fat_mass = round(current_w * (current_bf / 100), 2); lean_mass = round(current_w - fat_mass, 2)
    
    try: target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    except: target_date = datetime(2026, 12, 15)
    
    days_left = max((target_date - datetime.now()).days, 1)
    target_weight = round(lean_mass / (1 - 0.12), 2)
    weight_to_lose = current_w - target_weight
    
    daily_deficit = int((weight_to_lose * 7700) / days_left) if weight_to_lose > 0 else 0
    daily_target_cals = max(2800 - daily_deficit, 1200)
    
    cursor.execute("SELECT fasted_weight FROM Cut_Audits WHERE user_id=1 ORDER BY audit_date DESC LIMIT 4")
    recent_weights = [row[0] for row in cursor.fetchall()]
    stalled = False; stall_msg = "Glidepath optimal. Burn protocol active."
    
    if len(recent_weights) >= 3 and max(recent_weights[:3]) - min(recent_weights[:3]) < 0.2:
        stalled = True; stall_msg = "METABOLIC STALL DETECTED. System recommends steepening deficit by 150 kcal."
        daily_deficit += 150; daily_target_cals = max(daily_target_cals - 150, 1200)
            
    conn.close()
    return jsonify({
        "status": "unlocked",
        "telemetry": {"current_weight": current_w, "current_bf": current_bf, "lean_mass": lean_mass, "fat_mass": fat_mass, "target_weight": target_weight, "weight_to_lose": round(weight_to_lose, 2)},
        "glidepath": {"days_left": days_left, "daily_deficit": daily_deficit, "target_cals": daily_target_cals, "stalled": stalled, "stall_message": stall_msg}
    })

@app.route('/api/cut_unlock', methods=['POST'])
def cut_unlock():
    f_weight, bf = float(request.json.get('weight')), float(request.json.get('bf'))
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO Cut_Audits (user_id, fasted_weight, body_fat, audit_date) VALUES (1, ?, ?, ?)", (f_weight, bf, date.today().strftime("%Y-%m-%d")))
    cursor.execute("UPDATE Users SET body_weight=?, body_fat_pct=? WHERE user_id=1", (f_weight, bf))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/knapsack_optimizer', methods=['POST'])
def knapsack_optimizer():
    target_cals = request.json.get('target_cals', 1800)
    inventory = []
    for item in HOSTEL_FOODS: inventory.extend([item, item]) 
    n = len(inventory)
    dp = [0] * (target_cals + 1); selection = [[] for _ in range(target_cals + 1)]
    
    for i in range(n):
        item = inventory[i]; cals = item['cals']; protein = item['p']
        for c in range(target_cals, cals - 1, -1):
            if dp[c - cals] + protein > dp[c]:
                dp[c] = dp[c - cals] + protein; selection[c] = selection[c - cals] + [item]
                
    optimal_loadout = selection[target_cals]
    aggregated = {}; total_p = total_c = total_f = total_cals = total_cost = 0
    for item in optimal_loadout:
        if item['name'] not in aggregated: aggregated[item['name']] = {'qty': 0, 'cost': 0, 'cals': 0, 'p': 0, 'c': 0, 'f': 0}
        aggregated[item['name']]['qty'] += 1; aggregated[item['name']]['cost'] += item['cost']
        aggregated[item['name']]['cals'] += item['cals']; aggregated[item['name']]['p'] += item['p']
        aggregated[item['name']]['c'] += item['c']; aggregated[item['name']]['f'] += item['f']
        total_p += item['p']; total_c += item['c']; total_f += item['f']; total_cals += item['cals']; total_cost += item['cost']

    cart_output = [{"item": k, "servings": v['qty'], "cals": v['cals'], "p": v['p'], "c": v['c'], "f": v['f'], "cost": v['cost']} for k, v in aggregated.items()]
    return jsonify({"status": "success", "cart": cart_output, "totals": {"cals": total_cals, "p": total_p, "c": total_c, "f": total_f, "cost": total_cost}})

@app.route('/api/get_pr_vault', methods=['GET'])
def get_pr_vault():
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("SELECT exercise_name, weight_lifted, reps, log_date FROM Workout_Logs ORDER BY log_date DESC LIMIT 15")
    logs = [{"exercise": row[0], "weight": row[1], "reps": row[2], "date": row[3].split(" ")[0]} for row in cursor.fetchall()]
    cursor.execute("SELECT MAX(weight_lifted) FROM Workout_Logs WHERE exercise_name LIKE '%Bench%'")
    max_bench_row = cursor.fetchone()
    max_bench = max_bench_row[0] if max_bench_row and max_bench_row[0] else 0
    conn.close()
    
    wilks_score = int(max_bench * 0.60 * 1.5) 
    rarity_text = f"ANALYSIS: Factoring the biomechanical disadvantage of a 188cm wingspan (extended lever arm resistance), generating the isolated torque required for a {int(max_bench)}kg raw press indicates extremely high absolute structural power. This specific output-to-leverage ratio places your fast-twitch fiber activation in the upper echelon globally."
    return jsonify({"status": "success", "history": logs, "wilks_score": wilks_score, "rarity": rarity_text})

@app.route('/api/log_quick', methods=['POST'])
def log_quick():
    exercise, reps = request.json.get('exercise'), request.json.get('reps', 0)
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps) VALUES (1, ?, 0, ?)", (exercise, reps))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "ai_message": f"Spotter AI: Confirmed. {exercise} protocol activated."})

@app.route('/api/log_water', methods=['POST'])
def log_water():
    amount = int(request.json.get('amount', 500))
    today = date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("SELECT water_ml FROM Daily_Nutrition WHERE user_id=1 AND entry_date=?", (today,))
    row = cursor.fetchone()
    new_water = (row[0] if (row and row[0] is not None) else 0) + amount
    cursor.execute("UPDATE Daily_Nutrition SET water_ml=? WHERE user_id=1 AND entry_date=?", (new_water, today))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "new_water": new_water, "ai_message": f"💧 +{amount}ml logged."})

@app.route('/api/log_steps', methods=['POST'])
def log_steps():
    amount = int(request.json.get('amount', 1000))
    today = date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("SELECT daily_steps FROM Daily_Nutrition WHERE user_id=1 AND entry_date=?", (today,))
    row = cursor.fetchone()
    new_steps = (row[0] if (row and row[0] is not None) else 0) + amount
    cursor.execute("UPDATE Daily_Nutrition SET daily_steps=? WHERE user_id=1 AND entry_date=?", (new_steps, today))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "new_steps": new_steps, "ai_message": f"👟 +{amount} steps logged."})

@app.route('/api/log_session', methods=['POST'])
def log_session():
    session_lifts = request.json.get('session', [])
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    total_volume = sum([float(l['weight']) * int(l['reps']) for l in session_lifts])
    for l in session_lifts:
        cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps) VALUES (1, ?, ?, ?)", (l['exercise'], float(l['weight']), int(l['reps'])))
    conn.commit(); conn.close()
    msg = f"Spotter AI: Yes, exercise logged successfully! Tonnage and graphs updated. You accumulated {total_volume}kg in total volume."
    return jsonify({"status": "success", "ai_message": msg})

@app.route('/api/predict_overload', methods=['POST'])
def predict_overload():
    exercise = request.json.get('exercise')
    conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
    cursor.execute("SELECT weight_lifted, reps FROM Workout_Logs WHERE exercise_name=? ORDER BY log_date DESC LIMIT 1", (exercise,))
    history = cursor.fetchone(); conn.close()
    if not history: return jsonify({"status": "success", "predicted_weight": 60, "predicted_reps": 8})
    pred_w = history[0] + 2.5 if history[1] >= 3 else history[0]
    pred_r = 5 if history[1] >= 3 else history[1] + 1
    return jsonify({"status": "success", "predicted_weight": pred_w, "predicted_reps": pred_r})

@app.route('/api/chat_llm', methods=['POST'])
def chat_llm():
    user_msg = request.json.get('message')
    
    # NLP interception for manual typing commands
    weight_match = re.search(r'(\d+)\s*(kilo|kg|kilos)', user_msg.lower())
    reps_match = re.search(r'(\d+)\s*rep', user_msg.lower())
    exercise = "Bench Press" if "bench" in user_msg.lower() else "Conventional Deadlift" if "deadlift" in user_msg.lower() else "Squat" if "squat" in user_msg.lower() else "Unknown Lift"
    
    if weight_match and reps_match and exercise != "Unknown Lift":
        weight, reps = int(weight_match.group(1)), int(reps_match.group(1))
        conn = sqlite3.connect('omnigym_final.db'); cursor = conn.cursor()
        cursor.execute("INSERT INTO Workout_Logs (user_id, exercise_name, weight_lifted, reps) VALUES (1, ?, ?, ?)", (exercise, weight, reps))
        conn.commit(); conn.close()
        return jsonify({"status": "success", "reply": f"Yes, exercise logged successfully! Recorded {weight}kg {exercise} for {reps} reps.", "is_log": True})
        
    if llm_active:
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(f"You are Spotter AI, a highly advanced, full-fledged conversational AI assistant. You answer ANY question completely and accurately, while maintaining a slight tone of a high-tech systems coach. Provide full details. User: {user_msg}\nSpotter AI:")
            return jsonify({"status": "success", "reply": response.text})
        except: pass
    return jsonify({"status": "error", "reply": "AI processing core offline. Please configure your API key."})

if __name__ == '__main__':
    app.run(debug=True, port=5000)