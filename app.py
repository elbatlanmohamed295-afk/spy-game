"""
لعبة UNO كاملة - ملف بايثون واحد شامل
تثبيت المتطلبات:
    pip install flask flask-socketio eventlet

تشغيل:
    python uno_game.py

ثم افتح: http://localhost:5000
"""

from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
import json
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'uno-secret-key-2024-final-edition'
# استخدام eventlet ضروري جداً لضمان سرعة اللعبة على Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# ========== منطق اللعبة ==========

COLORS = ['red', 'green', 'blue', 'yellow']
COLOR_AR = {'red': 'أحمر', 'green': 'أخضر', 'blue': 'أزرق', 'yellow': 'أصفر', 'wild': 'ملوّن'}
VALUES = ['0','1','2','3','4','5','6','7','8','9','skip','reverse','draw2']
WILD_CARDS = ['wild', 'wild4']

def make_deck():
    deck = []
    for color in COLORS:
        deck.append({'color': color, 'value': '0', 'id': f'{color}_0_a'})
        for value in VALUES[1:]:
            deck.append({'color': color, 'value': value, 'id': f'{color}_{value}_a'})
            deck.append({'color': color, 'value': value, 'id': f'{color}_{value}_b'})
    for _ in range(4):
        deck.append({'color': 'wild', 'value': 'wild', 'id': f'wild_{random.randint(10000,99999)}'})
        deck.append({'color': 'wild', 'value': 'wild4', 'id': f'wild4_{random.randint(10000,99999)}'})
    # ضمان معرفات فريدة
    seen = set()
    unique_deck = []
    for i, card in enumerate(deck):
        card['id'] = f"{card['color']}_{card['value']}_{i}"
        unique_deck.append(card)
    random.shuffle(unique_deck)
    return unique_deck

def card_playable(card, top_card, current_color):
    if card['color'] == 'wild':
        return True
    if card['color'] == current_color:
        return True
    if card['value'] == top_card['value']:
        return True
    return False

def card_label(card):
    val_map = {
        'skip': 'تخطي', 'reverse': 'عكس', 'draw2': '+2',
        'wild': 'ملوّن', 'wild4': 'ملوّن +4',
        '0':'0','1':'1','2':'2','3':'3','4':'4',
        '5':'5','6':'6','7':'7','8':'8','9':'9'
    }
    color = COLOR_AR.get(card['color'], card['color'])
    val = val_map.get(card['value'], card['value'])
    return f"{color} {val}"

# ========== إدارة الغرف ==========
rooms = {}

def create_room(host_name, max_players):
    code = ''.join(random.choices(string.digits, k=6))
    while code in rooms:
        code = ''.join(random.choices(string.digits, k=6))
    rooms[code] = {
        'code': code,
        'host': host_name,
        'max_players': max_players,
        'players': [],
        'state': 'waiting',  # waiting, playing, finished
        'deck': [],
        'discard': [],
        'current_color': None,
        'current_player_idx': 0,
        'direction': 1,  # 1 = عادي, -1 = معكوس
        'draw_stack': 0,
        'winner': None,
        'chat': [],
        'pending_wild': None,
        'uno_called': set(),
        'last_action': '',
        'created_at': time.time()
    }
    return code

def get_room(code):
    return rooms.get(code)

def add_player(room, player_name, sid):
    room['players'].append({
        'name': player_name,
        'sid': sid,
        'hand': [],
        'connected': True,
        'uno': False
    })

def find_player(room, sid=None, name=None):
    for i, p in enumerate(room['players']):
        if sid and p['sid'] == sid:
            return i, p
        if name and p['name'] == name:
            return i, p
    return None, None

def deal_cards(room):
    room['deck'] = make_deck()
    room['discard'] = []
    for player in room['players']:
        player['hand'] = []
        player['uno'] = False
    for _ in range(7):
        for player in room['players']:
            if room['deck']:
                player['hand'].append(room['deck'].pop())
    # أول ورقة على الطاولة (ليست wild)
    while True:
        if not room['deck']:
            room['deck'] = make_deck()
        card = room['deck'].pop()
        if card['color'] != 'wild':
            room['discard'].append(card)
            room['current_color'] = card['color']
            # تطبيق تأثير أول ورقة
            if card['value'] == 'skip':
                room['current_player_idx'] = 1 % len(room['players'])
            elif card['value'] == 'reverse':
                room['direction'] = -1
                room['current_player_idx'] = (len(room['players']) - 1) % len(room['players'])
            elif card['value'] == 'draw2':
                room['draw_stack'] = 2
            break

def refill_deck(room):
    if len(room['discard']) > 1:
        top = room['discard'][-1]
        room['deck'] = room['discard'][:-1]
        random.shuffle(room['deck'])
        room['discard'] = [top]

def draw_card(room, player_idx, count=1):
    cards = []
    for _ in range(count):
        if not room['deck']:
            refill_deck(room)
        if room['deck']:
            card = room['deck'].pop()
            room['players'][player_idx]['hand'].append(card)
            cards.append(card)
    return cards

def next_player(room):
    n = len(room['players'])
    room['current_player_idx'] = (room['current_player_idx'] + room['direction']) % n

def build_game_state(room, viewer_sid=None):
    players_info = []
    for i, p in enumerate(room['players']):
        hand_count = len(p['hand'])
        hand = p['hand'] if p['sid'] == viewer_sid else None
        players_info.append({
            'name': p['name'],
            'hand_count': hand_count,
            'hand': hand,
            'connected': p['connected'],
            'uno': p.get('uno', False),
            'is_current': i == room['current_player_idx'],
            'index': i,
            'sid': p['sid']
        })
    top_card = room['discard'][-1] if room['discard'] else None
    viewer_idx, _ = find_player(room, sid=viewer_sid) if viewer_sid else (None, None)
    return {
        'state': room['state'],
        'players': players_info,
        'top_card': top_card,
        'current_color': room['current_color'],
        'current_player_idx': room['current_player_idx'],
        'direction': room['direction'],
        'draw_stack': room['draw_stack'],
        'winner': room['winner'],
        'chat': room['chat'][-50:],
        'pending_wild': room['pending_wild'],
        'last_action': room['last_action'],
        'deck_count': len(room['deck']),
        'viewer_idx': viewer_idx,
        'host': room['host'],
        'code': room['code'],
        'max_players': room['max_players']
    }

def check_winner(room, player_idx):
    if len(room['players'][player_idx]['hand']) == 0:
        room['state'] = 'finished'
        room['winner'] = room['players'][player_idx]['name']
        return True
    return False

def add_chat(room, sender, message, msg_type='player'):
    room['chat'].append({
        'sender': sender,
        'message': message,
        'type': msg_type,
        'time': datetime.now().strftime('%H:%M')
    })

# ========== مسارات الويب ==========

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, page='home')

@app.route('/create', methods=['POST'])
def create():
    name = request.form.get('name', '').strip()
    max_p = int(request.form.get('max_players', 4))
    if not name or max_p < 2 or max_p > 8:
        return redirect('/')
    code = create_room(name, max_p)
    session['name'] = name
    session['room'] = code
    session['is_host'] = True
    return redirect(f'/room/{code}')

@app.route('/join', methods=['POST'])
def join():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip()
    if not name or not code:
        return redirect('/')
    room = get_room(code)
    if not room:
        return redirect('/?error=notfound')
    
    # التحقق من أن الاسم غير مكرر إلا لو كان نفس اللاعب بيعمل Reconnect
    idx, existing_player = find_player(room, name=name)
    if idx is None and len(room['players']) >= room['max_players'] and room['state'] == 'waiting':
        return redirect('/?error=full')
        
    session['name'] = name
    session['room'] = code
    session['is_host'] = (room['host'] == name)
    return redirect(f'/room/{code}')

