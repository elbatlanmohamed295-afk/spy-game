from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random
import string
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_final_v3'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- بيانات اللعبة ---
GAME_DATA = {
    "أماكن عامة": ["المطار", "المستشفى", "الجامعة", "محطة المترو", "المول", "الفندق"],
    "أماكن ترفيه": ["السينما", "الملاهي", "القهوة", "الجيم", "الشاطئ", "السيرك"],
    "أماكن عمل": ["البنك", "الشركة", "موقع بناء", "قسم الشرطة", "المطعم", "استوديو"]
}
ALL_LOCATIONS = [loc for cat in GAME_DATA.values() for loc in cat]

AI_PROMPTS = [
    "يا {p1}، اسأل {p2} عن ريحة المكان ده.",
    "يا {p1}، لو روحت المكان ده تلبس إيه؟ اسأل {p2}.",
    "يا {p1}، إيه أغرب حاجة شفتها في المكان ده؟ اسأل {p2}.",
    "يا {p1}، بنروح المكان ده الصبح ولا بليل؟ وجه السؤال لـ {p2}.",
    "يا {p1}، شك في حد واسأله سؤال مباشر!"
]

# تخزين الغرف
rooms = {}

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

@app.route('/')
def index():
    return render_template('index.html')

# --- Socket Events ---

@socketio.on('join_game')
def on_join(data):
    user_id = data.get('userId') or str(uuid.uuid4())
    create_new = data.get('create', False)
    name = data.get('name')
    
    # 1. منطق الإنشاء أو الدخول
    if create_new:
        code = generate_code()
        while code in rooms: code = generate_code()
        
        rooms[code] = {
            'host': user_id,
            'players': {},
            'votes': {},
            'state': 'lobby',
            'game_info': {},
            'chat_history': []
        }
    else:
        raw_code = data.get('code')
        code = raw_code.upper() if raw_code else ''

    # 2. التحقق من الغرفة
    if code not in rooms:
        emit('error_msg', {'msg': 'الغرفة غير موجودة!'})
        return

    room = rooms[code]

    # 3. تسجيل اللاعب
    if user_id in room['players']:
        room['players'][user_id]['sid'] = request.sid
        if name: room['players'][user_id]['name'] = name
    else:
        if room['state'] != 'lobby':
            emit('error_msg', {'msg': 'اللعبة بدأت بالفعل!'})
            return
        if not name:
            emit('error_msg', {'msg': 'اكتب اسمك!'})
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

    # تحديث الواجهة والشات
    emit('chat_history', {'history': room['chat_history']})
    update_ui(code)

    # استعادة الحالة (لو عمل Refresh)
    if room['state'] == 'playing' and room['players'][user_id]['role']:
        restore_game(user_id, room)

def restore_game(uid, room):
    p = room['players'][uid]
    loc = room['game_info']['location']
    emit('game_started', {
        'role': p['role'],
        'location': loc if p['role'] == 'human' else "???",
        'all_locations': ALL_LOCATIONS,
        'reconnect': True
    }, room=p['sid'])

@socketio.on('start_game')
def on_start(data):
    code = data['code']
    room = rooms.get(code)
    if not room: return

    uids = list(room['players'].keys())
    if len(uids) < 3:
        emit('error_msg', {'msg': 'مطلوب 3 لاعبين على الأقل!'})
        return

    cat = random.choice(list(GAME_DATA.keys()))
    loc = random.choice(GAME_DATA[cat])
    gecko_uid = random.choice(uids)
    
    room['state'] = 'playing'
    room['votes'] = {}
    room['game_info'] = {'location': loc, 'gecko': gecko_uid}

    sys_msg = {'sender': 'System', 'msg': 'بدأت اللعبة! 🎮', 'type': 'system'}
    room['chat_history'].append(sys_msg)
    emit('new_message', sys_msg, room=code)

    for uid in uids:
        role = 'gecko' if uid == gecko_uid else 'human'
        room['players'][uid]['role'] = role
        emit('game_started', {
            'role': role,
            'location': loc if role == 'human' else "???",
            'all_locations': ALL_LOCATIONS
        }, room=room['players'][uid]['sid'])

    emit('start_timer', {'duration': 300}, room=code)

@socketio.on('submit_vote')
def on_vote(data):
    code = data['code']
    room = rooms.get(code)
    if room and room['state'] == 'playing':
        voter_id = data['userId']
        suspect_id = data['suspectId']
        
        # منع التصويت المكرر
        if voter_id in room['votes']: return

        room['votes'][voter_id] = suspect_id
        
        voter_name = room['players'][voter_id]['name']
        suspect_name = room['players'][suspect_id]['name']
        
        msg = {'sender': 'System', 'msg': f"🗳️ {voter_name} صوت ضد {suspect_name}", 'type': 'system'}
        room['chat_history'].append(msg)
        emit('new_message', msg, room=code)

        if len(room['votes']) == len(room['players']):
            finish_game(code)

def finish_game(code):
    room = rooms[code]
    votes = list(room['votes'].values())
    gecko_uid = room['game_info']['gecko']
    
    if not votes: return

    most_voted = max(set(votes), key=votes.count)
    gecko_name = room['players'][gecko_uid]['name']
    suspect_name = room['players'][most_voted]['name']
    
    winner = "Humans" if most_voted == gecko_uid else "Gecko"
    
    emit('game_over', {
        'winner': winner,
        'gecko_name': gecko_name,
        'suspect_name': suspect_name
    }, room=code)
    room['state'] = 'result'

# --- الشات والذكاء الاصطناعي ---
@socketio.on('send_message')
def on_chat(data):
    code = data.get('code')
    room = rooms.get(code)
    if room:
        name = room['players'][data['userId']]['name']
        msg_data = {'sender': name, 'msg': data['msg'], 'type': 'player', 'uid': data['userId']}
        room['chat_history'].append(msg_data)
        emit('new_message', msg_data, room=code)

@socketio.on('trigger_ai')
def on_ai(data):
    code = data['code']
    room = rooms.get(code)
    if room and len(room['players']) >= 2:
        try:
            uids = list(room['players'].keys())
            p1, p2 = random.sample(uids, 2)
            prompt = random.choice(AI_PROMPTS).format(
                p1=room['players'][p1]['name'], 
                p2=room['players'][p2]['name']
            )
            ai_msg = {'sender': 'AI Bot 🤖', 'msg': prompt, 'type': 'ai'}
            room['chat_history'].append(ai_msg)
            emit('ai_message', {'msg': prompt}, room=code)
            emit('new_message', ai_msg, room=code)
        except: pass

@socketio.on('request_punishment')
def on_punish(data):
    punishments = ["ارقص", "قلد قرد", "اعترف بسر", "اعمل ضغط", "غني بصوت عالي"]
    img = random.randint(1, 7)
    # لاحظ: نرسل اسم الملف فقط، والـ HTML يضيف المسار
    emit('show_punishment', {'text': random.choice(punishments), 'image': f"{img}.jpeg"}, room=data['code'])

@socketio.on('reset_game')
def on_reset(data):
    code = data['code']
    if code in rooms:
        rooms[code]['state'] = 'lobby'
        rooms[code]['votes'] = {}
        emit('return_to_lobby', {}, room=code)

def update_ui(code):
    if code in rooms:
        players = [{'name': p['name'], 'id': uid} for uid, p in rooms[code]['players'].items()]
        emit('update_players', {'players': players}, room=code)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)


