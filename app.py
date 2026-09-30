from flask import Flask, render_template, Response, jsonify
import cv2
import numpy as np
import json
import os
import requests
import threading
import time
import pyttsx3
from datetime import datetime
import database

app = Flask(__name__)

database.init_db()
for folder in ["students", "intruders"]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Student Master Details (Father Mobile Number Included)
STUDENTS_DATA = {
    "Vijay": {
        "roll_no": "1250439466",
        "class_roll": "48",
        "name": "Vijay Chaudhary",
        "father_name": "Brahamdev Chaudhary",
        "mother_name": "Sunita Devi",
        "class": "CSE-AI",
        "section": "2C",
        "mobile": "9984251087",          # Student Mobile
        "father_mobile": "9984251087"   # Father Mobile (Replace if different)
    }
}

# Real Mobile SMS Gateway Key
FAST2SMS_API_KEY = "GET https://www.fast2sms.com/dev/bulkV2?route=q&message=YOUR_MESSAGE&numbers=9999999999"  # Put your Fast2SMS API Key here for real SIM SMS

# Threading Voice Speech Engine (Camera lag free)
speech_lock = threading.Lock()
last_spoken = {}

def announce_voice(text, key_id, cooldown_sec=12):
    now = time.time()
    if key_id in last_spoken and (now - last_spoken[key_id]) < cooldown_sec:
        return
    last_spoken[key_id] = now

    def _run_speech():
        with speech_lock:
            try:
                engine = pyttsx3.init()
                engine.setProperty('rate', 145)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print("[Voice Error]:", e)

    threading.Thread(target=_run_speech, daemon=True).start()

sent_sms_today = set()

def send_sms(s):
    """ Send SMS to BOTH Student and Father """
    student_mob = s.get("mobile", "")
    father_mob = s.get("father_mobile", student_mob)

    mobs = list(set([m for m in [student_mob, father_mob] if m]))
    numbers_str = ",".join(mobs)

    message = (f"Attendance Alert: {s['name']} (Univ Roll: {s['roll_no']}) "
               f"marked PRESENT in {s['class']}-{s['section']} at "
               f"{datetime.now().strftime('%d-%m-%Y %I:%M %p')}.")

    print(f"\n📢 [SMS SENT TO {numbers_str}]: {message}\n")

    if FAST2SMS_API_KEY:
        try:
            url = "https://www.fast2sms.com/dev/bulkV2"
            payload = f"message={message}&language=english&route=q&numbers={numbers_str}"
            headers = {
                'authorization': FAST2SMS_API_KEY,
                'Content-Type': "application/x-www-form-urlencoded"
            }
            res = requests.post(url, data=payload, headers=headers)
            print("[SMS Response]:", res.text)
        except Exception as e:
            print("[SMS Error]:", e)

CASCADE_FILE = "haarcascade_frontalface_default.xml"
if not os.path.exists(CASCADE_FILE):
    import urllib.request
    url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
    urllib.request.urlretrieve(url, CASCADE_FILE)

face_cascade = cv2.CascadeClassifier(CASCADE_FILE)
recognizer = cv2.face.LBPHFaceRecognizer_create()

label_map = {}
faces_data = []
labels_data = []
current_id = 0

for file in os.listdir("students"):
    if file.endswith((".jpg", ".jpeg", ".png")):
        path = os.path.join("students", file)
        key_name = os.path.splitext(file)[0]
        
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        
        detected_faces = face_cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=5)
        for (x, y, w, h) in detected_faces:
            faces_data.append(img[y:y+h, x:x+w])
            labels_data.append(current_id)
            label_map[current_id] = key_name
            current_id += 1

is_trained = False
if len(faces_data) > 0:
    recognizer.train(faces_data, np.array(labels_data))
    is_trained = True

def get_current_slot():
    now = datetime.now()
    current_day = now.strftime("%A")
    current_time = now.strftime("%H:%M")

    if os.path.exists("timetable.json"):
        try:
            with open("timetable.json", "r") as f:
                timetable = json.load(f)
                for day_data in timetable:
                    if day_data["day"] == current_day:
                        for slot in day_data["schedule"]:
                            if slot["slot_start"] <= current_time < slot["slot_end"]:
                                return slot
        except Exception:
            pass
    return None

def get_student_info(search_name):
    if not search_name or search_name == "Unknown":
        return None
    search_clean = str(search_name).strip().lower()
    for key, info in STUDENTS_DATA.items():
        if search_clean in key.lower() or search_clean in info["name"].lower():
            return info
    return STUDENTS_DATA["Vijay"]

