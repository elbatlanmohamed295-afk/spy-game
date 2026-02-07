import os
import random
import time
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'el_3watly_secret_key_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- قاعدة بيانات اللعبة ---
GAME_DATA = {
    "أماكن 🌍": ["القهوة", "القسم", "الساحل", "الأهرامات", "لجنة امتحان", "فرح شعبي", "المترو", "الجيم", "المطار", "الحلاق"],
    "أكلات 🥘": ["كشري", "محشي", "فسيخ", "حواوشي", "كوارع", "اندومي", "ملوخية", "شاورما"],
    "أفلام ومسلسلات 🎬": ["الكيف", "الجزيرة", "لن أعيش في جلباب أبي", "مافيا", "غبي منه فيه"],
    "أشياء في البيت 🏠": ["الثلاجة", "الغسالة", "الريموت", "الشبشب", "الشاحن"]
}

PUNISHMENTS = ["ارقص بلدي 💃", "قلد صوت فرخة 🐔", "اعمل مذيع كورة 🎤", "غني أغنية حزينة 🐥", "10 ضغط حالاً 💪", "اعترف بحاجة محرجة 🙈"]

# --- إدارة الغرف (State Management) ---
class GameRoom:
    def __init__(self):
        self.players = {}  # {sid: {name, img, score, role}}
        self.spy_sid = None
        self.location = None
        self.category = None
        self.start_time = None
        self.votes = {}  # {voter_sid: target_sid}
        self.state = "lobby" # lobby, playing, voting

rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

# --- Socket Events ---

@socketio.on('join')
def on_join(data):
    username = data.get('username')
    room_code = data.get('room')
    img = data.get('userImg')
    
    if not username or not room_code: return

    join_room(room_code)
    
    if room_code not in rooms:
        rooms[room_code] = GameRoom()
    
    room = rooms[room_code]
    
    # إضافة اللاعب
    room.players[request.sid] = {
        'name': username,
        'img': img,
        'score': 0,
        'role': 'human'
    }
    
    emit_room_update(room_code)

@socketio.on('disconnect')
def on_disconnect():
    for room_code, room in rooms.items():
        if request.sid in room.players:
            del room.players[request.sid]
            # إذا الغرفة فضيت نحذفها
            if not room.players:
                del rooms[room_code]
            else:
                emit_room_update(room_code)
            break

@socketio.on('start_game')
def on_start(data):
    room_code = data['room']
    category = data.get('category', 'أماكن 🌍')
    timer_duration = int(data.get('timer', 300)) # بالثواني

    if room_code in rooms:
        room = rooms[room_code]
        if len(room.players) < 3:
            emit('error_msg', {'msg': 'محتاجين 3 لاعبين على الأقل يا كابتن!'}, to=request.sid)
            return

        # إعداد اللعبة
        room.state = "playing"
        room.category = category
        room.location = random.choice(GAME_DATA[category])
        room.votes = {}
        
        # اختيار البرص
        player_sids = list(room.players.keys())
        room.spy_sid = random.choice(player_sids)
        
        # إرسال البيانات للاعبين (كل واحد حسب دوره)
        for sid in player_sids:
            role = 'spy' if sid == room.spy_sid else 'human'
            room.players[sid]['role'] = role
            
            payload = {
                'role': role,
                'category': category,
                'location': room.location if role == 'human' else "???",
                'endTime': time.time() + timer_duration
            }
            emit('game_started', payload, room=sid)

@socketio.on('vote_player')
def on_vote(data):
    room_code = data['room']
    target_sid = data['targetSid']
    
    if room_code in rooms:
        room = rooms[room_code]
        room.votes[request.sid] = target_sid
        
        # التحقق إذا الكل صوت (ماعدا واحد مثلاً أو الأغلبية)
        total_players = len(room.players)
        total_votes = len(room.votes)
        
        emit('vote_update', {'votes': total_votes, 'total': total_players}, to=room_code)

@socketio.on('reveal_result')
def on_reveal(data):
    room_code = data['room']
    if room_code in rooms:
        room = rooms[room_code]
        
        # حساب التصويت
        vote_counts = {}
        for target in room.votes.values():
            vote_counts[target] = vote_counts.get(target, 0) + 1
            
        # أكثر شخص تم التصويت ضده
        if vote_counts:
            victim_sid = max(vote_counts, key=vote_counts.get)
            victim_name = room.players[victim_sid]['name']
            is_spy_caught = (victim_sid == room.spy_sid)
        else:
            victim_name = "لا أحد"
            is_spy_caught = False

        spy_name = room.players[room.spy_sid]['name']
        punishment = random.choice(PUNISHMENTS)
        
        emit('game_over', {
            'spyName': spy_name,
            'victimName': victim_name,
            'spyCaught': is_spy_caught,
            'location': room.location,
            'punishment': punishment
        }, to=room_code)
        
        room.state = "lobby"

def emit_room_update(room_code):
    if room_code in rooms:
        players_list = [
            {'sid': sid, 'name': p['name'], 'img': p['img'], 'isHost': i==0} 
            for i, (sid, p) in enumerate(rooms[room_code].players.items())
        ]
        emit('update_player_list', {'players': players_list}, to=room_code)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)


