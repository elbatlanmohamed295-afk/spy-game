from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, join_room, emit
import random
import string
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultimate_pro_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- قاعدة البيانات ---
GAME_DATA = {
    "أماكن عامة": ["المطار", "المستشفى", "الجامعة", "المترو", "المول", "الفندق"],
    "أماكن ترفيه": ["السينما", "الملاهي", "القهوة", "الجيم", "الشاطئ", "السيرك"],
    "أماكن عمل": ["البنك", "الشركة", "موقع بناء", "قسم الشرطة", "المطعم", "استوديو"]
}
ALL_LOCATIONS = [loc for cat in GAME_DATA.values() for loc in cat]

AI_PROMPTS = [
    "يا {p1}، اسأل {p2} عن ريحة المكان ده.",
    "يا {p1}، لو روحت المكان ده تلبس إيه؟ اسأل {p2}.",
    "يا {p1}، إيه أغرب حاجة شفتها في المكان ده؟ اسأل {p2}.",
    "يا {p1}، المكان ده ينفع للأطفال؟ اسأل {p2}.",
    "يا {p1}، بنروح المكان ده الصبح ولا بليل؟ وجه السؤال لـ {p2}.",
    "يا {p1}، شك في حد واسأله سؤال مباشر!"
]

# --- تخزين الغرف ---
# rooms[code] = { 
#   'host': uid, 
#   'players': {uid: {name, sid, role}}, 
#   'state': 'lobby',
#   'chat_history': []  <-- الجديد: حفظ الشات
# }
rooms = {}

# مسار الصور (يقرأ من المجلد الرئيسي مباشرة)
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
    user_id = data.get('userId') or str(uuid.uuid4())
    code = data.get('code', '').upper()
    name = data.get('name')
    create_new = data.get('create', False)

    # 1. إنشاء غرفة
    if create_new:
        code = generate_code()
        rooms[code] = {
            'host': user_id,
            'players': {},
            'state': 'lobby',
            'game_info': {},
            'chat_history': [] # تهيئة سجل الشات
        }
    
    # 2. التحقق
    if code not in rooms:
        emit('error_msg', {'msg': 'الغرفة غير موجودة!'})
        return

    room = rooms[code]
    
    # 3. إدارة اللاعبين (دخول جديد أو إعادة اتصال)
    if user_id in room['players']:
        room['players'][user_id]['sid'] = request.sid
        if name: room['players'][user_id]['name'] = name
    else:
        if room['state'] != 'lobby':
            emit('error_msg', {'msg': 'اللعبة بدأت بالفعل!'})
            return
        if not name:
            emit('error_msg', {'msg': 'الاسم مطلوب'})
            return
        room['players'][user_id] = {'name': name, 'sid': request.sid, 'role': None}

    join_room(code)
    
    # إرسال بيانات النجاح
    emit('join_success', {
        'code': code, 
        'userId': user_id, 
        'is_host': (room['host'] == user_id),
        'state': room['state']
    })

    # إرسال سجل الشات القديم للاعب الجديد
    emit('chat_history', {'history': room['chat_history']})

    # تحديث الواجهة واستعادة الحالة لو اللعبة شغالة
    update_ui(code)
    if room['state'] == 'playing' and room['players'][user_id]['role']:
        restore_game_state(user_id, room)

def restore_game_state(uid, room):
    role = room['players'][uid]['role']
    loc = room['game_info']['location']
    emit('game_started', {
        'role': role,
        'location': loc if role == 'human' else "???",
        'all_locations': ALL_LOCATIONS,
        'reconnect': True
    }, room=room['players'][uid]['sid'])

@socketio.on('start_game')
def on_start(data):
    code = data['code']
    room = rooms.get(code)
    if not room: return

    uids = list(room['players'].keys())
    if len(uids) < 3:
        emit('error_msg', {'msg': 'مطلوب 3 لاعبين على الأقل!'})
        return

    # إعداد اللعبة
    cat = random.choice(list(GAME_DATA.keys()))
    loc = random.choice(GAME_DATA[cat])
    gecko_uid = random.choice(uids)
    
    room['state'] = 'playing'
    room['game_info'] = {'location': loc, 'gecko': gecko_uid}

    # إضافة رسالة نظام في الشات
    sys_msg = {'sender': 'System', 'msg': 'بدأت اللعبة! حاولوا كشف البرص 🦎', 'type': 'system'}
    room['chat_history'].append(sys_msg)
    emit('new_message', sys_msg, room=code)

    for uid in uids:
        role = 'gecko' if uid == gecko_uid else 'human'
        room['players'][uid]['role'] = role
        sid = room['players'][uid]['sid']
        emit('game_started', {
            'role': role,
            'location': loc if role == 'human' else "???",
            'all_locations': ALL_LOCATIONS
        }, room=sid)

    emit('start_timer', {'duration': 300}, room=code)

# --- نظام الشات الجديد ---
@socketio.on('send_message')
def on_chat(data):
    code = data['code']
    msg = data['msg']
    uid = data['userId']
    room = rooms.get(code)
    
    if room and uid in room['players']:
        sender_name = room['players'][uid]['name']
        message_data = {
            'sender': sender_name,
            'msg': msg,
            'type': 'player',
            'uid': uid
        }
        # حفظ الرسالة
        room['chat_history'].append(message_data)
        # إرسال للجميع
        emit('new_message', message_data, room=code)

# --- الذكاء الاصطناعي ---
@socketio.on('trigger_ai')
def on_ai(data):
    code = data['code']
    room = rooms.get(code)
    if not room or len(room['players']) < 2: return

    uids = list(room['players'].keys())
    p1, p2 = random.sample(uids, 2)
    p1_name = room['players'][p1]['name']
    p2_name = room['players'][p2]['name']

    prompt = random.choice(AI_PROMPTS).format(p1=p1_name, p2=p2_name)
    
    # إرسال كـ Notification وكـ رسالة شات
    ai_msg = {'sender': 'AI Bot 🤖', 'msg': prompt, 'type': 'ai'}
    room['chat_history'].append(ai_msg)
    
    emit('ai_message', {'msg': prompt}, room=code) # للفقاعة
    emit('new_message', ai_msg, room=code) # للشات

@socketio.on('request_punishment')
def on_punish(data):
    punishments = ["ارقص بلدي", "قلد صوت قرد", "اعترف بسر", "اعمل 10 ضغط"]
    img = random.randint(1, 7)
    emit('show_punishment', {'text': random.choice(punishments), 'image': f"{img}.jpeg"}, room=data['code'])

@socketio.on('reset_game')
def on_reset(data):
    code = data['code']
    if code in rooms:
        rooms[code]['state'] = 'lobby'
        rooms[code]['chat_history'].append({'sender': 'System', 'msg': 'تم إعادة اللعبة', 'type': 'system'})
        emit('return_to_lobby', {}, room=code)

def update_ui(code):
    if code in rooms:
        players = [{'name': p['name']} for p in rooms[code]['players'].values()]
        emit('update_players', {'players': players}, room=code)

if __name__ == '__main__':
    socketio.run(app, debug=True)
