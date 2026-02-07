from flask import Flask, render_template
from flask_socketio import SocketIO, join_room, emit
import random
import string
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- قاعدة البيانات ---
LOCATIONS = {
    "أماكن عامة": ["المطار", "المستشفى", "الجامعة", "المترو", "المول"],
    "أماكن ترفيهية": ["السينما", "الملاهي", "القهوة", "الجيم", "الساحل"],
    "أماكن غريبة": ["الغواصة", "محطة فضاء", "بيت رعب", "السجن", "قاعدة عسكرية"]
}

PUNISHMENTS = [
    "ارقص دقيقة بدون موسيقى", "اعترف بآخر كذبة", 
    "اتصل بحد وقوله بحبك واقفل", "اشرب كوباية ميه كاملة", 
    "خلي اللي جنبك يضربك بالقلم"
]

# --- تخزين حالة اللعبة (State Management) ---
rooms = {}

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('create_room')
def on_create(data):
    code = generate_code()
    rooms[code] = {
        'players': {},      # {socket_id: name}
        'scores': {},       # {name: score}
        'state': 'lobby',   # lobby, playing, voting, result
        'game_data': {},    # location, gecko_name
        'votes': {}         # {voter_name: suspect_name}
    }
    join_room(code)
    emit('room_created', {'code': code, 'name': data['name']})

@socketio.on('join_room')
def on_join(data):
    code = data['code'].upper()
    name = data['name']
    
    if code in rooms:
        if name in rooms[code]['players'].values():
            emit('error', {'msg': 'الاسم موجود بالفعل!'})
        else:
            join_room(code)
            rooms[code]['players'][request.sid] = name # ربط الاسم بالـ ID
            rooms[code]['scores'].setdefault(name, 0)
            
            # إرسال تحديث لكل الناس في الغرفة
            player_list = list(rooms[code]['players'].values())
            emit('update_players', {'players': player_list}, room=code)
            emit('join_success', {'code': code, 'is_host': len(player_list)==1})
    else:
        emit('error', {'msg': 'الغرفة غير موجودة'})

@socketio.on('start_game')
def on_start(data):
    code = data['code']
    room = rooms.get(code)
    
    if room and len(room['players']) >= 3:
        # 1. إعداد اللعبة
        cat = random.choice(list(LOCATIONS.keys()))
        loc = random.choice(LOCATIONS[cat])
        players_list = list(room['players'].values())
        gecko = random.choice(players_list)
        
        room['game_data'] = {'location': loc, 'category': cat, 'gecko': gecko}
        room['state'] = 'playing'
        room['votes'] = {} # تصفير التصويت

        # 2. إرسال الأدوار (كل واحد يعرف دوره بس)
        for pid, pname in room['players'].items():
            role = 'gecko' if pname == gecko else 'human'
            info = "أنت البرص 🦎" if role == 'gecko' else f"المكان: {loc}"
            emit('game_started', {
                'role': role,
                'info': info,
                'category': cat,
                'duration': 60 * 5 # 5 دقائق
            }, room=pid) # إرسال خاص
        
        # 3. إرسال تايمر عام
        emit('start_timer', {'seconds': 300}, room=code)

@socketio.on('submit_vote')
def on_vote(data):
    code = data['code']
    voter = data['voter']
    suspect = data['suspect']
    room = rooms.get(code)
    
    if room and room['state'] == 'playing':
        room['votes'][voter] = suspect
        total_players = len(room['players'])
        current_votes = len(room['votes'])
        
        # تحديث الحالة للكل (فلان صوت)
        emit('vote_update', {
            'voter': voter, 
            'count': current_votes, 
            'total': total_players
        }, room=code)

        # لو الكل صوت، ننهي اللعبة ونفرز الأصوات
        if current_votes == total_players:
            calculate_results(code)

def calculate_results(code):
    room = rooms[code]
    votes = room['votes']
    gecko = room['game_data']['gecko']
    
    # حساب أكثر شخص حصل على تصويت
    vote_counts = {}
    for suspect in votes.values():
        vote_counts[suspect] = vote_counts.get(suspect, 0) + 1
    
    # من هو المشتبه به الرئيسي؟
    top_suspect = max(vote_counts, key=vote_counts.get)
    
    winner = ""
    msg = ""
    
    if top_suspect == gecko:
        winner = "Humans"
        msg = f"مبروك! قفشتوا البرص ({gecko}) 👮‍♂️"
    else:
        winner = "Gecko"
        msg = f"البرص فاز! ({gecko}) هرب والناس شكت في ({top_suspect}) 🦎"

    emit('game_over', {
        'winner': winner,
        'msg': msg,
        'gecko_name': gecko,
        'votes_summary': vote_counts
    }, room=code)
    
    room['state'] = 'result'

@socketio.on('request_punishment')
def on_punish(data):
    # كود العقاب كما هو
    punishment = random.choice(PUNISHMENTS)
    img = random.randint(1, 7)
    emit('show_punishment', {'text': punishment, 'img': f"{img}.jpeg"}, room=data['code'])

@socketio.on('reset_game')
def on_reset(data):
    code = data['code']
    if code in rooms:
        rooms[code]['state'] = 'lobby'
        rooms[code]['votes'] = {}
        emit('reset_to_lobby', {}, room=code)

from flask import request # نسينا استدعاء request فوق

if __name__ == '__main__':
    socketio.run(app, debug=True)
