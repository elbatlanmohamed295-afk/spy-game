"""
لعبة UNO كاملة - ملف بايثون واحد شامل
النسخة الاحترافية (Render Edition)
"""

from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'uno-pro-secret-key-2026'
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
    unique_deck = []
    for i, card in enumerate(deck):
        card['id'] = f"{card['color']}_{card['value']}_{i}"
        unique_deck.append(card)
    random.shuffle(unique_deck)
    return unique_deck

def card_playable(card, top_card, current_color):
    if card['color'] == 'wild': return True
    if card['color'] == current_color: return True
    if card['value'] == top_card['value']: return True
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
        'state': 'waiting',
        'deck': [],
        'discard': [],
        'current_color': None,
        'current_player_idx': 0,
        'direction': 1,
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
        if sid and p['sid'] == sid: return i, p
        if name and p['name'] == name: return i, p
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
    
    while True:
        if not room['deck']: room['deck'] = make_deck()
        card = room['deck'].pop()
        if card['color'] != 'wild':
            room['discard'].append(card)
            room['current_color'] = card['color']
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
        if not room['deck']: refill_deck(room)
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
    if not name or max_p < 2 or max_p > 8: return redirect('/')
    code = create_room(name, max_p)
    session['name'] = name
    session['room'] = code
    session['is_host'] = True
    return redirect(f'/room/{code}')

@app.route('/join', methods=['POST'])
def join():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip()
    if not name or not code: return redirect('/')
    room = get_room(code)
    if not room: return redirect('/?error=notfound')
    
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
    if not room: return redirect('/')
    return render_template_string(HTML_TEMPLATE, page='game', player_name=session['name'], room_code=code)

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
    socketio.emit('game_state', build_game_state(room), room=code)

@socketio.on('start_game')
def on_start_game(data):
    code = data.get('code')
    name = data.get('name')
    room = get_room(code)
    if not room or room['host'] != name or len(room['players']) < 2 or room['state'] != 'waiting': return
    random.shuffle(room['players'])
    deal_cards(room)
    room['state'] = 'playing'
    room['current_player_idx'] = 0
    add_chat(room, 'النظام', '🎮 بدأت اللعبة! حظاً موفقاً للجميع', 'system')
    room['last_action'] = f"بدأت اللعبة! دور {room['players'][0]['name']}"
    for p in room['players']:
        socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('play_card')
def on_play_card(data):
    code = data.get('code')
    card_id = data.get('card_id')
    chosen_color = data.get('chosen_color')
    room = get_room(code)
    if not room or room['state'] != 'playing': return

    idx, player = find_player(room, sid=request.sid)
    if idx is None or idx != room['current_player_idx']:
        emit('error', {'msg': 'ليس دورك!'})
        return

    card, card_pos = None, None
    for i, c in enumerate(player['hand']):
        if c['id'] == card_id:
            card, card_pos = c, i
            break
    if not card: return

    top_card = room['discard'][-1]

    if room['draw_stack'] > 0:
        if card['value'] not in ['draw2', 'wild4'] or card['value'] != top_card['value']:
            emit('error', {'msg': f'يجب عليك سحب {room["draw_stack"]} ورقة أو اللعب بورقة مماثلة!'})
            return

    if room['draw_stack'] == 0 and not card_playable(card, top_card, room['current_color']):
        emit('error', {'msg': 'لا يمكنك لعب هذه الورقة!'})
        return

    if card['color'] == 'wild' and not chosen_color:
        emit('choose_color', {})
        return
    if card['color'] == 'wild' and chosen_color:
        card['chosen_color'] = chosen_color

    player['hand'].pop(card_pos)
    room['discard'].append(card)
    room['current_color'] = chosen_color if card['color'] == 'wild' else card['color']

    label = card_label(card)
    if card['color'] == 'wild' and chosen_color: label += f' → {COLOR_AR.get(chosen_color, chosen_color)}'
    
    room['last_action'] = f'{player["name"]} لعب {label}'
    add_chat(room, 'النظام', f'🃏 {player["name"]} لعب: {label}', 'system')

    if check_winner(room, idx):
        add_chat(room, 'النظام', f'🏆 {player["name"]} فاز باللعبة!', 'system')
        for p in room['players']:
            socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])
        return

    if len(player['hand']) == 1:
        player['uno'] = True
        add_chat(room, 'النظام', f'🔴 {player["name"]} قال UNO!', 'system')
    else:
        player['uno'] = False

    n = len(room['players'])
    if card['value'] == 'skip':
        next_player(room); next_player(room)
        skipped = room['players'][(idx + room['direction']) % n]['name']
        add_chat(room, 'النظام', f'⛔ {skipped} تم تخطيه!', 'system')
    elif card['value'] == 'reverse':
        room['direction'] *= -1
        next_player(room) if n > 2 else (next_player(room), next_player(room))
        add_chat(room, 'النظام', f'🔄 تغير اتجاه اللعبة!', 'system')
    elif card['value'] in ['draw2', 'wild4']:
        room['draw_stack'] += 2 if card['value'] == 'draw2' else 4
        next_player(room)
        if not any(c['value'] == card['value'] for c in room['players'][room['current_player_idx']]['hand']):
            draw_card(room, room['current_player_idx'], room['draw_stack'])
            add_chat(room, 'النظام', f'😱 {room["players"][room["current_player_idx"]]["name"]} سحب {room["draw_stack"]} أوراق!', 'system')
            room['draw_stack'] = 0
            next_player(room)
    else:
        next_player(room)

    for p in room['players']:
        socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('draw_card')
