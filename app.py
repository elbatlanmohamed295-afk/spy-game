import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__, template_folder='.', static_folder='.')
app.config['SECRET_KEY'] = 'el_3watly_secret'

# الحل هنا: زيادة حجم البيانات المسموح بها إلى 10 ميجابايت لاستقبال الصور
socketio = SocketIO(app, max_http_buffer_size=10000000, cors_allowed_origins="*")

# قائمة العقابات
PUNISHMENTS = [
    "ارقص بلدي لمدة دقيقة قدامنا 💃",
    "قلد صوت فرخة بتبيض 🐔",
    "اعمل نفسك مذيع واشرح ماتش كورة خيالي بصوت عالي 🎤",
    "ابعت فويس نوت لجروب العيلة غني فيه 'أنا الفرخة واحنا الكتاكيت' 🐥",
    "امشي مشية عسكرية في الأوضة رايح جاي 💂‍♂️",
    "قل قصيدة شعر ارتجالية في حب 'طبق الكشري' 🍲",
    "اعمل 10 ضغط حالاً 💪",
    "قلد صوت حد من الموجودين وخلينا نحزر مين 🎭",
    "احكي موقف محرج حصلك في المواصلات 🚌",
    "سف على نفسك لمدة 30 ثانية 😂"
]

# بيانات اللعبة
GAME_DATA = {
    "أماكن 🌍": ["القهوة", "قسم الشرطة", "موقف الميكروباص", "الساحل الشرير", "الأهرامات", "مول العرب", "امتحان ثانوية عامة", "فرح شعبي", "عربية كبدة", "المترو", "الحلاق", "الجيم"],
    "أكلات 🥘": ["كشري", "محشي كرنب", "مكرونة بشاميل", "فسيخ ورنجة", "ساندوتش فول", "طعمية سخنة", "حواوشي", "فتة كوارع", "اندومي", "سميط وجبنة"],
    "مشاهير 🌟": ["محمد رمضان", "عادل إمام", "أحمد السقا", "ويجز", "حسن شاكوش", "محمد صلاح", "ياسمين صبري", "بيج رامي", "أحمد حلمي"],
    "ملابس 👕": ["فانلة حمالات", "شبشب زنوبة", "ترنج اديداس", "بدلة فرح", "كلسون شتوي", "شراب مخروم", "جلابية بيتي", "طقم العيد"],
    "أشياء منزلية 🏠": ["النيش", "كيس فيه أكياس", "ريموت ملفوف بلاستر", "طاسة القلي السوداء", "شبشب الحمام", "الراوتر", "مشترك كهرباء بايظ", "طقم كوبايات الشاي"]
}

rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('join')
def on_join(data):
    username = data.get('username')
    room = data.get('room')
    userImg = data.get('userImg', '') # استقبال الصورة
    sid = request.sid
    
    if not username or not room:
        return

    join_room(room)
    
    if room not in rooms:
        rooms[room] = {'players': [], 'current_spy': None}
    
    # حذف اللاعب القديم إذا كان موجوداً بنفس الاسم
    rooms[room]['players'] = [p for p in rooms[room]['players'] if p['name'] != username]
    
    # إضافة اللاعب الجديد
    rooms[room]['players'].append({'sid': sid, 'name': username, 'img': userImg})
    
    emit_player_list(room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    for room in list(rooms.keys()): # استخدام list لتجنب خطأ التعديل أثناء الدوران
        if room in rooms:
            rooms[room]['players'] = [p for p in rooms[room]['players'] if p['sid'] != sid]
            emit_player_list(room)

def emit_player_list(room):
    if room in rooms:
        # استخدام .get لتجنب خطأ KeyError إذا كانت البيانات قديمة
        players_data = [{'name': p['name'], 'img': p.get('img', '')} for p in rooms[room]['players']]
        count = len(players_data)
        emit('update_player_list', {'players': players_data, 'count': count}, to=room)

@socketio.on('start_game')
def on_start(data):
    room = data['room']
    category = data.get('category', 'أماكن 🌍')
    
    if room in rooms:
        players = rooms[room]['players']
        if len(players) < 3:
            emit('error_msg', 'يا كابتن لازم تكونوا 3 على الأقل!', to=request.sid)
            return

        items_list = GAME_DATA.get(category, GAME_DATA['أماكن 🌍'])
        chosen_item = random.choice(items_list)
        spy_player = random.choice(players)
        
        rooms[room]['current_spy'] = spy_player['name']
        
        for player in players:
            info = {
                'category': category,
                'is_spy': (player == spy_player)
            }
            if player == spy_player:
                info['role'] = 'الجاسوس 🦎'
                info['item'] = '؟؟؟؟؟'
            else:
                info['role'] = 'بني آدم 👷'
                info['item'] = chosen_item
            
            emit('game_started', info, to=player['sid'])

@socketio.on('reveal_spy')
def on_reveal(data):
    room = data['room']
    # التأكد من أن الغرفة والجاسوس موجودين لتجنب الأخطاء
    if room in rooms and rooms[room].get('current_spy'):
        real_spy = rooms[room]['current_spy']
        punishment = random.choice(PUNISHMENTS)
        emit('show_result', {'spy': real_spy, 'punishment': punishment}, to=room)

@socketio.on('reset_game')
def on_reset(data):
    room = data['room']
    emit('reset_view', to=room)

if __name__ == '__main__':
    # تشغيل السيرفر

    socketio.run(app, debug=True, host='0.0.0.0')
