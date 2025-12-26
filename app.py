import os
import random
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room

# 1. إعداد التطبيق (رجعناه للوضع الطبيعي عشان يشوف مجلد templates)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'el_3watly_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# 2. كود سحري: عشان الصور تظهر من المجلد الرئيسي
@app.route('/<path:filename>')
def serve_file(filename):
    # السيرفر هيدور على الصور في المجلد الرئيسي (.)
    return send_from_directory(os.getcwd(), filename)

# 3. الصفحة الرئيسية
@app.route('/')
def index():
    return render_template('index.html')

# --- باقي كود اللعبة (المنطق واللعب) ---

PUNISHMENTS = [
    "ارقص بلدي 💃", "قلد صوت فرخة 🐔", "اعمل مذيع كورة 🎤", 
    "غني فويس نوت 🐥", "مشية عسكرية 💂‍♂️", "قصيدة في الكشري 🍲",
    "10 ضغط 💪", "قلد حد فينا 🎭", "موقف محرج 🚌", "سف على نفسك 😂"
]

GAME_DATA = {
    "أماكن 🌍": ["القهوة", "القسم", "موقف الميكروباص", "الساحل", "الأهرامات", "مول العرب", "لجنة امتحان", "فرح شعبي", "عربية كبدة", "المترو"],
    "أكلات 🥘": ["كشري", "محشي", "بشاميل", "فسيخ", "فول", "طعمية", "حواوشي", "كوارع", "اندومي"],
    "مشاهير 🌟": ["محمد رمضان", "عادل إمام", "أحمد السقا", "ويجز", "حسن شاكوش", "مو صلاح", "ياسمين صبري", "بيج رامي"],
    "ملابس 👕": ["فانلة حمالات", "شبشب زنوبة", "ترنج", "بدلة فرح", "كلسون", "شراب مخروم", "جلابية"],
    "أشياء منزلية 🏠": ["النيش", "كيس الأكياس", "ريموت بلاسبر", "طاسة سوداء", "شبشب حمام", "راوتر", "مشترك بايظ"]
}

rooms = {}

@socketio.on('join')
def on_join(data):
    username = data.get('username')
    room = data.get('room')
    userImg = data.get('userImg', '')
    sid = request.sid
    if not username or not room: return
    
    join_room(room)
    if room not in rooms: rooms[room] = {'players': [], 'current_spy': None}
    
    # تحديث اللاعب
    rooms[room]['players'] = [p for p in rooms[room]['players'] if p['name'] != username]
    rooms[room]['players'].append({'sid': sid, 'name': username, 'img': userImg})
    
    emit_player_list(room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    for room in list(rooms.keys()):
        if room in rooms:
            rooms[room]['players'] = [p for p in rooms[room]['players'] if p['sid'] != sid]
            emit_player_list(room)

def emit_player_list(room):
    if room in rooms:
        players_data = [{'name': p['name'], 'img': p.get('img', '')} for p in rooms[room]['players']]
        emit('update_player_list', {'players': players_data, 'count': len(players_data)}, to=room)

@socketio.on('start_game')
def on_start(data):
    room = data['room']
    category = data.get('category', 'أماكن 🌍')
    
    if room in rooms:
        players = rooms[room]['players']
        if len(players) < 3:
            emit('error_msg', 'لازم 3 لاعبين!', to=request.sid)
            return

        items_list = GAME_DATA.get(category, GAME_DATA['أماكن 🌍'])
        chosen_item = random.choice(items_list)
        spy_player = random.choice(players)
        
        rooms[room]['current_spy'] = spy_player['name']
        
        for player in players:
            info = {'category': category, 'is_spy': (player == spy_player)}
            if player == spy_player:
                info['role'] = 'الجاسوس 🦎'; info['item'] = '؟؟؟؟؟'
            else:
                info['role'] = 'مواطن 👷'; info['item'] = chosen_item
            
            emit('game_started', info, to=player['sid'])

@socketio.on('reveal_spy')
def on_reveal(data):
    room = data['room']
    if room in rooms and rooms[room].get('current_spy'):
        emit('show_result', {
            'spy': rooms[room]['current_spy'], 
            'punishment': random.choice(PUNISHMENTS)
        }, to=room)

@socketio.on('reset_game')
def on_reset(data):
    emit('reset_view', to=data['room'])

if __name__ == '__main__':
    socketio.run(app)