@app.route('/room/<code>')
def room_page(code):
    if 'name' not in session or session.get('room') != code:
        return redirect('/')
    room = get_room(code)
    if not room:
        return redirect('/')
    return render_template_string(HTML_TEMPLATE, page='game',
        player_name=session['name'], room_code=code)

# ========== Socket.IO ==========

@socketio.on('connect')
def on_connect():
    pass

@socketio.on('join_game')
def on_join_game(data):
    code = data.get('code')
    name = data.get('name')
    room = get_room(code)
    if not room:
        emit('error', {'msg': 'الغرفة غير موجودة'})
        return

    # نظام الـ Reconnect المحسن
    existing_idx, existing_player = find_player(room, name=name)

    if existing_idx is not None:
        room['players'][existing_idx]['sid'] = request.sid
        room['players'][existing_idx]['connected'] = True
        join_room(code)
        emit('joined', {'success': True, 'player_name': name})
        state = build_game_state(room, request.sid)
        emit('game_state', state)
        add_chat(room, 'النظام', f'🔄 {name} عاد إلى اللعبة', 'system')
        socketio.emit('game_state', build_game_state(room), room=code)
        return

    if room['state'] != 'waiting':
        emit('error', {'msg': 'اللعبة بدأت بالفعل'})
        return
    if len(room['players']) >= room['max_players']:
        emit('error', {'msg': 'الغرفة ممتلئة'})
        return

    join_room(code)
    add_player(room, name, request.sid)
    add_chat(room, 'النظام', f'👋 {name} انضم إلى الغرفة', 'system')
    emit('joined', {'success': True, 'player_name': name})
    state = build_game_state(room, request.sid)
    emit('game_state', state)
    socketio.emit('game_state', build_game_state(room), room=code, include_self=False)

@socketio.on('start_game')
def on_start_game(data):
    code = data.get('code')
    name = data.get('name')
    room = get_room(code)
    if not room or room['host'] != name:
        return
    if len(room['players']) < 2:
        emit('error', {'msg': 'تحتاج لاعبين اثنين على الأقل'})
        return
    if room['state'] != 'waiting':
        return
    random.shuffle(room['players'])
    deal_cards(room)
    room['state'] = 'playing'
    room['current_player_idx'] = 0
    add_chat(room, 'النظام', '🎮 بدأت اللعبة! حظاً موفقاً للجميع 🎲', 'system')
    room['last_action'] = f"بدأت اللعبة! دور {room['players'][0]['name']}"
    for p in room['players']:
        state = build_game_state(room, p['sid'])
        socketio.emit('game_state', state, room=p['sid'])

@socketio.on('play_card')
def on_play_card(data):
    code = data.get('code')
    card_id = data.get('card_id')
    chosen_color = data.get('chosen_color')
    room = get_room(code)
    if not room or room['state'] != 'playing':
        return

    idx, player = find_player(room, sid=request.sid)
    if idx is None or idx != room['current_player_idx']:
        emit('error', {'msg': 'ليس دورك!'})
        return

    # إيجاد الورقة
    card = None
    card_pos = None
    for i, c in enumerate(player['hand']):
        if c['id'] == card_id:
            card = c
            card_pos = i
            break
    if card is None:
        emit('error', {'msg': 'الورقة غير موجودة'})
        return

    top_card = room['discard'][-1]

    # تحقق اللعب مع draw_stack
    if room['draw_stack'] > 0:
        if card['value'] == 'draw2' and top_card['value'] == 'draw2':
            pass  # مسموح
        elif card['value'] == 'wild4' and top_card['value'] == 'wild4':
            pass  # مسموح
        else:
            emit('error', {'msg': f'يجب عليك سحب {room["draw_stack"]} ورقة أو اللعب بورقة مماثلة!'})
            return

    # تحقق إمكانية اللعب
    if room['draw_stack'] == 0 and not card_playable(card, top_card, room['current_color']):
        emit('error', {'msg': 'لا يمكنك لعب هذه الورقة!'})
        return

    # Wild color
    if card['color'] == 'wild' and not chosen_color:
        emit('choose_color', {})
        return
    if card['color'] == 'wild' and chosen_color:
        card['chosen_color'] = chosen_color

    # العب الورقة
    player['hand'].pop(card_pos)
    room['discard'].append(card)

    if card['color'] == 'wild':
        room['current_color'] = chosen_color
    else:
        room['current_color'] = card['color']

    label = card_label(card)
    if card['color'] == 'wild' and chosen_color:
        label += f' → {COLOR_AR.get(chosen_color, chosen_color)}'

    room['last_action'] = f'{player["name"]} لعب {label}'
    add_chat(room, 'النظام', f'🃏 {player["name"]} لعب: {label}', 'system')

    # تحقق الفوز
    if check_winner(room, idx):
        add_chat(room, 'النظام', f'🏆 {player["name"]} فاز باللعبة!', 'system')
        for p in room['players']:
            socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])
        return

    # UNO
    if len(player['hand']) == 1:
        player['uno'] = True
        add_chat(room, 'النظام', f'🔴 {player["name"]} قال UNO!', 'system')
    else:
        player['uno'] = False

    # تأثيرات الأوراق
    n = len(room['players'])
    if card['value'] == 'skip':
        next_player(room)
        next_player(room)
        skipped = room['players'][(idx + room['direction']) % n]['name']
        add_chat(room, 'النظام', f'⛔ {skipped} تم تخطيه!', 'system')
    elif card['value'] == 'reverse':
        room['direction'] *= -1
        if n == 2:
            next_player(room)
            next_player(room)
        else:
            next_player(room)
        add_chat(room, 'النظام', f'🔄 تغير اتجاه اللعبة!', 'system')
    elif card['value'] == 'draw2':
        room['draw_stack'] += 2
        next_player(room)
        if room['draw_stack'] > 0 and not any(
            c['value'] == 'draw2' for c in room['players'][room['current_player_idx']]['hand']
        ):
            drawn = draw_card(room, room['current_player_idx'], room['draw_stack'])
            add_chat(room, 'النظام', f'😱 {room["players"][room["current_player_idx"]]["name"]} سحب {room["draw_stack"]} أوراق!', 'system')
            room['draw_stack'] = 0
            next_player(room)
    elif card['value'] == 'wild4':
        room['draw_stack'] += 4
        next_player(room)
        if room['draw_stack'] > 0 and not any(
            c['value'] == 'wild4' for c in room['players'][room['current_player_idx']]['hand']
        ):
            drawn = draw_card(room, room['current_player_idx'], room['draw_stack'])
            add_chat(room, 'النظام', f'💀 {room["players"][room["current_player_idx"]]["name"]} سحب {room["draw_stack"]} أوراق!', 'system')
            room['draw_stack'] = 0
            next_player(room)
    else:
        next_player(room)

    # إرسال الحالة
    for p in room['players']:
        socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('draw_card')
def on_draw_card(data):
    code = data.get('code')
    room = get_room(code)
    if not room or room['state'] != 'playing':
        return

    idx, player = find_player(room, sid=request.sid)
    if idx is None or idx != room['current_player_idx']:
        emit('error', {'msg': 'ليس دورك!'})
        return

    count = room['draw_stack'] if room['draw_stack'] > 0 else 1
    drawn = draw_card(room, idx, count)
    room['draw_stack'] = 0
    add_chat(room, 'النظام', f'📥 {player["name"]} سحب {count} ورقة', 'system')
    room['last_action'] = f'{player["name"]} سحب {count} ورقة'
    next_player(room)

    for p in room['players']:
        socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('call_uno')
def on_call_uno(data):
    code = data.get('code')
    room = get_room(code)
    if not room:
        return
    idx, player = find_player(room, sid=request.sid)
    if idx is None:
        return
    if len(player['hand']) == 1:
        player['uno'] = True
        add_chat(room, 'النظام', f'🔴 {player["name"]} قال UNO!', 'system')
        for p in room['players']:
            socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('catch_uno')
