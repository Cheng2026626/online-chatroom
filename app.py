from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, send
import mysql.connector
import bcrypt
from db_config import DB_CONFIG
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123456'  # 用于 session 加密
socketio = SocketIO(app, cors_allowed_origins="*")


# ========== 数据库连接函数 ==========
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ========== 页面路由 ==========
@app.route('/')
def index():
    return render_template('index.html')


# ========== 注册 API ==========
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    nickname = data.get('nickname')

    if not username or not password or not nickname:
        return jsonify({'success': False, 'message': '请填写完整信息'})

    # 加密密码
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, nickname) VALUES (%s, %s, %s)",
            (username, hashed.decode('utf-8'), nickname)
        )
        conn.commit()
        return jsonify({'success': True, 'message': '注册成功'})
    except mysql.connector.IntegrityError:
        return jsonify({'success': False, 'message': '用户名已存在'})
    finally:
        cursor.close()
        conn.close()


# ========== 登录 API ==========
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        session['user_id'] = user['id']
        session['nickname'] = user['nickname']
        return jsonify({'success': True, 'message': '登录成功', 'nickname': user['nickname']})
    else:
        return jsonify({'success': False, 'message': '用户名或密码错误'})


# ========== 获取当前用户信息 ==========
@app.route('/api/user/info', methods=['GET'])
def get_user_info():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, username, nickname, created_at FROM users WHERE id = %s",
        (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user:
        # 手动格式化时间
        if user['created_at']:
            user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify({'success': True, 'user': user})
    else:
        return jsonify({'success': False, 'message': '用户不存在'})

# ========== 修改昵称 ==========
@app.route('/api/user/nickname', methods=['POST'])
def update_nickname():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.get_json()
    new_nickname = data.get('nickname')

    if not new_nickname or len(new_nickname) > 50:
        return jsonify({'success': False, 'message': '昵称不能为空且不能超过50个字符'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET nickname = %s WHERE id = %s", (new_nickname, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    # 更新 session 中的昵称
    session['nickname'] = new_nickname

    return jsonify({'success': True, 'message': '昵称修改成功', 'nickname': new_nickname})

# ========== 获取历史消息 ==========
@app.route('/api/messages', methods=['GET'])
def get_messages():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT nickname, content, created_at FROM messages ORDER BY created_at LIMIT 100")
    messages = cursor.fetchall()

    cursor.close()
    conn.close()

    # 格式化时间
    for msg in messages:
        msg['created_at'] = msg['created_at'].strftime('%H:%M:%S')

    return jsonify({'success': True, 'messages': messages})


# ========== WebSocket 聊天 ==========
@socketio.on('send_message')
def handle_message(data):
    content = data.get('content')
    nickname = session.get('nickname')
    user_id = session.get('user_id')

    if not nickname or not user_id:
        emit('error', {'message': '请先登录'})
        return

    # 保存到数据库
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, nickname, content) VALUES (%s, %s, %s)",
        (user_id, nickname, content)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # 广播消息给所有连接的客户端
    emit('new_message', {
        'nickname': nickname,
        'content': content,
        'created_at': datetime.now().strftime('%H:%M:%S')
    }, broadcast=True)


# ========== 运行 ==========
if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)