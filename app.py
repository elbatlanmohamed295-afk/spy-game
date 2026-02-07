from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, join_room, leave_room, emit
import random
import string
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ai_game_secret_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- قاعدة البيانات ---
GAME_DATA = {
    "أماكن عامة": ["المطار", "المستشفى", "الجامعة", "المترو", "المول", "الفندق"],
    "أماكن ترفيه": ["السينما", "الملاهي", "القهوة", "الجيم", "الشاطئ", "السيرك"],
    "أماكن عمل": ["البنك", "الشركة", "موقع بناء", "قسم الشرطة", "المطعم"]
}
ALL_LOCATIONS = [loc for cat in GAME_DATA.values() for loc in cat]

# --- ذكاء اصطناعي (قوالب أسئلة) ---
AI_PROMPTS = [
    "يا {p1}، اسأل {p2} عن ريحة المكان ده.",
    "يا {p1}، لو روحت المكان ده تلبس إيه؟ اسأل {p2}.",
    "يا {p1}، اسأل {p2} إيه أسوأ حاجة ممكن تحصل في المكان ده؟",
    "يا {p1}، هل المكان ده غالي ولا رخيص؟ اسأل {p2}.",
    "يا {p1}، اسأل {p2} بنروح المكان ده الصبح ولا بليل؟",
    "يا {p1}، اطلب من {p2} يوصف المكان بكلمة واحدة.",
    "يا {p1}، شك في حد واسأله سؤال مباشر!"
]

# --- التخزين ---
# rooms[code] = { 'host': uid, 'players': {uid: {name, score, role, sid}}, 'state': ... }
rooms = {}

# مسار الصور (للملفات التي بجانب الكود)
@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory('.', filename)

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

@app.route('/')
def index():
    return render_template('index.html')

# --- Socket Events ---

@socketio.on('join_game')
def on_join(data):
    # نستقبل الـ UID من المتصفح (لو مش موجود نكريت واحد جديد)
    user_id = data.get('userId') or str(uuid.uuid4())
    code = data.get('code', '').upper()
    name = data.get('name')
    create_new = data.get('create', False)

    # 1. إنشاء غرفة جديدة
    if create_new:
        code = generate_code()
        rooms[code] = {
            'host': user_id,
            'players': {},
            'state': 'lobby',
            'game_info': {}
        }
    
    # 2. التحقق من وجود الغرفة
    if code not in rooms:
        emit('error_msg', {'msg': 'الغرفة غير موجودة أو انتهت'})
        return

    room = rooms[code]
    
    # 3. منطق إعادة الاتصال (Reconnection) أو دخول جديد
    if user_id in room['players']:
        # اللاعب موجود بالفعل -> تحديث الـ Socket ID فقط
        room['players'][user_id]['sid'] = request.sid
        # لو الاسم اتغير نحدثه
        if name: room['players'][user_id]['name'] = name
        print(f"Reconnection: {room['players'][user_id]['name']}")
    else:
        # لاعب جديد
        if room['state'] != 'lobby':
            emit('error_msg', {'msg': 'اللعبة شغالة، مقدرش أدخلك دلوقتي!'})
            return
        if not name:
            emit('error_msg', {'msg': 'لازم تكتب اسمك'})
            return
            
        room['players'][user_id] = {'name': name, 'score': 0, 'role': None, 'sid': request.sid}

    join_room(code)
    
    # إرسال بيانات النجاح
    is_host = (room['host'] == user_id)
    emit('join_success', {
        'code': code, 
        'userId': user_id, 
        'is_host': is_host,
        'state': room['state']
    })

    # لو اللعبة شغالة واللاعب رجع، نرجعله دوره
    if room['state'] == 'playing' and room['players'][user_id]['role']:
        p_data = room['players'][user_id]
        loc = room['game_info']['location']
        emit('game_started', {
            'role': p_data['role'],
            'location': loc if p_data['role'] == 'human' else "???",
            'all_locations': ALL_LOCATIONS,
            'reconnect': True # علامة إنه إعادة اتصال
        })

    update_ui(code)

@socketio.on('start_game')
def on_start(data):
    code = data['code']
    room = rooms.get(code)
    if not room: return

    # إعداد اللعبة
    cat = random.choice(list(GAME_DATA.keys()))
    loc = random.choice(GAME_DATA[cat])
    uids = list(room['players'].keys())
    
    if len(uids) < 3:
        emit('error_msg', {'msg': 'محتاجين 3 لاعبين على الأقل!'})
        return

    gecko_uid = random.choice(uids)
    room['state'] = 'playing'
    room['game_info'] = {'location': loc, 'gecko': gecko_uid}

    for uid in uids:
        role = 'gecko' if uid == gecko_uid else 'human'
        room['players'][uid]['role'] = role
        # إرسال لكل لاعب
        sid = room['players'][uid]['sid']
        emit('game_started', {
            'role': role,
            'location': loc if role == 'human' else "???",
            'all_locations': ALL_LOCATIONS
        }, room=sid)

    emit('start_timer', {'duration': 300}, room=code)

# --- الذكاء الاصطناعي (الموجه) ---
@socketio.on('trigger_ai')
def on_trigger_ai(data):
    code = data['code']
    room = rooms.get(code)
    if not room or room['state'] != 'playing': return

    uids = list(room['players'].keys())
    if len(uids) < 2: return

    # اختيار لاعبين عشوائيين
    p1_uid, p2_uid = random.sample(uids, 2)
    p1_name = room['players'][p1_uid]['name']
    p2_name = room['players'][p2_uid]['name']

    # اختيار قالب سؤال وتعبئته
    prompt_template = random.choice(AI_PROMPTS)
    ai_msg = prompt_template.format(p1=p1_name, p2=p2_name)

    emit('ai_message', {'msg': ai_msg}, room=code)

@socketio.on('request_punishment')
def on_punish(data):
    # اختيار صورة وعقاب
    punishments = ["ارقص", "غني", "اعترف بسر", "اعمل ضغط"]
    img = random.randint(1, 7)
    emit('show_punishment', {'text': random.choice(punishments), 'image': f"{img}.jpeg"}, room=data['code'])

@socketio.on('reset_game')
def on_reset(data):
    code = data['code']
    if code in rooms:
        rooms[code]['state'] = 'lobby'
        for p in rooms[code]['players'].values():
            p['role'] = None
        emit('return_to_lobby', {}, room=code)

def update_ui(code):
    if code not in rooms: return
    players_list = [{'name': p['name'], 'score': p['score']} for p in rooms[code]['players'].values()]
    emit('update_players', {'players': players_list}, room=code)

if __name__ == '__main__':
    socketio.run(app, debug=True)