camera = cv2.VideoCapture(0)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            continue
        
        current_slot = get_current_slot()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))

        for (x, y, w, h) in faces:
            face_roi = gray[y:y+h, x:x+w]
            key_name = "Unknown"
    
            
            if is_trained:
                label, confidence = recognizer.predict(face_roi)
                if confidence < 85:
                    key_name = label_map.get(label, "Unknown")

            if key_name != "Unknown":

                s_data = get_student_info(key_name)
                box_color = (0, 255, 0)
                active_subject = current_slot["subject"] if current_slot else "General"
                
                database.log_attendance(s_data["name"], active_subject, "PRESENT")

                # Voice Alert
                announce_voice(f"Welcome {s_data['name']}. Attendance marked.", s_data['name'])

                # SMS Alert
                today_str = datetime.now().strftime("%Y-%m-%d")
                sms_key = f"{key_name}_{today_str}"
                if sms_key not in sent_sms_today:
                    send_sms(s_data)
                    sent_sms_today.add(sms_key)

                display_text = f"{s_data['name']} ({s_data['class_roll']})"
            else:
                box_color = (0, 0, 255)
                display_text = "Unknown"
                
                # Voice Alert for Unknown / Not Student
        announce_voice("Alert! Aapka data system me registered nahi hai. Kripya admin se contact karein.", "unknown")
        
        # Intruder Folder check aur Photo Save
        folder_path = "intruders"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        full_path = f"{folder_path}/intruder_{current_timestamp}.jpg"
        
        saved = cv2.imwrite(full_path, frame)
        if saved:
            print(f"📸 Unknown photo saved: {full_path}")

            cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 2)
            cv2.putText(frame, display_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def api_status():
    slot = get_current_slot()
    logs = database.get_recent_logs()
    
    enriched_logs = []
    for log in logs:
        # log: (student_name, in_time, out_time, total_time, status, subject)
        s_name = log[0]
        in_time = log[1]
        out_time = log[2]
        total_time = log[3]
        status = log[4]
        
        match_info = get_student_info(s_name)
        
        if match_info:
            enriched_logs.append({
                "name": match_info["name"],
                "univ_roll": match_info["roll_no"],
                "class_roll": match_info["class_roll"],
                "father_name": match_info["father_name"],
                "mother_name": match_info["mother_name"],
                "class_sec": f"{match_info['class']} - {match_info['section']}",
                "student_mobile": match_info["mobile"],
                "father_mobile": match_info.get("father_mobile", match_info["mobile"]),
                "in_time": in_time,
                "out_time": out_time,
                "total_time": total_time,
                "status": status
            })
        else:
            enriched_logs.append({
                "name": s_name, "univ_roll": "-", "class_roll": "-",
                "father_name": "-", "mother_name": "-", "class_sec": "-",
                "student_mobile": "-", "father_mobile": "-",
                "in_time": in_time, "out_time": out_time, "total_time": total_time, "status": status
            })

    return jsonify({
        "subject": slot["subject"] if slot else "Free / No Active Class",
        "teacher": slot["teacher"] if slot else "N/A",
        "time": datetime.now().strftime("%I:%M:%S %p"),
        "logs": enriched_logs
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    # app.py mein ye function aur route add/update karein
def load_full_timetable():
    if os.path.exists("timetable.json"):
        with open("timetable.json", "r") as f:
            return json.load(f)
    return []

@app.route('/api/timetable')
def api_timetable():
    data = load_full_timetable()
    # Sirf aaj ka din filter kar raha hu
    today = datetime.now().strftime("%A")
    for day_data in data:
        if day_data["day"] == today:
            return jsonify(day_data["schedule"])
    return jsonify([])

# SMS Sender with Debugging
def send_sms(s):
    mobile = s.get("mobile")
    if not FAST2SMS_API_KEY:
        print("❌ SMS FAILED: API KEY MISSING!")
        return
        
    message = f"Attendance Alert: {s['name']} (Roll: {s['class_roll']}) marked PRESENT."
    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = f"message={message}&language=english&route=q&numbers={mobile}"
    
    headers = {
        'authorization': FAST2SMS_API_KEY,  # Yahan sirf apni API Key dalein
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        res = requests.post(url, data=payload, headers=headers)
        print(f"✅ SMS SENT! Response: {res.text}")
    except Exception as e:
        print(f"❌ SMS ERROR: {e}")