def on_draw_card(data):
    code = data.get('code')
    room = get_room(code)
    if not room or room['state'] != 'playing': return
    idx, player = find_player(room, sid=request.sid)
    if idx is None or idx != room['current_player_idx']: return

    count = room['draw_stack'] if room['draw_stack'] > 0 else 1
    draw_card(room, idx, count)
    room['draw_stack'] = 0
    add_chat(room, 'النظام', f'📥 {player["name"]} سحب {count} ورقة', 'system')
    room['last_action'] = f'{player["name"]} سحب {count} ورقة'
    next_player(room)
    for p in room['players']: socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('call_uno')
def on_call_uno(data):
    room = get_room(data.get('code'))
    if not room: return
    idx, player = find_player(room, sid=request.sid)
    if idx is not None and len(player['hand']) == 1:
        player['uno'] = True
        add_chat(room, 'النظام', f'🔴 {player["name"]} قال UNO!', 'system')
        for p in room['players']: socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

@socketio.on('catch_uno')
def on_catch_uno(data):
    room = get_room(data.get('code'))
    if not room: return
    catcher_idx, catcher = find_player(room, sid=request.sid)
    target_name = data.get('target')
    for i, p in enumerate(room['players']):
        if p['name'] == target_name and len(p['hand']) == 1 and not p.get('uno', False):
            draw_card(room, i, 2)
            add_chat(room, 'النظام', f'🎯 {catcher["name"]} مسك {target_name} بدون UNO! {target_name} سحب ورقتين', 'system')
            for pl in room['players']: socketio.emit('game_state', build_game_state(room, pl['sid']), room=pl['sid'])
            return

@socketio.on('send_chat')
def on_send_chat(data):
    msg = data.get('message', '').strip()
    room = get_room(data.get('code'))
    if msg and room:
        add_chat(room, data.get('name'), msg, 'player')
        socketio.emit('new_chat', room['chat'][-1], room=room['code'])

@socketio.on('restart_game')
def on_restart(data):
    room = get_room(data.get('code'))
    if room and room['host'] == data.get('name'):
        room.update({'state':'waiting', 'winner':None, 'draw_stack':0, 'direction':1, 'current_player_idx':0, 'last_action':''})
        for p in room['players']: p.update({'hand':[], 'uno':False})
        add_chat(room, 'النظام', '🔄 إعادة تشغيل اللعبة...', 'system')
        for p in room['players']: socketio.emit('game_state', build_game_state(room, p['sid']), room=p['sid'])

# ========== WebRTC Voice Chat (Mesh Network) ==========
@socketio.on('voice_join')
def on_voice_join(data):
    emit('voice_user_joined', {'sid': request.sid, 'name': data.get('name')}, room=data.get('code'), include_self=False)

@socketio.on('webrtc_signal')
def on_webrtc_signal(data):
    if data.get('target_sid'): emit('webrtc_signal', data, room=data.get('target_sid'))

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

