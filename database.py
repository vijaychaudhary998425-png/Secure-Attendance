import sqlite3
from datetime import datetime

DB_NAME = "secureattend_web.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            subject TEXT,
            date TEXT,
            in_time TEXT,
            out_time TEXT,
            total_time TEXT,
            status TEXT,
            UNIQUE(student_name, date, subject)
        )
    ''')
    conn.commit()
    conn.close()

def log_attendance(student_name, subject, status="PRESENT"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%I:%M:%S %p")

    cursor.execute('''
        SELECT id, in_time FROM attendance 
        WHERE student_name = ? AND date = ? AND subject = ?
    ''', (student_name, today, subject))
    
    row = cursor.fetchone()
    if row is None:
        # Initial In-Time Entry
        cursor.execute('''
            INSERT INTO attendance (student_name, subject, date, in_time, out_time, total_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (student_name, subject, today, current_time, current_time, "0 sec", status))
    else:
        # Update Out-Time and Calculate Total Duration
        in_time_str = row[1]
        fmt = "%I:%M:%S %p"
        try:
            t_in = datetime.strptime(in_time_str, fmt)
            t_out = datetime.strptime(current_time, fmt)
            diff_sec = int((t_out - t_in).total_seconds())
            
            if diff_sec < 60:
                dur_str = f"{diff_sec} sec"
            else:
                mins = diff_sec // 60
                hrs = mins // 60
                rem_mins = mins % 60
                if hrs > 0:
                    dur_str = f"{hrs}h {rem_mins}m"
                else:
                    dur_str = f"{mins} min"
        except Exception:
            dur_str = "0 sec"

        cursor.execute('''
            UPDATE attendance 
            SET out_time = ?, total_time = ? 
            WHERE id = ?
        ''', (current_time, dur_str, row[0]))

    conn.commit()
    conn.close()

def get_recent_logs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute('''
        SELECT student_name, in_time, out_time, total_time, status, subject 
        FROM attendance 
        WHERE date = ? 
        ORDER BY id DESC
    ''', (today,))
    logs = cursor.fetchall()
    conn.close()
    return logs