def on_catch_uno(data):
    code = data.get('code')
    target_name = data.get('target')
    room = get_room(code)
    if not room:
        return
    catcher_idx, catcher = find_player(room, sid=request.sid)
    for i, p in enumerate(room['players']):
        if p['name'] == target_name and len(p['hand']) == 1 and not p.get('uno', False):
            drawn = draw_card(room, i, 2)
            add_chat(room, 'النظام', f'🎯 {catcher["name"]} مسك {target_name} بدون UNO! {target_name} سحب ورقتين', 'system')
            for pl in room['players']:
                socketio.emit('game_state', build_game_state(room, pl['sid']), room=pl['sid'])
            return

@socketio.on('send_chat')
def on_send_chat(data):
    code = data.get('code')
    name = data.get('name')
    message = data.get('message', '').strip()
    if not message or len(message) > 200:
        return
    room = get_room(code)
    if not room:
        return
    add_chat(room, name, message, 'player')
    socketio.emit('new_chat', room['chat'][-1], room=code)

@socketio.on('restart_game')
def on_restart(data):
    code = data.get('code')
    name = data.get('name')
    room = get_room(code)
    if not room or room['host'] != name:
        return
    room['state'] = 'waiting'
    room['winner'] = None
    room['draw_stack'] = 0
    room['direction'] = 1
    room['current_player_idx'] = 0
    room['pending_wild'] = None
    room['last_action'] = ''
    for p in room['players']:
        p['hand'] = []
        p['uno'] = False
    add_chat(room, 'النظام', '🔄 إعادة تشغيل اللعبة...', 'system')
    for p in room['players']:
        socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

# ========== مسارات خاصة بالصوت WebRTC ==========
@socketio.on('voice_join')
def on_voice_join(data):
    # إخبار الآخرين أن لاعباً انضم لشبكة الصوت لكي يقوموا بإرسال Offer له
    emit('voice_user_joined', {'sid': request.sid, 'name': data.get('name')}, room=data.get('code'), include_self=False)

@socketio.on('voice_leave')
def on_voice_leave(data):
    emit('voice_user_left', {'sid': request.sid}, room=data.get('code'), include_self=False)

@socketio.on('webrtc_signal')
def on_webrtc_signal(data):
    target = data.get('target_sid')
    if target:
        emit('webrtc_signal', data, room=target)

@socketio.on('voice_speaking')
def on_voice_speaking(data):
    emit('voice_speaking_update', {'sid': request.sid, 'speaking': data.get('speaking')}, room=data.get('code'), include_self=False)

@socketio.on('disconnect')
def on_disconnect():
    for code, room in rooms.items():
        for p in room['players']:
            if p['sid'] == request.sid:
                p['connected'] = False
                add_chat(room, 'النظام', f'📴 {p["name"]} انقطع عن اللعبة', 'system')
                socketio.emit('game_state', build_game_state(room), room=code)
                socketio.emit('voice_user_left', {'sid': request.sid}, room=code, include_self=False)
                break

# ========== HTML/CSS/JS ==========

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>🃏 UNO بالعربي</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root {
  --bg: #0a0a0f;
  --surface: #111118;
  --surface2: #1a1a25;
  --surface3: #222230;
  --border: #2a2a3a;
  --accent: #ff4757;
  --accent2: #ffa502;
  --text: #e8e8f0;
  --text2: #8888a0;
  --red: #e74c3c;
  --green: #27ae60;
  --blue: #2980b9;
  --yellow: #f39c12;
  --wild: #333;
  --radius: 12px;
  --shadow: 0 8px 32px rgba(0,0,0,0.5);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Tajawal', sans-serif;
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ===== الصفحة الرئيسية ===== */
.home-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: radial-gradient(ellipse at top, #1a0a2e 0%, #0a0a0f 60%);
  overflow-y: auto;
}
.home-logo {
  font-size: clamp(48px, 10vw, 96px);
  font-weight: 900;
  letter-spacing: -2px;
  background: linear-gradient(135deg, #ff4757, #ffa502, #ffd700);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 0 30px rgba(255,71,87,0.5));
  animation: pulse-logo 2s ease-in-out infinite;
}
@keyframes pulse-logo {
  0%,100%{filter:drop-shadow(0 0 30px rgba(255,71,87,0.5))}
  50%{filter:drop-shadow(0 0 60px rgba(255,165,2,0.8))}
}
.home-subtitle {
  color: var(--text2);
  font-size: 18px;
  margin: 8px 0 40px;
  letter-spacing: 2px;
}
.home-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  width: 100%;
  max-width: 600px;
}
@media(max-width:480px){ .home-cards { grid-template-columns: 1fr; } }
.home-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 28px;
}
.home-card h2 {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 16px;
  color: var(--accent2);
}
.input-field {
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  color: var(--text);
  font-family: 'Tajawal', sans-serif;
  font-size: 15px;
  margin-bottom: 12px;
  transition: border-color 0.2s;
  text-align: right;
}
.input-field:focus { outline: none; border-color: var(--accent); }
.input-field::placeholder { color: var(--text2); }
select.input-field { cursor: pointer; }
.btn {
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: var(--radius);
  font-family: 'Tajawal', sans-serif;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-primary {
  background: linear-gradient(135deg, var(--accent), #ff6b81);
  color: white;
}
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(255,71,87,0.4); }
.btn-secondary {
  background: linear-gradient(135deg, var(--accent2), #ff7675);
  color: white;
}
.btn-secondary:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(255,165,2,0.4); }
.btn:active { transform: translateY(0); }

/* ===== الواجهة الرئيسية وتنسيق الهيكل ===== */
.game-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}
.game-header {
  flex-shrink: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 10px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.room-code { font-size: 13px; color: var(--text2); }
.room-code span { color: var(--accent2); font-weight: 700; font-size: 16px; letter-spacing: 2px; }

.game-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.game-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 10px;
  gap: 10px;
  overflow: hidden;
}

/* السيدبار الجانبي */
.sidebar {
  width: 320px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.3s ease;
}

@media(max-width:768px){
  .sidebar { 
    position: absolute; 
    right: 0; top: 0; bottom: 0; 
    transform: translateX(100%);
    z-index: 100; 
    box-shadow: -5px 0 30px rgba(0,0,0,0.8);
  }
  .sidebar.show { transform: translateX(0); }
}

/* ===== لوحة اللاعبين العلوية ===== */
.players-strip {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 5px;
  scrollbar-width: none; 
}
.player-chip {
  flex-shrink: 0;
  background: var(--surface2);
  border: 2px solid var(--border);
  border-radius: 50px;
  padding: 6px 14px 6px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s;
}
.player-chip.active {
  border-color: var(--accent2);
  background: rgba(255,165,2,0.1);
  box-shadow: 0 0 16px rgba(255,165,2,0.3);
}
.player-chip.me { border-color: var(--blue); }
.player-chip.disconnected { opacity: 0.4; }
.chip-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
}
.chip-info { display: flex; flex-direction: column; }
.chip-name {
  font-size: 13px; font-weight: 700;
  white-space: nowrap; max-width: 80px; overflow: hidden; text-overflow: ellipsis;
}
.chip-count { font-size: 11px; color: var(--text2); }
.chip-uno {
  background: var(--accent); color: white; font-size: 10px; font-weight: 900;
  padding: 2px 6px; border-radius: 4px; animation: uno-pulse 0.5s ease-in-out infinite alternate;
}
@keyframes uno-pulse { from{transform:scale(1)} to{transform:scale(1.1)} }

