import os
import random
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'el_3watly_pro_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/<path:filename>')
def serve_file(filename):
    return send_from_directory(os.getcwd(), filename)

@app.route('/')
def index():
    return render_template('index.html')

PUNISHMENTS = ["ارقص بلدي 💃", "قلد صوت فرخة 🐔", "اعمل مذيع كورة 🎤", "غني فويس نوت 🐥", "10 ضغط 💪", "قلد حد فينا 🎭", "موقف محرج 🚌"]

GAME_DATA = {
    "أماكن 🌍": ["القهوة", "القسم", "الساحل", "الأهرامات", "لجنة امتحان", "فرح شعبي", "المترو"],
    "أكلات 🥘": ["كشري", "محشي", "فسيخ", "حواوشي", "كوارع", "اندومي"],
    "مشاهير 🌟": ["محمد رمضان", "عادل إمام", "ويجز", "مو صلاح", "بيج رامي"]
}

rooms = {}

@socketio.on('join')
def on_join(data):
    username, room, userImg = data.get('username'), data.get('room'), data.get('userImg', '')
    if not username or not room: return
    join_room(room)
    if room not in rooms: rooms[room] = {'players': [], 'spy': None, 'votes': set()}
    rooms[room]['players'] = [p for p in rooms[room]['players'] if p['name'] != username]
    rooms[room]['players'].append({'sid': request.sid, 'name': username, 'img': userImg})
    emit_player_list(room)

def emit_player_list(room):
    players_data = [{'name': p['name'], 'img': p.get('img', '')} for p in rooms[room]['players']]
    emit('update_player_list', {'players': players_data, 'count': len(players_data)}, to=room)

@socketio.on('send_shout')
def on_shout(data):
    emit('receive_shout', {'user': data['user'], 'msg': data['msg']}, to=data['room'])

@socketio.on('start_game')
def on_start(data):
    room = data['room']
    if room in rooms and len(rooms[room]['players']) >= 3:
        rooms[room]['votes'] = set()
        emit('reset_vote_ui', to=room)
        category = data.get('category', 'أماكن 🌍')
        item = random.choice(GAME_DATA[category])
        spy = random.choice(rooms[room]['players'])
        rooms[room]['spy'] = spy['name']
        for p in rooms[room]['players']:
            is_spy = (p == spy)
            emit('game_started', {'category': category, 'is_spy': is_spy, 'role': 'الجاسوس 🦎' if is_spy else 'مواطن 👷', 'item': '؟؟؟؟؟' if is_spy else item}, to=p['sid'])

@socketio.on('request_reveal')
def on_reveal(data):
    room, sid = data['room'], request.sid
    if room in rooms:
        rooms[room]['votes'].add(sid)
        if len(rooms[room]['votes']) >= len(rooms[room]['players']):
            emit('show_result', {'spy': rooms[room]['spy'], 'punishment': random.choice(PUNISHMENTS)}, to=room)
        else:
            emit('vote_update', {'current': len(rooms[room]['votes']), 'total': len(rooms[room]['players'])}, to=room)

@socketio.on('reset_game')
def on_reset(data):
    emit('reset_view', to=data['room'])

if __name__ == '__main__':
    socketio.run(app)


