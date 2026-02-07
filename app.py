from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, join_room, emit
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultimate_secret_key_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- قاعدة البيانات الموسعة ---
GAME_DATA = {
    "أماكن عامة": ["المطار", "المستشفى", "الجامعة", "محطة المترو", "المكتبة العامة", "السوبر ماركت"],
    "أماكن ترفيه": ["السينما", "الملاهي", "الكافيه", "الجيم (GYM)", "الشاطئ", "حديقة الحيوان"],
    "أماكن خاصة": ["قسم الشرطة", "محطة الفضاء", "السفارة", "البنك", "استوديو تصوير", "غواصة حربية"]
}

# تجميع كل الأماكن في قائمة واحدة للمساعدة
ALL_LOCATIONS = [loc for cat in GAME_DATA.values() for loc in cat]

PUNISHMENTS = [
    "قل نكتة بايخة ولو محدش ضحك تعيد",
    "ارقص بلدي لمدة دقيقة",
    "اعمل 10 ضغط حالاً",
    "اتصل بآخر رقم وقوله 'أنا بحبك'",
    "قلد صوت حيوان يختاره الجمهور",
    "اعترف بآخر كذبة كذبتها",
    "اشرب كوباية مية كاملة مرة واحدة"
]

rooms = {}

# --- دالة سحرية لقراءة الصور من المجلد الرئيسي ---
@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory('.', filename)

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

@app.route('/')
def index():
    return render_template('index.html')

# --- Socket Events ---

@app.route('/ping') # للتأكد أن السيرفر يعمل
def ping(): return "Pong"

@socketio.on('create_room')
def on_create(data):
    code = generate_code()
    name = data['name']
    rooms[code] = {
        'host': request.sid, # تسجيل من هو الأدمن
        'players': {request.sid: {'name': name, 'score': 0}},
        'state': 'lobby',
        'game_info': {}
    }
    join_room(code)
    emit('room_created', {'code': code, 'is_host': True})
    emit('update_ui', {'players': get_players_list(code), 'is_host': True}, room=code)

@socketio.on('join_room')
def on_join(data):
    code = data['code'].upper()
    name = data['name']
    
    if code not in rooms:
        emit('error_msg', {'msg': 'الغرفة غير موجودة!'})
        return

    if len(rooms[code]['players']) >= 10:
        emit('error_msg', {'msg': 'الغرفة ممتلئة!'})
        return

    join_room(code)
    rooms[code]['players'][request.sid] = {'name': name, 'score': 0}
    
    # إشعار الجميع
    is_host = (rooms[code]['host'] == request.sid)
    emit('join_success', {'code': code, 'is_host': is_host})
    emit('update_ui', {'players': get_players_list(code)}, room=code)

@socketio.on('start_game')
def on_start(data):
    code = data['code']
    room = rooms.get(code)
    
    # تحقق أمني: هل المرسل هو الأدمن؟
    if room['host'] != request.sid:
        return 

    if len(room['players']) < 3:
        emit('error_msg', {'msg': 'تحتاج 3 لاعبين على الأقل!'})
        return

    # إعداد اللعبة
    category = random.choice(list(GAME_DATA.keys()))
    location = random.choice(GAME_DATA[category])
    all_sids = list(room['players'].keys())
    gecko_sid = random.choice(all_sids)
    
    room['state'] = 'playing'
    room['game_info'] = {'location': location, 'gecko': gecko_sid}

    # إرسال البيانات لكل لاعب (Private Info)
    for sid in all_sids:
        role = 'gecko' if sid == gecko_sid else 'human'
        emit('game_started', {
            'role': role,
            'location': location if role == 'human' else "???",
            'category': category,
            'all_locations': ALL_LOCATIONS # قائمة المساعدة
        }, room=sid)

    # تشغيل التايمر للكل
    emit('start_timer', {'duration': 300}, room=code)

@socketio.on('request_punishment')
def on_punish(data):
    code = data['code']
    p_text = random.choice(PUNISHMENTS)
    p_img = random.randint(1, 7) # صور من 1.jpeg لـ 7.jpeg
    emit('show_punishment', {'text': p_text, 'image': f"{p_img}.jpeg"}, room=code)

@socketio.on('reset_game')
def on_reset(data):
    code = data['code']
    if rooms.get(code) and rooms[code]['host'] == request.sid:
        rooms[code]['state'] = 'lobby'
        emit('return_to_lobby', {}, room=code)

def get_players_list(code):
    return [{'name': p['name'], 'id': sid} for sid, p in rooms[code]['players'].items()]

if __name__ == '__main__':
    socketio.run(app, debug=True)