/* ===== منطقة الساحة (الطاولة) ===== */
.play-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  overflow: auto;
  min-height: 200px;
}
.table-center {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 30px;
  flex-wrap: wrap;
}
.color-indicator {
  width: 48px; height: 48px;
  border-radius: 50%;
  border: 3px solid white;
  box-shadow: 0 0 20px currentColor;
  flex-shrink: 0;
  transition: all 0.3s;
}
.deck-pile {
  width: 80px; height: 115px;
  background: linear-gradient(135deg, #1e3a5f, #2d5a8e);
  border-radius: 10px;
  border: 3px solid white;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
  position: relative;
  box-shadow: 4px 4px 0 #0a1f3f;
  color: white; font-weight: 900;
}
.deck-pile .deck-oval {
  width: 85%; height: 65%; background: #e74c3c; border-radius: 50%; 
  display: flex; align-items: center; justify-content: center; 
  transform: rotate(-25deg); border: 2px solid #f1c40f;
  font-size: 16px;
  text-shadow: 1px 1px 0 #000;
}
.deck-pile:hover { transform: scale(1.05); }
.deck-pile::before {
  content: attr(data-count);
  position: absolute; bottom: -24px; font-size: 12px; color: var(--text2); white-space: nowrap;
}

/* ======= تصميم كروت UNO الأصلية (نسخة طبق الأصل) ======= */
.top-card, .hand-card {
  border-radius: 8px;
  border: 5px solid white;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  position: relative;
  transition: transform 0.2s, box-shadow 0.2s;
  color: white;
  overflow: hidden;
  user-select: none;
}
.top-card {
  width: 90px; height: 130px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1);
  animation: card-played 0.3s ease-out;
}
.hand-card {
  flex-shrink: 0;
  width: 80px; height: 115px;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.3);
}
.hand-card:hover { transform: translateY(-20px); z-index: 10; }
.hand-card.playable { border-color: #f1c40f; box-shadow: 0 0 16px rgba(241,196,15,0.8); }
.hand-card.playable:hover { box-shadow: 0 8px 24px rgba(241,196,15,1); }
.hand-card.not-playable { opacity: 0.5; cursor: not-allowed; }
.hand-card.not-playable:hover { transform: none; }

/* الشكل البيضاوي الأبيض والنصوص للكروت */
.uno-oval {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%) rotate(-25deg);
  width: 85%; height: 65%;
  background: white;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  box-shadow: inset 0 0 6px rgba(0,0,0,0.4);
  z-index: 1;
}
.uno-val-center {
  font-size: 2.5em; font-weight: 900;
  transform: rotate(25deg);
  text-shadow: 2px 2px 0 #000;
  letter-spacing: -1px;
}
.c-yellow .uno-val-center { color: var(--yellow); }
.c-red .uno-val-center { color: var(--red); }
.c-green .uno-val-center { color: var(--green); }
.c-blue .uno-val-center { color: var(--blue); }
.c-wild .uno-val-center { color: #111; text-shadow: none; font-size: 1.5em; }

.corner-val {
  position: absolute; font-size: 1.2em; font-weight: 900;
  text-shadow: 1px 1px 0 #000; z-index: 2;
}
.corner-tl { top: 2px; left: 4px; }
.corner-br { bottom: 2px; right: 4px; transform: rotate(180deg); }

/* ألوان الخلفيات الأصلية */
.c-red { background: linear-gradient(135deg, #c0392b, #e74c3c); }
.c-green { background: linear-gradient(135deg, #1a6b3a, #27ae60); }
.c-blue { background: linear-gradient(135deg, #1a3a7a, #2980b9); }
.c-yellow { background: linear-gradient(135deg, #b8860b, #f39c12); }
.c-wild { background: linear-gradient(135deg, #8e44ad, #e74c3c, #f1c40f, #2980b9); }

/* ================================== */
.action-info {
  font-size: 14px; color: var(--text2); text-align: center;
  padding: 8px 16px; background: var(--surface2); border-radius: 50px;
}

/* ===== قسم أوراقك (اليد) =====  */
.my-hand-section {
  flex-shrink: 0;
  background: var(--surface2);
  border-radius: 16px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}
.hand-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px;
}
.hand-title { font-size: 15px; font-weight: 700; color: var(--text2); }
.hand-btn {
  padding: 6px 14px; border: none; border-radius: 8px; font-family: 'Tajawal', sans-serif;
  font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s;
}
.uno-btn { background: var(--accent); color: white; }
.uno-btn:hover { background: #ff6b81; }

.cards-scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 25px 5px 10px 5px; 
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.ci-red { color: #ff4757; background: rgba(255,71,87,0.2); }
.ci-green { color: #2ed573; background: rgba(46,213,115,0.2); }
.ci-blue { color: #1e90ff; background: rgba(30,144,255,0.2); }
.ci-yellow { color: #ffd700; background: rgba(255,215,0,0.2); }

/* ===== السيدبار =====  */
.sidebar-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.sidebar-tab {
  flex: 1; padding: 12px; border: none; background: none; color: var(--text2);
  font-family: 'Tajawal', sans-serif; font-size: 14px; font-weight: 600; cursor: pointer;
  border-bottom: 2px solid transparent;
}
.sidebar-tab.active { color: var(--accent2); border-bottom-color: var(--accent2); }
.tab-content { display: none; flex: 1; flex-direction: column; overflow: hidden; }
.tab-content.active { display: flex; }

/* ===== الشات ===== */
.chat-messages {
  flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
.chat-msg { padding: 8px 12px; border-radius: 10px; font-size: 13px; line-height: 1.4; word-break: break-word; }
.chat-msg.player-msg { background: var(--surface2); border-right: 3px solid var(--accent2); }
.chat-msg.system-msg { background: rgba(255,255,255,0.04); color: var(--text2); font-size: 12px; text-align: center; border-radius: 6px; }
.msg-sender { font-weight: 700; font-size: 12px; color: var(--accent2); margin-bottom: 2px; }
.msg-time { font-size: 10px; color: var(--text2); margin-top: 4px; }
.chat-input-area { padding: 10px; border-top: 1px solid var(--border); display: flex; gap: 8px; flex-shrink: 0; }
.chat-input {
  flex: 1; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; color: var(--text); font-family: 'Tajawal', sans-serif; font-size: 14px;
}
.chat-input:focus { outline: none; border-color: var(--accent2); }
.send-btn {
  background: var(--accent2); border: none; border-radius: 8px; width: 40px; cursor: pointer;
  font-size: 18px; color: white; display: flex; align-items: center; justify-content: center;
}

/* ===== لوحة اللاعبين في السيدبار ===== */
.players-list { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.player-row {
  background: var(--surface2); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px; display: flex; align-items: center; gap: 10px;
}
.player-row.active { border-color: var(--accent2); background: rgba(255,165,2,0.08); }
.player-row.me { border-color: var(--blue); }
.p-avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.p-info { flex: 1; min-width: 0; }
.p-name { font-weight: 700; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.p-cards { font-size: 12px; color: var(--text2); }
.p-badge { font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 700; }

/* ===== الغرفة الانتظار ===== */
.waiting-room {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
}
.waiting-code { background: var(--surface2); border: 2px dashed var(--accent2); border-radius: 16px; padding: 20px 32px; text-align: center; }
.waiting-code-label { font-size: 14px; color: var(--text2); margin-bottom: 8px; }
.waiting-code-value { font-size: 48px; font-weight: 900; letter-spacing: 10px; color: var(--accent2); }

/* ===== المودال ===== */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 200; padding: 20px;
}
.modal { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 28px; max-width: 360px; width: 100%; text-align: center; }
.color-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.color-btn { padding: 16px; border: none; border-radius: 12px; font-family: 'Tajawal', sans-serif; font-size: 18px; font-weight: 900; cursor: pointer; color: white; }
.color-btn:hover { transform: scale(1.05); }
.color-btn.red { background: var(--red); }
.color-btn.green { background: var(--green); color: #111; }
.color-btn.blue { background: var(--blue); }
.color-btn.yellow { background: var(--yellow); color: #111; }

/* ===== الفائز ===== */
.winner-card {
  background: linear-gradient(135deg, #1a1025, #0d1a2e); border: 2px solid var(--accent2);
  border-radius: 24px; padding: 40px; text-align: center; box-shadow: 0 0 60px rgba(255,165,2,0.3);
}
.winner-emoji { font-size: 70px; margin-bottom: 12px; }
.winner-title { font-size: 32px; font-weight: 900; color: var(--accent2); }

/* ===== المايك ===== */
.voice-bar {
  background: var(--surface2); border-top: 1px solid var(--border); padding: 10px; display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}
.mic-btn {
  width: 45px; height: 45px; border-radius: 50%; border: none; cursor: pointer; font-size: 20px;
  display: flex; align-items: center; justify-content: center; background: var(--surface3); color: var(--text2);
}
.mic-btn.active { background: var(--accent); color: white; animation: mic-pulse 1s infinite alternate; }
@keyframes mic-pulse { from{box-shadow: 0 0 5px var(--accent);} to{box-shadow: 0 0 15px var(--accent);} }
.voice-users { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.voice-user { font-size: 13px; padding: 4px 12px; border-radius: 50px; background: var(--surface3); display: flex; align-items: center; gap: 6px; }
.voice-user.speaking { background: rgba(46,213,115,0.2); color: var(--green); font-weight: bold; }

/* ===== موبايل ===== */
.mobile-chat-btn {
  display: none; position: fixed; bottom: 20px; left: 20px; width: 55px; height: 55px;
  border-radius: 50%; background: var(--accent2); border: none; color: white; font-size: 24px;
  z-index: 50; box-shadow: var(--shadow);
}
@media(max-width:768px){ .mobile-chat-btn { display: flex; align-items: center; justify-content: center; } }
.sidebar-close {
  display: none; position: absolute; top: 10px; left: 10px; background: var(--accent); border: none;
  color: white; font-size: 20px; width: 35px; height: 35px; border-radius: 50%;
}
@media(max-width:768px){ .sidebar-close { display: flex; align-items: center; justify-content: center; } }

/* نبض الدور */
.my-turn-banner {
  background: linear-gradient(135deg, rgba(255,165,2,0.2), rgba(255,71,87,0.2));
  border: 1px solid var(--accent2); border-radius: 10px; padding: 8px 16px;
  text-align: center; font-weight: 700; color: var(--accent2); font-size: 15px;
  animation: my-turn-pulse 1s ease-in-out infinite; width: 100%; max-width: 400px;
}
@keyframes my-turn-pulse { 0%,100%{opacity:1}50%{opacity:0.6} }
.draw-stack-badge {
  position: absolute; top: -10px; right: -10px; background: var(--accent); color: white;
  font-size: 13px; font-weight: 900; padding: 4px 8px; border-radius: 50px; box-shadow: 0 2px 5px rgba(0,0,0,0.5); z-index: 5;
}
</style>
</head>
<body>

{% if page == 'home' %}
<div class="home-page">
  <div class="home-logo">UNO</div>
  <div class="home-subtitle">🃏 العبة الكلاسيكية بالعربي</div>
  <div class="home-cards">
    <div class="home-card">
      <h2>🏠 إنشاء غرفة</h2>
      <form action="/create" method="POST">
        <input class="input-field" type="text" name="name" placeholder="اسمك" required maxlength="20">
        <select class="input-field" name="max_players">
          <option value="2">لاعبان (2)</option>
          <option value="3">3 لاعبين</option>
          <option value="4" selected>4 لاعبين</option>
          <option value="5">5 لاعبين</option>
          <option value="6">6 لاعبين</option>
          <option value="8">8 لاعبين</option>
        </select>
        <button class="btn btn-primary" type="submit">إنشاء غرفة 🎮</button>
      </form>
    </div>
    <div class="home-card">
      <h2>🚪 انضمام لغرفة</h2>
      <form action="/join" method="POST">
        <input class="input-field" type="text" name="name" placeholder="اسمك" required maxlength="20">
        <input class="input-field" type="text" name="code" placeholder="كود الغرفة (6 أرقام)"
          required maxlength="6" pattern="[0-9]{6}" inputmode="numeric">
        <button class="btn btn-secondary" type="submit">انضم الآن ▶</button>
      </form>
    </div>
  </div>
  <div style="margin-top:24px;color:var(--text2);font-size:13px;text-align:center;line-height:1.8">
    🎴 كل لاعب يبدأ بـ7 أوراق · 🔄 الأوراق الخاصة تغير الدور · 🔴 قل UNO عند آخر ورقة
  </div>
</div>

{% elif page == 'game' %}
<div class="game-page">
  <div class="game-header">
    <div class="room-code">الغرفة: <span id="roomCodeDisplay">{{ room_code }}</span></div>
    <div id="gameStatusBadge" style="font-size:14px;color:var(--text2); font-weight: bold;">⏳ انتظار...</div>
    <div id="directionIndicator" style="font-size:20px; color: var(--accent2);">▶</div>
  </div>

  <div class="game-body">
    <div class="game-main">
      <div class="players-strip" id="playersStrip"></div>

      <div class="play-area" id="playArea">
        <div id="waitingRoom" class="waiting-room">
          <div class="waiting-code">
            <div class="waiting-code-label">شارك هذا الكود مع أصدقائك</div>
            <div class="waiting-code-value">{{ room_code }}</div>
          </div>
          <div id="waitingPlayers" class="waiting-players"></div>
          <button class="btn btn-primary" id="startBtn" style="max-width:240px;display:none; font-size: 18px;"
            onclick="startGame()">🎮 ابدأ اللعبة</button>
          <div id="waitingHint" style="color:var(--text2);font-size:14px;text-align:center"></div>
        </div>

        <div id="gameTable" style="display:none;width:100%;flex-direction:column;align-items:center;gap:20px">
          <div id="myTurnBanner" style="display:none" class="my-turn-banner">🎯 دورك الآن! العب ورقة أو اسحب من الساحة</div>
          <div class="table-center">
            <div class="deck-pile" id="deckPile" onclick="drawCard()" title="اسحب ورقة" data-count="52 ورقة"><div class="deck-oval">UNO</div></div>
            <div id="topCard"></div>
            <div id="colorIndicator" class="color-indicator"></div>
          </div>
          <div id="actionInfo" class="action-info">ابدأ اللعبة</div>
        </div>
      </div>

      <div class="my-hand-section" id="myHandSection" style="display:none">
        <div class="hand-header">
          <span class="hand-title" id="handTitle">أوراقك</span>
          <div class="hand-actions">
            <button class="hand-btn uno-btn" onclick="callUno()">🔴 UNO!</button>
          </div>
        </div>
        <div class="cards-scroll" id="myHandCards"></div>
      </div>
    </div>

    <div class="sidebar" id="sidebar">
      <button class="sidebar-close" onclick="toggleSidebar()">✕</button>
      <div class="sidebar-tabs">
        <button class="sidebar-tab active" onclick="switchTab('chat')">💬 المحادثة</button>
        <button class="sidebar-tab" onclick="switchTab('players')">👥 اللاعبون</button>
      </div>

      <div class="tab-content active" id="tab-chat">
        <div class="chat-messages" id="chatMessages"></div>
        <div class="voice-bar">
          <button class="mic-btn" id="micBtn" onclick="toggleMic()" title="تشغيل المايك">🎤</button>
          <div class="voice-users" id="voiceUsers">
            <span style="font-size:12px;color:var(--text2)">انقر للإنضمام للصوت</span>
          </div>
        </div>
        <div class="chat-input-area">
          <input class="chat-input" id="chatInput" placeholder="اكتب رسالتك هنا..." maxlength="200"
            onkeydown="if(event.key==='Enter')sendChat()">
          <button class="send-btn" onclick="sendChat()">➤</button>
        </div>
      </div>

      <div class="tab-content" id="tab-players">
        <div class="players-list" id="playersList"></div>
        <div style="padding:15px;border-top:1px solid var(--border)">
          <button class="btn btn-secondary" id="restartBtn" style="display:none;" onclick="restartGame()">🔄 إعادة اللعبة من جديد</button>
        </div>
      </div>
    </div>
  </div>

  <button class="mobile-chat-btn" onclick="toggleSidebar()">💬</button>
  
  <div id="audioElements" style="display:none;"></div>
</div>

<div class="modal-overlay" id="colorModal" style="display:none">
  <div class="modal">
    <h3>🎨 اختر اللون الجديد</h3>
    <div class="color-grid">
      <button class="color-btn red" onclick="chooseColor('red')">🔴 أحمر</button>
      <button class="color-btn green" onclick="chooseColor('green')">🟢 أخضر</button>
      <button class="color-btn blue" onclick="chooseColor('blue')">🔵 أزرق</button>
      <button class="color-btn yellow" onclick="chooseColor('yellow')">🟡 أصفر</button>
    </div>
  </div>
</div>

<div class="winner-overlay" id="winnerOverlay" style="display:none">
  <div class="winner-card">
    <div class="winner-emoji">🏆</div>
    <div class="winner-title">لدينا فائز!</div>
    <div class="winner-name" id="winnerName" style="font-size: 24px; font-weight: bold; margin: 15px 0;"></div>
    <div class="winner-btns">
      <button class="btn btn-primary" id="winRestartBtn" style="display:none" onclick="restartGame()">🔄 لعب دور جديد</button>
      <button class="btn btn-secondary" onclick="window.location='/'">🏠 الخروج للرئيسية</button>
    </div>
  </div>
</div>

<script>
const PLAYER_NAME = "{{ player_name }}";
const ROOM_CODE = "{{ room_code }}";

let socket = null;
let gameState = null;
let pendingCard = null;
let isHost = false;

// ===== الاتصال وإعادة الاتصال (Reconnect) =====
function connect() {
  socket = io();
  socket.on('connect', () => {
    // بمجرد الاتصال، نرسل طلب الانضمام. السيرفر سيتعرف على الاسم ويحدث الجلسة
    socket.emit('join_game', { code: ROOM_CODE, name: PLAYER_NAME });
  });
  socket.on('joined', (data) => {
    if (!data.success) alert(data.msg || 'حدث خطأ في الانضمام');
  });
  socket.on('game_state', (state) => {
    gameState = state;
    render(state);
  });
  socket.on('new_chat', (msg) => {
    appendChat(msg);
  });
  socket.on('choose_color', () => {
    document.getElementById('colorModal').style.display = 'flex';
  });
  socket.on('error', (data) => {
    showToast('⚠️ ' + data.msg);
  });
  socket.on('disconnect', () => {
    showToast('🔴 انقطع الاتصال بالسيرفر، جاري المحاولة...');
    // إعادة محاولة الاتصال التلقائي
    setTimeout(() => { if (!socket.connected) socket.connect(); }, 2000);
  });
}

// ===== رندر الحالة =====
function render(state) {
  isHost = state.host === PLAYER_NAME;
  updateHeader(state);
  if (state.state === 'waiting') {
    renderWaiting(state);
  } else {
    renderGame(state);
  }
  if (state.winner) renderWinner(state);
  renderPlayers(state);
}

function updateHeader(state) {
  const badge = document.getElementById('gameStatusBadge');
  const dir = document.getElementById('directionIndicator');
  if (state.state === 'waiting') badge.textContent = `⏳ في الانتظار: ${state.players.length}/${state.max_players}`;
  else if (state.state === 'playing') {
    const cur = state.players[state.current_player_idx];
    badge.textContent = cur ? `🎯 دور: ${cur.name}` : '';
    badge.style.color = cur && cur.name === PLAYER_NAME ? 'var(--accent2)' : 'var(--text2)';
  } else if (state.state === 'finished') badge.textContent = '🏆 انتهت اللعبة';
  dir.textContent = state.direction === 1 ? '▶ اتجاه اللعب' : '◀ اتجاه عكسي';
}

function renderWaiting(state) {
  document.getElementById('waitingRoom').style.display = 'flex';
  document.getElementById('gameTable').style.display = 'none';
  document.getElementById('myHandSection').style.display = 'none';
  const wp = document.getElementById('waitingPlayers');
  wp.innerHTML = state.players.map(p => `
    <div class="player-row ${p.name === PLAYER_NAME ? 'me' : ''}">
      <div class="p-avatar" style="background:${avatarColor(p.name)};color:white">${p.name[0]}</div>
      <div class="p-info">
        <div class="p-name">${p.name} ${p.name === state.host ? '👑' : ''}</div>
        <div class="p-cards">${p.name === PLAYER_NAME ? '(أنت)' : 'موجود بالغرفة'}</div>
      </div>
    </div>`).join('');
  const startBtn = document.getElementById('startBtn');
  const hint = document.getElementById('waitingHint');
  if (isHost) {
    if (state.players.length >= 2) {
      startBtn.style.display = 'block';
      hint.textContent = `جاهزون للبدء! (العدد: ${state.players.length} من أصل ${state.max_players})`;
    } else {
      startBtn.style.display = 'none';
      hint.textContent = 'في انتظار انضمام أصدقائك للغرفة...';
    }
  } else {
    startBtn.style.display = 'none';
    hint.textContent = `في انتظار قيام الهوست (${state.host}) ببدء اللعبة...`;
  }
}

function renderGame(state) {
  document.getElementById('waitingRoom').style.display = 'none';
  document.getElementById('gameTable').style.display = 'flex';
  document.getElementById('myHandSection').style.display = 'flex';

  const myIdx = state.viewer_idx;
  const isMyTurn = myIdx === state.current_player_idx;
  const myPlayer = myIdx !== null ? state.players[myIdx] : null;

  const banner = document.getElementById('myTurnBanner');
  banner.style.display = isMyTurn && state.state === 'playing' ? 'block' : 'none';

  const tc = state.top_card;
  const topEl = document.getElementById('topCard');
  const valMap = {skip:'⊘',reverse:'⇄',draw2:'+2',wild:'🌈',wild4:'🌈+4', '0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9'};
  
  if (tc) {
    let tVal = valMap[tc.value]||tc.value;
    topEl.className = `top-card c-${tc.color === 'wild' ? 'wild' : tc.color}`;
    topEl.innerHTML = `
      <div class="corner-val corner-tl">${tVal}</div>
      <div class="uno-oval"><div class="uno-val-center">${tVal}</div></div>
      <div class="corner-val corner-br">${tVal}</div>
      ${state.draw_stack > 0 ? `<div class="draw-stack-badge">+${state.draw_stack}</div>` : ''}
    `;
  }

  const ci = document.getElementById('colorIndicator');
  ci.className = `color-indicator ci-${state.current_color||'wild'}`;
  const colorMap = {red:'var(--red)',green:'var(--green)',blue:'var(--blue)',yellow:'var(--yellow)',wild:'var(--wild)'};
  ci.style.boxShadow = `0 0 25px ${colorMap[state.current_color]||'gray'}`;

  const dp = document.getElementById('deckPile');
  dp.dataset.count = state.deck_count + ' ورقة بالكومة';
  dp.style.cursor = isMyTurn ? 'pointer' : 'default';
  dp.onclick = isMyTurn ? drawCard : null;

  document.getElementById('actionInfo').textContent = state.last_action || '';

  const strip = document.getElementById('playersStrip');
  strip.innerHTML = state.players.map((p, i) => {
    const colors = ['#ff4757','#2ed573','#1e90ff','#ffd700','#a855f7','#ff7f50','#20b2aa','#ff69b4'];
    const col = colors[i % colors.length];
    return `<div class="player-chip ${i === state.current_player_idx ? 'active' : ''} ${p.name === PLAYER_NAME ? 'me' : ''} ${!p.connected ? 'disconnected' : ''}">
      <div class="chip-avatar" style="background:${col};color:${i===3?'#1a1a00':'white'}">${p.name[0]}</div>
      <div class="chip-info">
        <div class="chip-name">${p.name}</div>
        <div class="chip-count">${p.hand_count} كروت</div>
      </div>
      ${p.uno ? '<span class="chip-uno">UNO!</span>' : ''}
    </div>`;
  }).join('');

  const hand = myPlayer ? myPlayer.hand : null;
  const handTitle = document.getElementById('handTitle');
  if (!hand) {
    document.getElementById('myHandCards').innerHTML = '<div style="color:var(--text2);font-size:13px; margin: auto;">أنت متصل كزائر الآن</div>';
    return;
  }
  handTitle.textContent = `أوراقك الخاصة (${hand.length})`;

  const cards = document.getElementById('myHandCards');
  
  cards.innerHTML = hand.map(c => {
    const canPlay = isMyTurn && state.state === 'playing' && cardPlayable(c, tc, state.current_color, state.draw_stack);
    let val = valMap[c.value]||c.value;
    return `<div class="hand-card c-${c.color === 'wild' ? 'wild' : c.color} ${canPlay ? 'playable' : 'not-playable'}"
      onclick="${canPlay ? `playCard('${c.id}')` : `showToast('هذه الورقة لا تطابق الورقة في الساحة!')`}"
      title="${cardLabelAr(c)}">
      <div class="corner-val corner-tl">${val}</div>
      <div class="uno-oval"><div class="uno-val-center">${val}</div></div>
      <div class="corner-val corner-br">${val}</div>
    </div>`;
  }).join('');
}

function renderPlayers(state) {
  const list = document.getElementById('playersList');
  const colors = ['#ff4757','#2ed573','#1e90ff','#ffd700','#a855f7','#ff7f50','#20b2aa','#ff69b4'];
  list.innerHTML = state.players.map((p, i) => {
    const col = colors[i % colors.length];
    const isActive = i === state.current_player_idx;
    const isMe = p.name === PLAYER_NAME;
    let badge = '';
    if (p.name === state.host) badge = '<span class="p-badge" style="background:rgba(255,165,2,0.2);color:var(--accent2)">👑 الهوست</span>';
    if (isMe) badge += '<span class="p-badge" style="background:rgba(30,144,255,0.2);color:var(--blue)">أنت</span>';
    if (p.uno) badge += '<span class="p-badge" style="background:rgba(255,71,87,0.3);color:var(--red)">UNO!</span>';
    if (!p.connected) badge += '<span class="p-badge" style="background:rgba(100,100,100,0.2);color:var(--text2)">📴 غير متصل</span>';

    let catchBtn = '';
    if (state.state === 'playing' && p.name !== PLAYER_NAME && p.hand_count === 1 && !p.uno) {
      catchBtn = `<button onclick="catchUno('${p.name}')" style="background:var(--accent);border:none;color:white;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;font-family:Tajawal; font-weight: bold;">صيده بدون UNO!</button>`;
    }
    return `<div class="player-row ${isActive ? 'active' : ''} ${isMe ? 'me' : ''}">
      <div class="p-avatar" style="background:${col};color:${i===3?'#1a1a00':'white'}">${p.name[0]}</div>
      <div class="p-info">
        <div class="p-name">${p.name}</div>
        <div class="p-cards">${p.hand_count} كروت متبقية</div>
      </div>
      <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap">
        ${badge}${catchBtn}
      </div>
    </div>`;
  }).join('');

  const rb = document.getElementById('restartBtn');
  rb.style.display = isHost && (state.state === 'finished' || state.state === 'playing') ? 'block' : 'none';
  const wr = document.getElementById('winRestartBtn');
  if (wr) wr.style.display = isHost ? 'block' : 'none';
}

function renderWinner(state) {
  document.getElementById('winnerOverlay').style.display = 'flex';
  document.getElementById('winnerName').textContent = state.winner;
}

// ===== منطق اللعب =====
function cardPlayable(card, topCard, currentColor, drawStack) {
  if (!topCard) return false;
  if (drawStack > 0) {
    if (card.value === 'draw2' && topCard.value === 'draw2') return true;
    if (card.value === 'wild4' && topCard.value === 'wild4') return true;
    return false;
  }
  if (card.color === 'wild') return true;
  if (card.color === currentColor) return true;
  if (card.value === topCard.value) return true;
  return false;
}

function cardLabelAr(c) {
  const valMap = {skip:'تخطي',reverse:'عكس',draw2:'سحب 2',wild:'ملوّن',wild4:'سحب 4 ملوّن'};
  const colMap = {red:'أحمر',green:'أخضر',blue:'أزرق',yellow:'أصفر',wild:'مميز'};
  return (colMap[c.color]||c.color) + ' ' + (valMap[c.value]||c.value);
}

function playCard(cardId) {
  if (!gameState) return;
  const myIdx = gameState.viewer_idx;
  if (myIdx !== gameState.current_player_idx) return;
  const myPlayer = gameState.players[myIdx];
  const card = myPlayer.hand ? myPlayer.hand.find(c => c.id === cardId) : null;
  if (!card) return;

  if (card.color === 'wild') {
    pendingCard = cardId;
    document.getElementById('colorModal').style.display = 'flex';
    return;
  }
  socket.emit('play_card', { code: ROOM_CODE, card_id: cardId });
}

function chooseColor(color) {
  document.getElementById('colorModal').style.display = 'none';
  if (pendingCard) {
    socket.emit('play_card', { code: ROOM_CODE, card_id: pendingCard, chosen_color: color });
    pendingCard = null;
  }
}

function drawCard() {
  if (!gameState || gameState.viewer_idx !== gameState.current_player_idx) return;
  socket.emit('draw_card', { code: ROOM_CODE });
}

function callUno() {
  socket.emit('call_uno', { code: ROOM_CODE });
}

function catchUno(name) {
  socket.emit('catch_uno', { code: ROOM_CODE, target: name });
}

function startGame() {
  socket.emit('start_game', { code: ROOM_CODE, name: PLAYER_NAME });
}

function restartGame() {
  document.getElementById('winnerOverlay').style.display = 'none';
  socket.emit('restart_game', { code: ROOM_CODE, name: PLAYER_NAME });
}

// ===== الشات =====
function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  socket.emit('send_chat', { code: ROOM_CODE, name: PLAYER_NAME, message: msg });
  input.value = '';
}

function appendChat(msg) {
  const container = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = `chat-msg ${msg.type === 'system' ? 'system-msg' : 'player-msg'}`;
  if (msg.type === 'player') {
    div.innerHTML = `<div class="msg-sender">${msg.sender}</div>${escHtml(msg.message)}<div class="msg-time">${msg.time}</div>`;
  } else {
    div.textContent = msg.message;
  }
  container.appendChild(div);
  const shouldScroll = container.scrollTop + container.clientHeight > container.scrollHeight - 60;
  if (shouldScroll) container.scrollTop = container.scrollHeight;
}

function loadChat(chatArr) {
  const container = document.getElementById('chatMessages');
  container.innerHTML = '';
  chatArr.forEach(appendChat);
  container.scrollTop = container.scrollHeight;
}

// =========================================================
// ====== نظام الصوت الحقيقي القوي (Mesh Network) ======
// =========================================================
let localStream = null;
let micActive = false;
let peerConnections = {}; 
let voiceUsers = {}; 

// إضافة سيرفرات قوية لضمان الاتصال من شبكات مختلفة
const rtcConfig = { 
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun2.l.google.com:19302' },
        { urls: 'stun:stun3.l.google.com:19302' },
        { urls: 'stun:stun4.l.google.com:19302' }
    ] 
};

async function toggleMic() {
  const btn = document.getElementById('micBtn');
  
  if (!micActive) {
    try {
      // طلب الإذن للمايك فقط
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micActive = true;
      btn.classList.add('active');
      btn.title = 'إغلاق المايك';
      
      voiceUsers[socket.id] = { name: PLAYER_NAME, speaking: false };
      updateVoiceBar();
      
      // إخبار الجميع لإنشاء اتصالات
      socket.emit('voice_join', { code: ROOM_CODE, name: PLAYER_NAME, sid: socket.id });
      setupVoiceAnalyser();
      showToast('🎤 جاري ربطك صوتياً بباقي الغرفة...');
    } catch(e) {
      showToast('❌ المتصفح يمنع وصول المايك! تأكد من إعطاء الصلاحيات.');
      console.error('Mic Error:', e);
    }
  } else {
    // إغلاق المايك بالكامل
    if (localStream) localStream.getTracks().forEach(t => t.stop());
    localStream = null;
    micActive = false;
    btn.classList.remove('active');
    btn.title = 'تشغيل المايك';
    
    delete voiceUsers[socket.id];
    updateVoiceBar();
    
    Object.keys(peerConnections).forEach(sid => {
      peerConnections[sid].close();
      const audioEl = document.getElementById('audio_' + sid);
      if (audioEl) audioEl.remove();
    });
    peerConnections = {};
    
    socket.emit('voice_leave', { code: ROOM_CODE, sid: socket.id });
    showToast('🔇 تم إيقاف المايك');
  }
}

// لما حد جديد يفتح المايك، إنت (الموجود مسبقاً) هتبعتله عرض اتصال Offer
socket && socket.on('voice_user_joined', async (data) => {
  if (!micActive || data.sid === socket.id) return;
  
  voiceUsers[data.sid] = { name: data.name, speaking: false };
  updateVoiceBar();
  
  try {
      const pc = createPeerConnection(data.sid, data.name);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      
      socket.emit('webrtc_signal', {
        target_sid: data.sid,
        sender_sid: socket.id,
        sender_name: PLAYER_NAME,
        type: 'offer',
        sdp: pc.localDescription,
        code: ROOM_CODE
      });
  } catch(e) {
      console.error("خطأ في إنشاء اتصال مع", data.name, e);
  }
});

// لما حد يقفل المايك
socket && socket.on('voice_user_left', (data) => {
  if (peerConnections[data.sid]) {
    peerConnections[data.sid].close();
    delete peerConnections[data.sid];
  }
  if (voiceUsers[data.sid]) {
    delete voiceUsers[data.sid];
  }
  const audioEl = document.getElementById('audio_' + data.sid);
  if (audioEl) audioEl.remove();
  updateVoiceBar();
});

// استقبال العروض والردود (Signaling)
socket && socket.on('webrtc_signal', async (data) => {
  if (data.target_sid !== socket.id || !micActive) return;
  
  let pc = peerConnections[data.sender_sid];
  
  try {
      if (data.type === 'offer') {
        if (!pc) {
           voiceUsers[data.sender_sid] = { name: data.sender_name, speaking: false };
           updateVoiceBar();
           pc = createPeerConnection(data.sender_sid, data.sender_name);
        }
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        
        socket.emit('webrtc_signal', {
          target_sid: data.sender_sid,
          sender_sid: socket.id,
          sender_name: PLAYER_NAME,
          type: 'answer',
          sdp: pc.localDescription,
          code: ROOM_CODE
        });
      } else if (data.type === 'answer') {
        if (pc) await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
      } else if (data.type === 'candidate') {
        if (pc && pc.remoteDescription) {
          await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
        }
      }
  } catch(e) {
      console.error("Signal Error:", e);
  }
});

function createPeerConnection(sid, name) {
  const pc = new RTCPeerConnection(rtcConfig);
  peerConnections[sid] = pc;
  
  if (localStream) {
    localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
  }
  
  pc.onicecandidate = (e) => {
    if (e.candidate) {
      socket.emit('webrtc_signal', {
        target_sid: sid,
        sender_sid: socket.id,
        type: 'candidate',
        candidate: e.candidate,
        code: ROOM_CODE
      });
    }
  };
  
  pc.ontrack = (e) => {
    let audio = document.getElementById('audio_' + sid);
    if (!audio) {
      audio = document.createElement('audio');
      audio.id = 'audio_' + sid;
      audio.autoplay = true;
      audio.controls = false; // مخفي للمستخدم
      document.getElementById('audioElements').appendChild(audio);
    }
    audio.srcObject = e.streams[0];
    
    // إجبار تشغيل الصوت تفادياً لسياسات المتصفح
    let playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.then(() => {
          console.log("صوت " + name + " يعمل الآن");
      }).catch(error => {
        console.warn("سياسة المتصفح تمنع التشغيل التلقائي للصوت لـ", name);
      });
    }
  };
  
  return pc;
}

// التحدث بصرياً
function setupVoiceAnalyser() {
  if (!localStream) return;
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = ctx.createMediaStreamSource(localStream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  src.connect(analyser);
  const buf = new Uint8Array(analyser.frequencyBinCount);
  
  function check() {
    if (!micActive) return;
    analyser.getByteFrequencyData(buf);
    const vol = buf.reduce((a,b)=>a+b,0)/buf.length;
    const speaking = vol > 15; // حساسية المايك
    
    if (voiceUsers[socket.id] && voiceUsers[socket.id].speaking !== speaking) {
        voiceUsers[socket.id].speaking = speaking;
        updateVoiceBar();
        socket.emit('voice_speaking', { code: ROOM_CODE, sid: socket.id, speaking: speaking });
    }
    requestAnimationFrame(check);
  }
  check();
}

socket && socket.on('voice_speaking_update', (data) => {
    if (voiceUsers[data.sid]) {
        voiceUsers[data.sid].speaking = data.speaking;
        updateVoiceBar();
    }
});

function updateVoiceBar() {
  const bar = document.getElementById('voiceUsers');
  const sids = Object.keys(voiceUsers);
  if (sids.length === 0) {
    bar.innerHTML = '<span style="font-size:12px;color:var(--text2)">انقر على المايك للانضمام للصوت</span>';
    return;
  }
  bar.innerHTML = sids.map(sid => {
    const u = voiceUsers[sid];
    return `<div class="voice-user ${u && u.speaking ? 'speaking' : ''}">
      ${u && u.speaking ? '🔊' : '🎤'} ${u.name}
    </div>`;
  }).join('');
}

// ===== المساعدات =====
function switchTab(tab) {
  document.querySelectorAll('.sidebar-tab').forEach((t,i) => {
    t.classList.toggle('active', (i===0 && tab==='chat') || (i===1 && tab==='players'));
  });
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
}

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  sb.classList.toggle('show');
}

function avatarColor(name) {
  const colors = ['#ff4757','#2ed573','#1e90ff','#ffd700','#a855f7','#ff7f50','#20b2aa','#ff69b4'];
  let h = 0;
  for (let c of name) h = (h*31 + c.charCodeAt(0)) % colors.length;
  return colors[h];
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

let toastTimeout;
function showToast(msg) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.style.cssText = `position:fixed;bottom:100px;left:50%;transform:translateX(-50%);
      background:var(--surface);border:1px solid var(--border);border-radius:50px;
      padding:10px 20px;font-size:15px; font-weight: bold; z-index:999;transition:all 0.3s;
      box-shadow:var(--shadow);white-space:nowrap;max-width:90vw;text-align:center`;
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { t.style.opacity = '0'; }, 3000);
}

// بعد تحميل الشات الكامل
const origRender = render;
window.render = function(state) {
  origRender(state);
  if (state.chat) loadChat(state.chat);
};

connect();
{% endif %}
</script>
</body>
</html>
"""

# المتغير الخاص باستضافة Render
application = app

if __name__ == '__main__':
    print("=" * 50)
    print("🃏 لعبة UNO بالعربي - نسخة Render النهائية")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
