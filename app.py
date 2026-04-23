import os
import sqlite3
import traceback
from flask import Flask, render_template_string, request, jsonify, g

app = Flask(__name__)
DATABASE = 'vitallink.db'

# ==========================================
# --- إعداد الداتا بيز المدمجة (بدون مكتبات خارجية) ---
# ==========================================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # عشان نقرأ البيانات كأنها قاموس
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- إنشاء الداتا بيز وتعبئة البيانات مع أول تشغيل ---
@app.before_request
def setup_database():
    if getattr(app, '_db_initialized', False):
        return
    try:
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, phone TEXT, blood_type TEXT, diseases TEXT, allergies TEXT
            )
        ''')
        cur = db.execute('SELECT COUNT(*) FROM user')
        if cur.fetchone()[0] == 0:
            db.execute('''
                INSERT INTO user (name, phone, blood_type, diseases, allergies)
                VALUES (?, ?, ?, ?, ?)
            ''', ("شهد كمال", "0551234567", "AB+", "السكري, ضغط الدم", "البنسلين, الفراولة"))
            db.commit()
        app._db_initialized = True
    except Exception as e:
        print("Database error:", e)

# ==========================================
# --- صائد الأخطاء ---
# ==========================================
@app.errorhandler(Exception)
def handle_exception(e):
    error_details = traceback.format_exc()
    return f"""
    <div style="direction: ltr; text-align: left; background: #ffebee; color: #b71c1c; padding: 20px; font-family: monospace;">
        <h2>🚨 حصل خطأ! (Error 500)</h2>
        <p><b>السبب:</b> {str(e)}</p>
        <hr><pre>{error_details}</pre>
    </div>
    """, 500

# ==========================================
# --- التصميم والقوالب (CSS & HTML) ---
# ==========================================

CSS = """
:root { --primary: #8E4C4C; --bg: #F4F7FA; --card: #FFFFFF; }
body { font-family: 'Segoe UI', Tahoma; background: var(--bg); direction: rtl; margin: 0; padding: 20px; color: #333; }
.app-container { max-width: 450px; margin: 0 auto; }
.card { background: var(--card); border-radius: 20px; padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
.banner { background: linear-gradient(90deg, #FFE4E1, #FFDAB9); padding: 20px; border-radius: 20px; display: flex; align-items: center; gap: 15px; }
.avatar { width: 60px; height: 60px; background: var(--primary); border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; font-size: 24px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
.grid-item { background: white; padding: 20px; border-radius: 15px; text-align: center; text-decoration: none; color: #333; box-shadow: 0 2px 4px rgba(0,0,0,0.05); display: block; }
.grid-item i { font-size: 24px; color: var(--primary); margin-bottom: 10px; }
.tag { background: #FFEBEE; color: #D32F2F; padding: 5px 12px; border-radius: 15px; display: inline-block; margin: 5px 0; font-size: 14px; }
.form-input { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; font-family: inherit; }
.btn { background: var(--primary); color: white; border: none; padding: 15px; border-radius: 12px; width: 100%; font-size: 16px; cursor: pointer; margin-top: 15px; }
.header-nav { display: flex; align-items: center; gap: 15px; margin-bottom: 20px; font-weight: bold; font-size: 18px; }
.header-nav a { color: #333; text-decoration: none; font-size: 20px; }
"""

HEADER_HTML = f"""<!DOCTYPE html><html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>VitalLink</title><style>{CSS}</style><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"></head><body><div class="app-container">"""
FOOTER_HTML = """</div></body></html>"""

INDEX_HTML = HEADER_HTML + """
<div class="banner">
    <div class="avatar"><i class="fas fa-user"></i></div>
    <div>
        <h3 style="margin: 0;">مرحباً {{ user['name'] if user else 'زائر' }}</h3>
        <small>متصل بالنظام</small>
    </div>
</div>
<h3 style="margin-top: 20px;">وصول سريع</h3>
<div class="grid">
    <a href="/profile" class="grid-item"><i class="fas fa-user-circle"></i><br>الملف الشخصي</a>
    <a href="/medical" class="grid-item"><i class="fas fa-briefcase-medical"></i><br>البيانات الطبية</a>
    <a href="/qr" class="grid-item"><i class="fas fa-qrcode"></i><br>رمز الطوارئ</a>
</div>
""" + FOOTER_HTML

PROFILE_HTML = HEADER_HTML + """
<div class="header-nav"><a href="/"><i class="fas fa-arrow-right"></i></a><span>الملف الشخصي</span></div>
<div class="card">
    <div style="text-align: center; margin-bottom: 20px;"><div class="avatar" style="margin: 0 auto;"><i class="fas fa-camera"></i></div></div>
    <form method="POST">
        <label>الاسم</label>
        <input type="text" name="name" class="form-input" value="{{ user['name'] if user else '' }}">
        <label style="display: block; margin-top: 15px;">رقم الهاتف</label>
        <input type="text" name="phone" class="form-input" value="{{ user['phone'] if user else '' }}">
        <button type="submit" class="btn">حفظ الملف الشخصي</button>
    </form>
</div>
""" + FOOTER_HTML

MEDICAL_HTML = HEADER_HTML + """
<div class="header-nav"><a href="/"><i class="fas fa-arrow-right"></i></a><span>المعلومات الطبية</span></div>
<div class="card">
    <h4>فصيلة الدم</h4><span class="tag" style="font-size: 18px; background: #ffe4e1;">{{ user['blood_type'] if user else 'غير محدد' }}</span>
    <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">
    <h4>الأمراض المزمنة</h4>
    {% for disease in diseases %}<span class="tag"><i class="fas fa-times-circle"></i> {{ disease.strip() }}</span>{% endfor %}
    <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">
    <h4>الحساسية</h4>
    {% for allergy in allergies %}<span class="tag" style="background: #FFF3E0; color: #E65100;"><i class="fas fa-times-circle"></i> {{ allergy.strip() }}</span>{% endfor %}
</div>
""" + FOOTER_HTML

QR_HTML = HEADER_HTML + """
<div class="header-nav"><a href="/"><i class="fas fa-arrow-right"></i></a><span>رمز الطوارئ</span></div>
<div class="card" style="text-align: center;">
    <p><i class="fas fa-info-circle"></i> اعرض هذا الرمز في حالات الطوارئ.</p>
    {% if user %}
    <img src="https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={{ request.url_root }}emergency/{{ user['id'] }}" alt="QR Code" style="margin: 20px 0; border-radius: 10px; max-width: 100%;">
    <div style="background:#f0f0f0; padding:10px; border-radius:10px; margin-top:10px; word-break:break-all; font-size:12px; direction: ltr;">
        {{ request.url_root }}emergency/{{ user['id'] }}
    </div>
    {% else %}
    <p style="color:red;">لا يوجد مستخدم لاستخراج الرمز</p>
    {% endif %}
</div>
""" + FOOTER_HTML

EMERGENCY_HTML = HEADER_HTML + """
<div style="background: #d32f2f; color: white; padding: 15px; border-radius: 15px; text-align: center; margin-bottom: 20px;">
    <h2><i class="fas fa-ambulance"></i> حالة طوارئ طبية</h2>
</div>
<div class="card">
    <h3 style="color: var(--primary); text-align: center;">{{ user['name'] }}</h3>
    <p><b>فصيلة الدم:</b> <span class="tag" style="font-size: 16px;">{{ user['blood_type'] }}</span></p>
    <p><b>رقم الطوارئ:</b> <a href="tel:{{ user['phone'] }}" style="text-decoration: none; font-weight: bold; color: #d32f2f; direction: ltr; display: inline-block;">{{ user['phone'] }} <i class="fas fa-phone"></i></a></p>
    <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">
    <p><b>الأمراض المزمنة:</b></p>
    {% for disease in (user['diseases'].split(',') if user['diseases'] else []) %}
        <span class="tag">{{ disease.strip() }}</span>
    {% endfor %}
</div>

<script>
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
            fetch('/api/location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat: position.coords.latitude, lng: position.coords.longitude })
            });
        });
    }
</script>
""" + FOOTER_HTML

# ==========================================
# --- الروابط (Routes) ---
# ==========================================

@app.route('/')
def home():
    db = get_db()
    user = db.execute('SELECT * FROM user LIMIT 1').fetchone()
    return render_template_string(INDEX_HTML, user=user)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        db.execute('UPDATE user SET name = ?, phone = ? WHERE id = 1', (name, phone))
        db.commit()
    user = db.execute('SELECT * FROM user LIMIT 1').fetchone()
    return render_template_string(PROFILE_HTML, user=user)

@app.route('/medical')
def medical():
    db = get_db()
    user = db.execute('SELECT * FROM user LIMIT 1').fetchone()
    diseases_list = user['diseases'].split(',') if user and user['diseases'] else []
    allergies_list = user['allergies'].split(',') if user and user['allergies'] else []
    return render_template_string(MEDICAL_HTML, user=user, diseases=diseases_list, allergies=allergies_list)

@app.route('/qr')
def qr_page():
    db = get_db()
    user = db.execute('SELECT * FROM user LIMIT 1').fetchone()
    return render_template_string(QR_HTML, user=user)

@app.route('/emergency/<int:user_id>')
def emergency(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
    if user is None:
        return "<h2 style='text-align:center;'>مستخدم غير موجود</h2>", 404
    return render_template_string(EMERGENCY_HTML, user=user)

@app.route('/api/location', methods=['POST'])
def save_location():
    data = request.json
    print(f"🚨 ALERT! Scanned at Lat: {data['lat']}, Lng: {data['lng']}")
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)