# ========== HTML/CSS/JS (Professional UI) ==========

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>UNO Pro Online</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;900&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root {
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155; --border: #475569;
  --accent: #ef4444; --accent2: #f59e0b; --text: #f8fafc; --text2: #cbd5e1;
  --red: #ef4444; --green: #10b981; --blue: #3b82f6; --yellow: #f59e0b; --wild: #111;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Tajawal', sans-serif; user-select: none; }
body { background: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }

/* Home Page */
.home-page { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); }
.home-logo { font-size: 5rem; font-weight: 900; background: linear-gradient(135deg, var(--red), var(--yellow)); -webkit-background-clip: text; color: transparent; filter: drop-shadow(0 0 20px rgba(239,68,68,0.5)); margin-bottom: 20px; }
.card-box { background: var(--surface); padding: 30px; border-radius: 20px; width: 100%; max-width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid var(--border); margin-bottom: 20px;}
.input-field { width: 100%; padding: 15px; margin-bottom: 15px; background: var(--bg); border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-size: 16px; }
.input-field:focus { outline: none; border-color: var(--blue); }
.btn { width: 100%; padding: 15px; border: none; border-radius: 10px; font-size: 18px; font-weight: 900; cursor: pointer; transition: 0.3s; color: white; margin-bottom: 10px;}
.btn-primary { background: linear-gradient(135deg, var(--red), #b91c1c); }
.btn-secondary { background: linear-gradient(135deg, var(--blue), #1d4ed8); }
.btn:active { transform: scale(0.98); }

/* Game Layout */
.game-page { display: flex; flex-direction: column; height: 100%; width: 100%; }
.header { background: var(--surface); padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); z-index: 10; }
.main-content { display: flex; flex: 1; overflow: hidden; position: relative; }
.play-zone { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }

/* Sidebar (Chat/Players) */
.sidebar { width: 320px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; transition: 0.3s; z-index: 100; }
@media (max-width: 768px) { .sidebar { position: absolute; right: 0; top: 0; bottom: 0; transform: translateX(100%); } .sidebar.show { transform: translateX(0); box-shadow: -10px 0 30px rgba(0,0,0,0.8); } }
.tabs { display: flex; border-bottom: 1px solid var(--border); }
.tab { flex: 1; padding: 15px; text-align: center; cursor: pointer; font-weight: bold; color: var(--text2); border-bottom: 2px solid transparent; }
.tab.active { color: var(--yellow); border-color: var(--yellow); }
.tab-content { display: none; flex: 1; flex-direction: column; overflow: hidden; }
.tab-content.active { display: flex; }

/* Voice & Chat */
.voice-bar { padding: 10px; background: var(--surface2); display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--border); }
.mic-btn { width: 45px; height: 45px; border-radius: 50%; border: none; background: var(--surface); color: white; font-size: 20px; cursor: pointer; transition: 0.3s; display: flex; justify-content: center; align-items: center; }
.mic-btn.active { background: var(--green); box-shadow: 0 0 15px var(--green); animation: pulse 1s infinite; }
@keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
.voice-users { flex: 1; display: flex; flex-wrap: wrap; gap: 5px; font-size: 12px; }
.v-user { background: var(--bg); padding: 5px 10px; border-radius: 20px; display: flex; align-items: center; gap: 5px;}
.v-user.speaking { color: var(--green); font-weight: bold; border: 1px solid var(--green); }
.chat-box { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.msg { background: var(--surface2); padding: 8px 12px; border-radius: 10px; font-size: 14px; width: fit-content; max-width: 90%; }
.msg.sys { background: transparent; color: var(--text2); font-size: 12px; text-align: center; align-self: center; border: 1px dashed var(--border); }
.msg-sender { color: var(--yellow); font-size: 11px; font-weight: bold; margin-bottom: 2px; }
.chat-input { display: flex; padding: 10px; background: var(--surface); border-top: 1px solid var(--border); }
.chat-input input { flex: 1; padding: 10px; border-radius: 8px; border: none; background: var(--bg); color: white; outline: none; }

/* Players List */
.players-list { padding: 10px; overflow-y: auto; flex: 1; }
.pl-row { display: flex; align-items: center; gap: 10px; background: var(--surface2); padding: 10px; border-radius: 10px; margin-bottom: 8px; border: 1px solid transparent; }
.pl-row.active { border-color: var(--yellow); background: rgba(245, 158, 11, 0.1); }
.pl-avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-weight: bold; font-size: 18px; }
.pl-info { flex: 1; }
.pl-name { font-weight: bold; font-size: 15px; }
.pl-status { font-size: 12px; color: var(--text2); }
.uno-badge { background: var(--red); padding: 2px 6px; border-radius: 5px; font-size: 10px; font-weight: bold; }
.catch-btn { background: var(--red); border: none; color: white; padding: 5px 10px; border-radius: 5px; cursor: pointer; font-weight: bold; font-size: 12px; }

/* Top Strip (Mini Players) */
.top-players { display: flex; gap: 10px; padding: 10px; overflow-x: auto; background: var(--surface); border-bottom: 1px solid var(--border); scrollbar-width: none; }
.mini-p { display: flex; align-items: center; gap: 8px; background: var(--bg); padding: 5px 15px 5px 5px; border-radius: 30px; border: 1px solid var(--border); }
.mini-p.active { border-color: var(--yellow); box-shadow: 0 0 10px rgba(245,158,11,0.2); }
.mini-avatar { width: 25px; height: 25px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 12px; font-weight: bold; }

/* Table Area */
.table-area { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; position: relative; gap: 20px; }
.turn-banner { background: rgba(245, 158, 11, 0.2); color: var(--yellow); padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 16px; animation: bounce 2s infinite; border: 1px solid var(--yellow); text-align: center;}
@keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }

.cards-center { display: flex; align-items: center; gap: 30px; }
.color-ring { width: 50px; height: 50px; border-radius: 50%; border: 4px solid white; transition: 0.3s; box-shadow: 0 0 20px rgba(0,0,0,0.5); }

/* UNO Cards Styling (Original Look) */
.uno-card {
  width: 90px; height: 135px; border-radius: 10px; border: 6px solid white;
  display: flex; justify-content: center; align-items: center; position: relative;
  box-shadow: 2px 5px 15px rgba(0,0,0,0.4); overflow: hidden;
}
.uno-card.deck { background: linear-gradient(135deg, #1e3a5f, #111); cursor: pointer; transition: 0.2s; }
.uno-card.deck:hover { transform: scale(1.05); }
.uno-card.deck .center-oval { width: 85%; height: 60%; background: var(--red); border-radius: 50%; transform: rotate(-30deg); display: flex; justify-content: center; align-items: center; border: 2px solid var(--yellow); }
.uno-card.deck .center-txt { font-weight: 900; font-size: 18px; color: var(--yellow); transform: rotate(30deg); text-shadow: 1px 1px 0 #000; }

.uno-card.face-up { animation: dropIn 0.3s ease-out; }
@keyframes dropIn { from { transform: scale(1.5) translateY(-50px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }

.center-oval { position: absolute; width: 85%; height: 65%; background: white; border-radius: 50%; transform: rotate(-25deg); display: flex; justify-content: center; align-items: center; box-shadow: inset 0 0 8px rgba(0,0,0,0.3); }
.center-val { font-size: 3rem; font-weight: 900; transform: rotate(25deg); text-shadow: 2px 2px 0px rgba(0,0,0,0.3); letter-spacing: -2px; }
.c-red { background: var(--red); } .c-red .center-val { color: var(--red); }
.c-green { background: var(--green); } .c-green .center-val { color: var(--green); }
.c-blue { background: var(--blue); } .c-blue .center-val { color: var(--blue); }
.c-yellow { background: var(--yellow); } .c-yellow .center-val { color: var(--yellow); }
.c-wild { background: linear-gradient(135deg, #8e44ad, #e74c3c, #f1c40f, #2980b9); } .c-wild .center-val { color: #222; text-shadow: none; font-size: 2rem; }
.corner { position: absolute; font-size: 1.2rem; font-weight: 900; text-shadow: 1px 1px 0 #000; }
.corner.tl { top: 2px; left: 4px; }
.corner.br { bottom: 2px; right: 4px; transform: rotate(180deg); }
.stack-badge { position: absolute; top: -15px; right: -15px; background: var(--red); padding: 5px 10px; border-radius: 50%; font-weight: bold; border: 2px solid white; font-size: 14px; z-index: 10; box-shadow: 0 4px 10px rgba(0,0,0,0.5);}

/* Hand Area */
.hand-area { background: var(--surface); border-top: 1px solid var(--border); padding: 15px; display: flex; flex-direction: column; z-index: 5; }
.hand-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.hand-cards { display: flex; gap: 10px; overflow-x: auto; padding: 20px 10px 10px 10px; scrollbar-width: none; }
.hand-card-wrapper { transition: 0.2s; cursor: pointer; }
.hand-card-wrapper:hover { transform: translateY(-25px); z-index: 20; }
.hand-card-wrapper.playable .uno-card { border-color: var(--yellow); box-shadow: 0 0 15px var(--yellow); }
.hand-card-wrapper.disabled { opacity: 0.5; pointer-events: none; }

/* UI Elements */
.action-toast { background: var(--bg); border: 1px solid var(--border); padding: 8px 20px; border-radius: 30px; font-size: 14px; color: var(--text2); }
.mobile-toggle { display: none; position: fixed; bottom: 20px; left: 20px; width: 60px; height: 60px; border-radius: 50%; background: var(--blue); color: white; font-size: 24px; border: none; z-index: 1000; box-shadow: 0 5px 15px rgba(0,0,0,0.5); }
.close-sidebar { display: none; position: absolute; top: 10px; left: 10px; background: var(--red); color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-size: 18px; z-index: 101; }
@media (max-width: 768px) { .mobile-toggle, .close-sidebar { display: flex; justify-content: center; align-items: center; } }

/* Modals */
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center; z-index: 2000; backdrop-filter: blur(5px); }
.modal-box { background: var(--surface); padding: 30px; border-radius: 20px; text-align: center; border: 1px solid var(--border); width: 90%; max-width: 400px;}
.color-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px; }
.c-btn { padding: 20px; border: none; border-radius: 15px; font-size: 18px; font-weight: bold; color: white; cursor: pointer; transition: 0.2s; }
.c-btn:hover { transform: scale(1.05); }

/* Global Toast */
#global-toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: var(--surface2); border: 1px solid var(--border); padding: 12px 25px; border-radius: 30px; font-weight: bold; z-index: 3000; transition: 0.3s; opacity: 0; pointer-events: none; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
</style>
</head>
<body>

{% if page == 'home' %}
<div class="home-page">
    <div class="home-logo">UNO PRO</div>
    <div class="card-box">
        <h2>إنشاء غرفة جديدة</h2>
        <form action="/create" method="POST">
            <input class="input-field" type="text" name="name" placeholder="اسم اللاعب" required maxlength="15">
            <select class="input-field" name="max_players">
                <option value="2">2 لاعبين</option><option value="3">3 لاعبين</option>
                <option value="4" selected>4 لاعبين</option><option value="5">5 لاعبين</option>
                <option value="6">6 لاعبين</option><option value="8">8 لاعبين</option>
            </select>
            <button class="btn btn-primary" type="submit">إنشاء وبدء 🎮</button>
        </form>
    </div>
    <div class="card-box">
        <h2>الانضمام لغرفة</h2>
        <form action="/join" method="POST">
            <input class="input-field" type="text" name="name" placeholder="اسم اللاعب" required maxlength="15">
            <input class="input-field" type="number" name="code" placeholder="كود الغرفة (6 أرقام)" required>
            <button class="btn btn-secondary" type="submit">انضمام للعب ▶</button>
        </form>
    </div>
</div>
{% elif page == 'game' %}
<div class="game-page">
    <div class="header">
        <div style="font-weight: bold; color: var(--text2);">كود الغرفة: <span style="color: var(--yellow); font-size: 1.2rem; letter-spacing: 2px;">{{ room_code }}</span></div>
        <div id="status-badge" style="font-size: 14px; font-weight: bold;">جاري التحميل...</div>
    </div>

    <div class="main-content">
        <div class="play-zone">
            <div class="top-players" id="top-players"></div>

            <div class="table-area">
                <div id="turn-banner" class="turn-banner" style="display: none;">🎯 دورك الآن!</div>
                
                <div id="waiting-screen" style="text-align: center; display: flex; flex-direction: column; gap: 15px; align-items: center;">
                    <h2 style="color: var(--yellow); font-size: 2rem;">غرفة الانتظار</h2>
                    <p style="color: var(--text2);">شارك الكود: <b style="font-size: 1.5rem; color: white;">{{ room_code }}</b></p>
                    <button id="start-btn" class="btn btn-primary" style="display: none; max-width: 250px;" onclick="socket.emit('start_game', {code: ROOM_CODE, name: PLAYER_NAME})">ابدأ اللعبة الآن</button>
                </div>

                <div id="play-screen" class="cards-center" style="display: none;">
                    <div class="uno-card deck" onclick="drawCard()" title="سحب ورقة">
                        <div class="center-oval"><div class="center-txt">UNO</div></div>
                    </div>
                    <div style="position: relative;" id="top-card-container">
                        </div>
                    <div id="color-ring" class="color-ring"></div>
                </div>

                <div id="action-toast" class="action-toast">مرحباً بك في أونو</div>
            </div>

            <div class="hand-area" id="hand-area" style="display: none;">
                <div class="hand-header">
                    <div class="hand-title" id="hand-title">أوراقك</div>
                    <button class="btn btn-primary" style="width: auto; padding: 5px 15px; border-radius: 5px; margin: 0;" onclick="socket.emit('call_uno', {code: ROOM_CODE})">🔴 قول UNO!</button>
                </div>
                <div class="hand-cards" id="hand-cards"></div>
            </div>
        </div>

        <div class="sidebar" id="sidebar">
            <button class="close-sidebar" onclick="document.getElementById('sidebar').classList.remove('show')">✕</button>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('chat')">💬 المحادثة</div>
                <div class="tab" onclick="switchTab('players')">👥 اللاعبون</div>
            </div>
            
            <div class="tab-content active" id="tab-chat">
                <div class="voice-bar">
                    <button class="mic-btn" id="mic-btn" onclick="toggleMic()">🎤</button>
                    <div class="voice-users" id="voice-users">الصوت مغلق</div>
                </div>
                <div class="chat-box" id="chat-box"></div>
                <div class="chat-input">
                    <input type="text" id="chat-input" placeholder="رسالتك..." onkeypress="if(event.key==='Enter') sendChat()">
                    <button class="send-btn" style="background: none; border: none; font-size: 20px; cursor: pointer; margin-right: 10px;" onclick="sendChat()">🚀</button>
                </div>
            </div>

            <div class="tab-content" id="tab-players">
                <div class="players-list" id="players-list"></div>
                <div style="padding: 15px;" id="restart-div" style="display: none;">
                    <button class="btn btn-secondary" onclick="socket.emit('restart_game', {code: ROOM_CODE, name: PLAYER_NAME})">🔄 إعادة اللعبة</button>
                </div>
            </div>
        </div>
        
        <button class="mobile-toggle" onclick="document.getElementById('sidebar').classList.add('show')">💬</button>
    </div>
</div>

<div class="overlay" id="color-modal" style="display: none;">
    <div class="modal-box">
        <h2 style="margin-bottom: 20px;">اختر اللون الجديد</h2>
        <div class="color-grid">
            <button class="c-btn c-red" onclick="chooseColor('red')">أحمر</button>
            <button class="c-btn c-green" onclick="chooseColor('green')">أخضر</button>
            <button class="c-btn c-blue" onclick="chooseColor('blue')">أزرق</button>
            <button class="c-btn c-yellow" onclick="chooseColor('yellow')">أصفر</button>
        </div>
    </div>
</div>

<div class="overlay" id="winner-modal" style="display: none;">
    <div class="modal-box" style="background: linear-gradient(135deg, #1e293b, #0f172a); border-color: var(--yellow);">
        <div style="font-size: 80px; margin-bottom: 10px;">🏆</div>
        <h1 style="color: var(--yellow); margin-bottom: 10px;">الفائز!</h1>
        <h2 id="winner-name" style="margin-bottom: 30px;"></h2>
        <button class="btn btn-primary" onclick="window.location='/'">خروج</button>
    </div>
</div>

<div id="audio-elements" style="display: none;"></div>

<div id="global-toast">رسالة</div>

<script>
const PLAYER_NAME = "{{ player_name }}";
const ROOM_CODE = "{{ room_code }}";
let socket = io();
let gameState = null;
let pendingCard = null;

// Helper: ألوان الشخصيات
function getAvatarColor(name) {
    const colors = ['#ef4444', '#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899'];
    let hash = 0;
    for(let i=0; i<name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
}

function showToast(msg) {
    const t = document.getElementById('global-toast');
    t.innerText = msg;
    t.style.opacity = 1;
    setTimeout(() => t.style.opacity = 0, 3000);
}

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
}

// الاتصال
socket.on('connect', () => {
    socket.emit('join_game', { code: ROOM_CODE, name: PLAYER_NAME });
});
socket.on('disconnect', () => showToast('انقطع الاتصال بالسيرفر!'));

socket.on('game_state', state => {
    gameState = state;
    renderAll();
});

function renderAll() {
    const state = gameState;
    const isHost = state.host === PLAYER_NAME;
    const myIdx = state.viewer_idx;
    const isMyTurn = myIdx === state.current_player_idx;
    
    // الهيدر
    document.getElementById('status-badge').innerText = state.state === 'waiting' ? `في الانتظار (${state.players.length}/${state.max_players})` : (state.state === 'finished' ? 'انتهت اللعبة' : `دور: ${state.players[state.current_player_idx]?.name || ''}`);
    
    // الغرفة / اللعبة
    if(state.state === 'waiting') {
        document.getElementById('waiting-screen').style.display = 'flex';
        document.getElementById('play-screen').style.display = 'none';
        document.getElementById('hand-area').style.display = 'none';
        document.getElementById('start-btn').style.display = (isHost && state.players.length >= 2) ? 'block' : 'none';
    } else {
        document.getElementById('waiting-screen').style.display = 'none';
        document.getElementById('play-screen').style.display = 'flex';
        document.getElementById('hand-area').style.display = 'flex';
        document.getElementById('turn-banner').style.display = isMyTurn ? 'block' : 'none';
    }

    // بناء الورقة على الطاولة
    if(state.top_card) {
        const tc = state.top_card;
        const valMap = {skip:'⊘', reverse:'⇄', draw2:'+2', wild:'🌈', wild4:'+4'};
        let v = valMap[tc.value] || tc.value;
        document.getElementById('top-card-container').innerHTML = `
            <div class="uno-card top-card c-${tc.color === 'wild' ? 'wild' : tc.color}">
                <div class="corner tl">${v}</div>
                <div class="center-oval"><div class="center-val">${v}</div></div>
                <div class="corner br">${v}</div>
            </div>
            ${state.draw_stack > 0 ? `<div class="stack-badge">+${state.draw_stack}</div>` : ''}
        `;
        document.getElementById('color-ring').className = `color-ring c-${state.current_color || 'wild'}`;
    }

    document.getElementById('action-toast').innerText = state.last_action || 'مرحباً في اللعبة';

    // أوراقي
    if(myIdx !== null && state.players[myIdx].hand) {
        const hand = state.players[myIdx].hand;
        document.getElementById('hand-title').innerText = `أوراقك (${hand.length})`;
        const valMap = {skip:'⊘', reverse:'⇄', draw2:'+2', wild:'🌈', wild4:'+4'};
        
        document.getElementById('hand-cards').innerHTML = hand.map(c => {
            const canPlay = isMyTurn && state.state === 'playing' && (
                (state.draw_stack > 0 && ['draw2', 'wild4'].includes(c.value) && c.value === state.top_card.value) ||
                (state.draw_stack === 0 && (c.color === 'wild' || c.color === state.current_color || c.value === state.top_card.value))
            );
            let v = valMap[c.value] || c.value;
            return `
            <div class="hand-card-wrapper ${canPlay ? 'playable' : 'disabled'}" onclick="playCard('${c.id}', ${canPlay})">
                <div class="uno-card hand-card c-${c.color === 'wild' ? 'wild' : c.color}">
                    <div class="corner tl">${v}</div>
                    <div class="center-oval"><div class="center-val">${v}</div></div>
                    <div class="corner br">${v}</div>
                </div>
            </div>`;
        }).join('');
    }

    // شريط اللاعبين المصغر (العلوي)
    document.getElementById('top-players').innerHTML = state.players.map((p, i) => `
        <div class="mini-p ${i === state.current_player_idx ? 'active' : ''}">
            <div class="mini-avatar" style="background:${getAvatarColor(p.name)}; color:white;">${p.name[0]}</div>
            <div style="font-size:12px; font-weight:bold;">${p.name} <span style="color:var(--yellow)">[${p.hand_count}]</span></div>
            ${p.uno ? '<div class="uno-badge">UNO</div>' : ''}
        </div>
    `).join('');

    // قائمة اللاعبين (السيدبار)
    document.getElementById('players-list').innerHTML = state.players.map((p, i) => {
        let catchBtn = (state.state === 'playing' && p.name !== PLAYER_NAME && p.hand_count === 1 && !p.uno) ? 
            `<button class="catch-btn" onclick="socket.emit('catch_uno', {code:ROOM_CODE, target:'${p.name}'})">صيده!</button>` : '';
        return `
        <div class="pl-row ${i === state.current_player_idx ? 'active' : ''}">
            <div class="pl-avatar" style="background:${getAvatarColor(p.name)}; color:white;">${p.name[0]}</div>
            <div class="pl-info">
                <div class="pl-name">${p.name} ${p.name === state.host ? '👑' : ''}</div>
                <div class="pl-status">${p.hand_count} ورقة ${!p.connected ? '(غير متصل)' : ''}</div>
            </div>
            ${p.uno ? '<div class="uno-badge">UNO</div>' : ''}
            ${catchBtn}
        </div>`;
    }).join('');

    document.getElementById('restart-div').style.display = (isHost && state.state !== 'waiting') ? 'block' : 'none';

    // الفائز
    if(state.winner) {
        document.getElementById('winner-modal').style.display = 'flex';
        document.getElementById('winner-name').innerText = state.winner;
    } else {
        document.getElementById('winner-modal').style.display = 'none';
    }
}

// التفاعل
function playCard(id, canPlay) {
    if(!canPlay) return;
    const card = gameState.players[gameState.viewer_idx].hand.find(c => c.id === id);
    if(card.color === 'wild') {
        pendingCard = id;
        document.getElementById('color-modal').style.display = 'flex';
    } else {
        socket.emit('play_card', {code: ROOM_CODE, card_id: id});
    }
}
function chooseColor(c) {
    document.getElementById('color-modal').style.display = 'none';
    if(pendingCard) {
        socket.emit('play_card', {code: ROOM_CODE, card_id: pendingCard, chosen_color: c});
        pendingCard = null;
    }
}
function drawCard() {
    if(gameState.viewer_idx === gameState.current_player_idx) socket.emit('draw_card', {code: ROOM_CODE});
}

// الشات
socket.on('new_chat', msg => {
    const box = document.getElementById('chat-box');
    if(msg.type === 'system') {
        box.innerHTML += `<div class="msg sys">${msg.message}</div>`;
    } else {
        box.innerHTML += `<div class="msg"><div class="msg-sender">${msg.sender}</div>${msg.message}</div>`;
    }
    box.scrollTop = box.scrollHeight;
});
function sendChat() {
    const inp = document.getElementById('chat-input');
    if(inp.value.trim()) socket.emit('send_chat', {code: ROOM_CODE, name: PLAYER_NAME, message: inp.value});
    inp.value = '';
}


// ==========================================
// نظام الصوت الشامل (Mesh WebRTC) للموبايل والـ PC
// ==========================================
let localStream = null;
let micActive = false;
let peerConnections = {};
let voiceUsers = {};
const rtcConfig = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }, { urls: 'stun:stun1.l.google.com:19302' }] };

async function toggleMic() {
    const btn = document.getElementById('mic-btn');
    if (!micActive) {
        try {
            // طلب المايك بقوة
            localStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
            micActive = true;
            btn.classList.add('active');
            
            voiceUsers[socket.id] = { name: PLAYER_NAME, speaking: false };
            renderVoiceBar();
            
            socket.emit('voice_join', { code: ROOM_CODE, name: PLAYER_NAME, sid: socket.id });
            detectSpeaking();
            showToast('المايك يعمل الآن 🎤');
        } catch(err) {
            showToast('يجب إعطاء صلاحية المايك للمتصفح!');
        }
    } else {
        // إغلاق المايك بالكامل
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
        micActive = false;
        btn.classList.remove('active');
        
        Object.keys(peerConnections).forEach(sid => {
            peerConnections[sid].close();
            const aud = document.getElementById('aud_' + sid);
            if(aud) aud.remove();
        });
        peerConnections = {};
        delete voiceUsers[socket.id];
        renderVoiceBar();
        socket.emit('voice_leave', { code: ROOM_CODE, sid: socket.id });
        showToast('المايك مغلق 🔇');
    }
}

socket.on('voice_user_joined', async (data) => {
    if(!micActive || data.sid === socket.id) return;
    voiceUsers[data.sid] = { name: data.name, speaking: false };
    renderVoiceBar();
    
    // إنشاء Offer للشخص الجديد
    const pc = createPC(data.sid, data.name);
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.emit('webrtc_signal', { target_sid: data.sid, sender_sid: socket.id, sender_name: PLAYER_NAME, type: 'offer', sdp: pc.localDescription, code: ROOM_CODE });
});

socket.on('voice_user_left', (data) => {
    if(peerConnections[data.sid]) { peerConnections[data.sid].close(); delete peerConnections[data.sid]; }
    const aud = document.getElementById('aud_' + data.sid); if(aud) aud.remove();
    delete voiceUsers[data.sid];
    renderVoiceBar();
});

socket.on('webrtc_signal', async (data) => {
    if(data.target_sid !== socket.id || !micActive) return;
    
    let pc = peerConnections[data.sender_sid];
    
    if(data.type === 'offer') {
        if(!pc) {
            voiceUsers[data.sender_sid] = { name: data.sender_name, speaking: false };
            renderVoiceBar();
            pc = createPC(data.sender_sid, data.sender_name);
        }
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
        const ans = await pc.createAnswer();
        await pc.setLocalDescription(ans);
        socket.emit('webrtc_signal', { target_sid: data.sender_sid, sender_sid: socket.id, sender_name: PLAYER_NAME, type: 'answer', sdp: pc.localDescription, code: ROOM_CODE });
    } else if(data.type === 'answer' && pc) {
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
    } else if(data.type === 'candidate' && pc && pc.remoteDescription) {
        await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
    }
});

function createPC(sid, name) {
    const pc = new RTCPeerConnection(rtcConfig);
    peerConnections[sid] = pc;
    
    if(localStream) localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
    
    pc.onicecandidate = e => {
        if(e.candidate) socket.emit('webrtc_signal', { target_sid: sid, sender_sid: socket.id, type: 'candidate', candidate: e.candidate, code: ROOM_CODE });
    };
    
    pc.ontrack = e => {
        let aud = document.getElementById('aud_' + sid);
        if(!aud) {
            aud = document.createElement('audio');
            aud.id = 'aud_' + sid;
            aud.autoplay = true;
            aud.playsInline = true;
            document.getElementById('audio-elements').appendChild(aud);
        }
        aud.srcObject = e.streams[0];
        // محاولة إجبار التشغيل في الموبايل
        let playProm = aud.play();
        if(playProm !== undefined) playProm.catch(e => console.log("تحتاج للتفاعل مع الشاشة لتشغيل الصوت"));
    };
    return pc;
}

function detectSpeaking() {
    if(!localStream) return;
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(localStream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    
    function check() {
        if(!micActive) return;
        analyser.getByteFrequencyData(data);
        const vol = data.reduce((a,b)=>a+b,0)/data.length;
        const speaking = vol > 10;
        if(voiceUsers[socket.id] && voiceUsers[socket.id].speaking !== speaking) {
            voiceUsers[socket.id].speaking = speaking;
            renderVoiceBar();
            socket.emit('voice_speaking', { code: ROOM_CODE, sid: socket.id, speaking: speaking });
        }
        requestAnimationFrame(check);
    }
    check();
}

socket.on('voice_speaking_update', data => {
    if(voiceUsers[data.sid]) { voiceUsers[data.sid].speaking = data.speaking; renderVoiceBar(); }
});

function renderVoiceBar() {
    const bar = document.getElementById('voice-users');
    const sids = Object.keys(voiceUsers);
    if(sids.length === 0) { bar.innerHTML = 'اضغط على المايك للتحدث'; return; }
    bar.innerHTML = sids.map(sid => {
        const u = voiceUsers[sid];
        return `<div class="v-user ${u.speaking ? 'speaking' : ''}">${u.speaking ? '🔊' : '🎤'} ${u.name}</div>`;
    }).join('');
}

// ضغطة عشوائية في الشاشة لتفعيل الصوت للموبايلات
document.body.addEventListener('click', () => {
    document.querySelectorAll('audio').forEach(a => {
        if(a.paused) a.play().catch(e=>{});
    });
}, {once: true});

</script>
{% endif %}
</body>
</html>
"""

application = app

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
