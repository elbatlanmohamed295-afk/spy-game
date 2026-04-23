from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- الإعدادات والبيانات (مطابقة لطلبك: شهد كمال) ---
USER_DATA = {
    "name": "شهد كمال",
    "phone": "0551234567",
    "blood_type": "AB+",
    "diseases": ["test1", "test2", "test3", "test4"],
    "allergies": ["test1", "test2"],
    "medications": ["test1", "test2", "test3"],
    "emergency_contact": {"name": "شهد كمال", "relation": "friend", "phone": "0123456789"}
}

# --- نظام التنسيق CSS (مستوحى من الصور بالكامل) ---
CSS = """
:root {
    --primary: #8E4C4C; 
    --bg-light: #F8FAFC;
    --card-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}
body { 
    font-family: 'Segoe UI', Tahoma; background: var(--bg-light); 
    direction: rtl; margin: 0; padding: 0; color: #333;
}
.app-container { max-width: 500px; margin: auto; padding: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; }
.banner { 
    background: linear-gradient(135deg, #FFE4E1 0%, #FFDAB9 100%);
    padding: 25px; border-radius: 24px; display: flex; align-items: center; gap: 15px;
    margin-bottom: 25px; box-shadow: var(--card-shadow);
}
.avatar { width: 65px; height: 65px; background: var(--primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 30px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
.card { 
    background: white; padding: 20px; border-radius: 20px; 
    text-align: center; text-decoration: none; color: inherit;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); transition: 0.3s;
}
.card:active { transform: scale(0.95); }
.card i { font-size: 24px; color: var(--primary); margin-bottom: 10px; display: block; }
.input-group { background: white; padding: 15px; border-radius: 15px; margin-bottom: 10px; border: 1px solid #eee; }
.tag { background: #FEE2E2; color: #991B1B; padding: 6px 12px; border-radius: 12px; margin: 4px; display: inline-block; font-size: 14px; }
.btn-save { background: var(--primary); color: white; width: 100%; padding: 15px; border: none; border-radius: 15px; font-size: 18px; cursor: pointer; margin-top: 20px; }
.qr-container { background: white; padding: 30px; border-radius: 30px; text-align: center; box-shadow: var(--card-shadow); }
#location-status { font-size: 12px; color: #666; margin-top: 10px; }
"""

# --- القالب الرئيسي (Base Template) ---
BASE_HTML = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VitalLink - شهد كمال</title>
    <style>{{ css | safe }}</style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="app-container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# --- الصفحات ---
HOME_HTML = """
{% extends "base" %}
{% block content %}
<div class="header">
    <h2>VitalLink Home</h2>
    <div><i class="fas fa-moon"></i> <i class="fas fa-globe" style="margin-right:10px;"></i></div>
</div>
<div class="banner">
    <div class="avatar"><i class="fas fa-user"></i></div>
    <div>
        <h3 style="margin:0;">مرحباً {{ user.name }}</h3>
        <small>متصل بالخادم الخلفي (Render)</small>
    </div>
</div>
<h4>وصول سريع</h4>
<div class="grid">
    <a href="/profile" class="card"><i class="fas fa-user-circle"></i> الملف الشخصي</a>
    <a href="/medical" class="card"><i class="fas fa-file-medical"></i> المعلومات الطبية</a>
    <a href="/contacts" class="card"><i class="fas fa-address-book"></i> جهات الطوارئ</a>
    <a href="/qr" class="card"><i class="fas fa-qrcode"></i> رمز الطوارئ</a>
</div>
{% endblock %}
"""

QR_HTML = """
{% extends "base" %}
{% block content %}
<div class="header">
    <a href="/" style="color:black;"><i class="fas fa-arrow-right"></i></a>
    <h2>رمز الطوارئ</h2>
</div>
<div class="qr-container">
    <p><i class="fas fa-info-circle"></i> اعرض هذا الرمز في حالات الطوارئ.</p>
    <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={{ request.url_root }}emergency" alt="QR Code">
    <div style="background:#f0f0f0; padding:10px; border-radius:10px; margin-top:20px; word-break:break-all; font-size:12px;">
        {{ request.url_root }}emergency
    </div>
    <div id="location-status">جاري فحص حالة نظام التتبع...</div>
</div>
{% endblock %}
"""

EMERGENCY_VIEW = """
{% extends "base" %}
{% block content %}
<div style="text-align:center; color:white; background:red; padding:15px; border-radius:15px;">
    <h2>حالة طوارئ نشطة!</h2>
</div>
<div class="card" style="margin-top:20px; text-align:right;">
    <h3>بيانات المصاب: {{ user.name }}</h3>
    <p><b>فصيلة الدم:</b> <span class="tag">{{ user.blood_type }}</span></p>
    <p><b>الأمراض:</b> {% for d in user.diseases %}<span class="tag">{{ d }}</span>{% endfor %}</p>
</div>
<script>
    // أول ما الكود يتفتح، يبعت الموقع فوراً للسيرفر
    navigator.geolocation.getCurrentPosition(pos => {
        fetch('/log_location', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({lat: pos.coords.latitude, lng: pos.coords.longitude})
        });
    });
</script>
{% endblock %}
"""

# --- الروابط (Routes) ---
@app.route('/')
def home():
    return render_template_string(BASE_HTML + HOME_HTML, css=CSS, user=USER_DATA)

@app.route('/profile')
def profile():
    return render_template_string(BASE_HTML + """
    {% extends "base" %}
    {% block content %}
    <div class="header"><a href="/" style="color:black;"><i class="fas fa-arrow-right"></i></a><h2>الملف الشخصي</h2></div>
    <div class="card"><div class="avatar" style="margin:auto;"><i class="fas fa-camera"></i></div></div>
    <div class="input-group"><label>الاسم</label><br><b>{{ user.name }}</b></div>
    <div class="input-group"><label>رقم الموبايل</label><br><b>{{ user.phone }}</b></div>
    <button class="btn-save">حفظ الملف الشخصي</button>
    {% endblock %}
    """, css=CSS, user=USER_DATA)

@app.route('/medical')
def medical():
    return render_template_string(BASE_HTML + """
    {% extends "base" %}
    {% block content %}
    <div class="header"><a href="/" style="color:black;"><i class="fas fa-arrow-right"></i></a><h2>المعلومات الطبية</h2></div>
    <div class="card" style="text-align:right;">
        <h4>فصيلة الدم</h4><span class="tag">{{ user.blood_type }}</span>
        <hr><h4>الأمراض</h4>{% for d in user.diseases %}<span class="tag">{{ d }}</span>{% endfor %}
        <hr><h4>الأدوية</h4>{% for m in user.medications %}<span class="tag">{{ m }}</span>{% endfor %}
    </div>
    {% endblock %}
    """, css=CSS, user=USER_DATA)

@app.route('/qr')
def qr_page():
    return render_template_string(BASE_HTML + QR_HTML, css=CSS)

@app.route('/emergency')
def emergency():
    return render_template_string(BASE_HTML + EMERGENCY_VIEW, css=CSS, user=USER_DATA)

@app.route('/log_location', methods=['POST'])
def log_location():
    data = request.json
    print(f"ALERT: QR Scanned at Lat: {data['lat']}, Lng: {data['lng']}")
    return jsonify({"status": "received"})

@app.route('/base')
def base(): return render_template_string(BASE_HTML, css=CSS)

if __name__ == '__main__':
    app.run(debug=True)
