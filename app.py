from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from models import Tab, User
from db import db
import psycopg2
import sys
from datetime import datetime
from markupsafe import Markup, escape
import re
import os

print("=" * 50)
print("[START] SONGegwer")
print("=" * 50)

# 1. Проверяем PostgreSQL
try:
    print("Подключаемся к PostgreSQL...")
    conn = psycopg2.connect(
        host="localhost",
        user="postgres",
        password="1234",
        port="5432"
    )
    
    conn.autocommit = True
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'songegwer'")
    if not cursor.fetchone():
        print("Создаем базу 'songegwer'...")
        cursor.execute("CREATE DATABASE songegwer")
        print("[OK] База создана")
    else:
        print("[OK] База уже существует")
    
    cursor.close()
    conn.close()
    print("[OK] PostgreSQL готов!")
    
except Exception as e:
    print(f"[ERROR] Ошибка PostgreSQL: {e}")
    sys.exit(1)

# 2. Запускаем Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-metal-edition-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:1234@localhost:5432/songegwer'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB

db.init_app(app)

# Ensure upload folder exists
os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)

# Inject current user into templates
@app.context_processor
def inject_current_user():
    user = None
    if session.get('user_id'):
        try:
            user = User.query.get(session.get('user_id'))
        except Exception:
            user = None
    # also expose set of favorite tab ids for current user to templates for fast checks
    fav_ids = set()
    try:
        if user:
            # user.favorites may be a dynamic relationship; get ids
            fav_ids = set([t.id for t in user.favorites.all()])
    except Exception:
        fav_ids = set()

    # also provide a small preview list of favorite items for the header
    fav_preview = []
    try:
        if user:
            fav_preview = user.favorites.order_by(Tab.created_at.desc()).limit(8).all()
    except Exception:
        fav_preview = []

    return dict(current_user=user, current_user_fav_ids=fav_ids, current_user_favs_preview=fav_preview)


# ========== TEMPLATE FILTERS ==========
@app.template_filter('highlight_tab')
def highlight_tab(tabtext):
    """Convert raw tab text into HTML with lightweight highlighting.
    - Wrap numbers (frets) in .tab-num
    - Wrap measure separators '|' in .tab-bar
    - Wrap '^' and '>' accents in .tab-accent
    Returns safe Markup.
    """
    if not tabtext:
        return ''

    # Normalize newlines
    s = tabtext.replace('\r\n', '\n')
    # Escape everything first
    s = escape(s)

    # We want to transform the raw escaped text in one pass so replacements don't touch
    # tags that we insert. Use a single regex and a function so we can: highlight accents,
    # multi-digit frets, single-digit frets, and replace '|' with a bar and measure counter.
    measure_counter = {'n': 0}

    pattern = re.compile(r"(\d{2,})|(\d)|(\^|>|~|b|p|h)|(\|)")

    def repl(m):
        # group1: multi-digit
        if m.group(1):
            return f"<span class=\"tab-num multi\">{m.group(1)}</span>"
        # group2: single-digit
        if m.group(2):
            return f"<span class=\"tab-num\">{m.group(2)}</span>"
        # group3: accents
        if m.group(3):
            return f"<span class=\"tab-accent\">{m.group(3)}</span>"
        # group4: measure bar
        if m.group(4):
            measure_counter['n'] += 1
            return f"<span class=\"tab-bar\">|</span><span class=\"measure-num\">{measure_counter['n']}</span>"
        return m.group(0)

    s = pattern.sub(repl, s)

    # Keep newlines
    s = s.replace('\n', '\n')

    return Markup(s)

# Вспомогательная функция для определения длины
def get_song_length(content):
    """Определяет длину песни по количеству строк"""
    lines = len(content.strip().split('\n'))
    if lines > 100:
        return 'LONG', 'length-LONG'
    elif lines > 50:
        return 'MEDIUM', 'length-MEDIUM'
    else:
        return 'SHORT', 'length-SHORT'

# ========== ГЛАВНАЯ СТРАНИЦА ==========
@app.route("/")
def home():
    """Главная страница - список песен"""
    # Получаем все песни
    tabs = Tab.query.order_by(Tab.created_at.desc()).all()
    
    # Добавляем информацию о длине для каждой песни
    for tab in tabs:
        tab.length_label, tab.length_class = get_song_length(tab.content)
    
    return render_template('index.html', tabs=tabs)

# ========== ПОИСК ==========
@app.route("/search", methods=['GET', 'POST'])
def search():
    """Поиск песен"""
    query = ""
    results = []
    
    # Получаем query из GET или POST
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
    else:
        query = request.args.get('query', '').strip()
    
    if query:
        # Ищем по названию и исполнителю
        results = Tab.query.filter(
            (Tab.title.ilike(f'%{query}%')) | 
            (Tab.artist.ilike(f'%{query}%'))
        ).order_by(Tab.created_at.desc()).all()
        
        for tab in results:
            tab.length_label, tab.length_class = get_song_length(tab.content)
    
    return render_template('search.html', query=query, results=results)

# ========== АККАУНТ ==========
@app.route("/account")
def account():
    """Страница аккаунта"""
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        # fetch user's tabs
        user_tabs = Tab.query.filter_by(user_id=user.id).order_by(Tab.created_at.desc()).all()
        # followers / following lists
        try:
            followers = user.followers.order_by(User.username).all()
        except Exception:
            followers = []
        try:
            following = user.following.order_by(User.username).all()
        except Exception:
            following = []
        # following ids for quick checks
        try:
            following_ids = set([u.id for u in user.following.all()])
        except Exception:
            following_ids = set()
    else:
        user_tabs = []
        followers = []
        following = []
        following_ids = set()
    return render_template('account.html', user=user, user_tabs=user_tabs, followers=followers, following=following, following_ids=following_ids)

# ========== РЕГИСТРАЦИЯ ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not username or not email or not password:
            flash('Заполните все поля!', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Пользователь с таким именем или email уже существует', 'error')
            return redirect(url_for('register'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('account'))

    return render_template('register.html')

# ========== ВХОД ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if not user or not user.check_password(password):
            flash('Неверные учетные данные', 'error')
            return redirect(url_for('login'))

        session['user_id'] = user.id
        flash('Вход выполнен', 'success')
        return redirect(url_for('account'))

    return render_template('login.html')

# ========== ВЫХОД ==========
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из аккаунта', 'success')
    return redirect(url_for('home'))


# ========== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ==========
@app.route('/account/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash('Необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not email:
            flash('Имя пользователя и email не могут быть пустыми', 'error')
            return redirect(url_for('edit_profile'))

        # Check duplicate username/email
        other_user = User.query.filter(User.id != user.id).filter((User.username == username) | (User.email == email)).first()
        if other_user:
            flash('Имя пользователя или email уже используются', 'error')
            return redirect(url_for('edit_profile'))

        user.username = username
        user.email = email
        if password:
            user.set_password(password)

        db.session.commit()
        flash('Профиль обновлён', 'success')
        return redirect(url_for('account'))

    return render_template('account_edit.html', user=user)


@app.route('/account/delete', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        flash('Необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('home'))
    # require password confirmation
    pwd = request.form.get('confirm_password', '')
    confirmed = request.form.get('confirm_deletion')
    if not confirmed:
        flash('Подтвердите удаление, установив галочку.', 'error')
        return redirect(url_for('account'))

    if not pwd:
        flash('Введите пароль для подтверждения удаления.', 'error')
        return redirect(url_for('account'))

    if not user.check_password(pwd):
        flash('Неверный пароль. Удаление аккаунта отменено.', 'error')
        return redirect(url_for('account'))

    # remove avatar file
    try:
        if user.avatar_filename:
            prev_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], user.avatar_filename)
            if os.path.exists(prev_path):
                os.remove(prev_path)
    except Exception:
        pass

    # delete user's tabs and user record
    try:
        Tab.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Ошибка при удалении аккаунта', 'error')
        return redirect(url_for('account'))

    session.pop('user_id', None)
    flash('Аккаунт удалён', 'success')
    return redirect(url_for('home'))

# ========== ЗАГРУЗКА АВАТАРА ==========
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ('png', 'jpg', 'jpeg', 'gif')

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    if 'user_id' not in session:
        flash('Необходимо войти в систему', 'error')
        return redirect(url_for('login'))

    file = request.files.get('avatar')
    if not file or file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('account'))

    if not allowed_file(file.filename):
        flash('Недопустимый формат файла', 'error')
        return redirect(url_for('account'))

    from werkzeug.utils import secure_filename
    # Create unique filename to avoid collisions
    filename = file.filename
    ext = filename.rsplit('.', 1)[1].lower()
    user = User.query.get(session['user_id'])
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    new_filename = f'user_{user.id}_{timestamp}.{ext}'
    new_filename = secure_filename(new_filename)
    save_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], new_filename)
    # Save file
    file.save(save_path)

    # Remove previous avatar if exists
    try:
        if user.avatar_filename:
            prev_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], user.avatar_filename)
            if os.path.exists(prev_path):
                os.remove(prev_path)
    except Exception:
        pass

    user.avatar_filename = new_filename
    db.session.commit()
    flash('Аватар загружен', 'success')
    return redirect(url_for('account'))

# ========== ДОБАВЛЕНИЕ ПЕСНИ ==========
@app.route("/create", methods=['GET', 'POST'])
def create_tab():
    """Создание нового таба"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        artist = request.form.get('artist', '').strip()
        
        # Получаем строки табулатуры
        string_e = request.form.get('string_e', '').strip()
        string_b = request.form.get('string_b', '').strip()
        string_g = request.form.get('string_g', '').strip()
        string_d = request.form.get('string_d', '').strip()
        string_a = request.form.get('string_a', '').strip()
        string_E = request.form.get('string_E', '').strip()
        
        if not title or not artist:
            flash('Заполните название и исполнителя!', 'error')
        else:
        # description field removed — we only store the six string lines
            tab_content = f"""e {string_e}
B {string_b}
G {string_g}
D {string_d}
A {string_a}
E {string_E}"""
            
            # parse optional BPM/speed
            speed_val = request.form.get('speed_bpm', '').strip()
            try:
                speed_val_i = int(speed_val) if speed_val else 120
            except Exception:
                speed_val_i = 120

            new_tab = Tab(
                title=title,
                artist=artist,
                content=tab_content,
                speed_bpm=speed_val_i
            )
            # Attach to current user if logged in
            if 'user_id' in session:
                try:
                    new_tab.user_id = int(session['user_id'])
                except Exception:
                    pass
            else:
                new_tab.user_id = None  # Для анонимных пользователей
            
            db.session.add(new_tab)
            db.session.commit()
            
            flash(f'Таб "{title}" успешно добавлен!', 'success')
            return redirect(url_for('view_tab', id=new_tab.id))
    
    return render_template('create.html')

# ========== ПРОСМОТР ПЕСНИ ==========
@app.route("/tab/<int:id>")
def view_tab(id):
    """Просмотр одного таба"""
    tab = Tab.query.get_or_404(id)
    length_label, length_class = get_song_length(tab.content)
    
    # if the tab has an owner, ensure the user object is available to the template
    owner = None
    try:
        owner = tab.user
    except Exception:
        owner = None

    return render_template('tab.html', tab=tab, length_label=length_label, length_class=length_class, owner=owner)


@app.route('/user/<int:user_id>')
def user_profile(user_id):
    """Public user profile page: show username, avatar (if any) and their public tabs."""
    user = User.query.get_or_404(user_id)
    # load user's tabs (most recent first)
    try:
        user_tabs = user.tabs if user.tabs is not None else []
        # sort by created_at desc if attribute exists
        user_tabs = sorted(user_tabs, key=lambda t: t.created_at or 0, reverse=True)
    except Exception:
        user_tabs = []

    # compute lengths for display
    for t in user_tabs:
        try:
            t.length_label, t.length_class = get_song_length(t.content)
        except Exception:
            t.length_label, t.length_class = ('?', '')

    # compute simple counts
    try:
        followers_count = user.followers.count() if hasattr(user, 'followers') else 0
    except Exception:
        followers_count = 0
    try:
        following_count = user.following.count() if hasattr(user, 'following') else 0
    except Exception:
        following_count = 0
    try:
        favorites_count = user.favorites.count() if hasattr(user, 'favorites') else 0
    except Exception:
        favorites_count = 0

    # current_user following state
    current_user_obj = None
    current_is_following = False
    if session.get('user_id'):
        try:
            current_user_obj = User.query.get(session.get('user_id'))
            if current_user_obj and current_user_obj.id != user.id:
                current_is_following = current_user_obj.following.filter_by(id=user.id).first() is not None
        except Exception:
            current_is_following = False

    return render_template('user_profile.html', user=user, user_tabs=user_tabs,
                           followers_count=followers_count,
                           following_count=following_count,
                           favorites_count=favorites_count,
                           current_is_following=current_is_following)


@app.route('/toggle_follow/<int:user_id>', methods=['POST'])
def toggle_follow(user_id):
    # require login
    if 'user_id' not in session:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'login_required'}), 401
        flash('Войдите в систему, чтобы следить за пользователями', 'error')
        return redirect(url_for('login'))

    current = User.query.get(session['user_id'])
    target = User.query.get_or_404(user_id)

    if current.id == target.id:
        flash('Вы не можете подписаться на самого себя', 'error')
        return redirect(request.referrer or url_for('user_profile', user_id=user_id))

    # check current following state
    is_following = current.following.filter_by(id=target.id).first() is not None

    if is_following:
        # unfollow
        try:
            current.following.remove(target)
            db.session.commit()
            fav_state = False
            flash(f'Вы отписались от {target.username}', 'success')
        except Exception:
            db.session.rollback()
            flash('Не удалось отписаться — попробуйте снова', 'error')
    else:
        # follow
        try:
            current.following.append(target)
            db.session.commit()
            fav_state = True
            flash(f'Вы подписались на {target.username}', 'success')
        except Exception:
            db.session.rollback()
            flash('Не удалось подписаться — попробуйте снова', 'error')

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'following': fav_state, 'user_id': user_id})

    return redirect(request.referrer or url_for('user_profile', user_id=user_id))


@app.route('/export_all')
def export_all():
    tabs = Tab.query.order_by(Tab.created_at.desc()).all()
    return render_template('export_all.html', tabs=tabs)


# ========== FAVORITES ==========
@app.route('/toggle_favorite/<int:id>', methods=['POST'])
def toggle_favorite(id):
    if 'user_id' not in session:
        # If AJAX request, return JSON error otherwise redirect to login
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'login_required'}), 401
        flash('Необходимо войти в систему, чтобы добавлять в избранное', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    tab = Tab.query.get_or_404(id)

    # check if favorite exists
    try:
        exists = user.favorites.filter_by(id=tab.id).first()
    except Exception:
        # fallback: query manually
        exists = Tab.query.filter(Tab.id==tab.id).first() if False else None

    if exists:
        # remove
        user.favorites.remove(tab)
        db.session.commit()
        fav_state = False
    else:
        user.favorites.append(tab)
        db.session.commit()
        fav_state = True

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'favorited': fav_state, 'tab_id': tab.id})

    return redirect(request.referrer or url_for('home'))


@app.route('/favorites')
def favorites():
    if 'user_id' not in session:
        flash('Войдите, чтобы просматривать избранные', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    # get all favorited tabs
    tabs = user.favorites.order_by(Tab.created_at.desc()).all()
    for tab in tabs:
        tab.length_label, tab.length_class = get_song_length(tab.content)

    return render_template('favorites.html', tabs=tabs)

# ========== РЕДАКТИРОВАНИЕ ==========
@app.route("/edit/<int:id>", methods=['GET', 'POST'])
def edit_tab(id):
    """Редактирование таба"""
    tab = Tab.query.get_or_404(id)
    
    # Only allow edit if owner (if tab has owner)
    if tab.user_id and session.get('user_id') and int(session.get('user_id')) != int(tab.user_id):
        flash('У вас нет прав на редактирование этого таба', 'error')
        return redirect(url_for('view_tab', id=tab.id))

    if request.method == 'POST':
        tab.title = request.form.get('title', tab.title).strip()
        tab.artist = request.form.get('artist', tab.artist).strip()
        
        # Получаем строки табулатуры
        string_e = request.form.get('string_e', '').strip()
        string_b = request.form.get('string_b', '').strip()
        string_g = request.form.get('string_g', '').strip()
        string_d = request.form.get('string_d', '').strip()
        string_a = request.form.get('string_a', '').strip()
        string_E = request.form.get('string_E', '').strip()
        
        # description removed — assemble content only from six strings
        tab_content = f"""e {string_e}
    B {string_b}
    G {string_g}
    D {string_d}
    A {string_a}
    E {string_E}"""
        
        # update BPM if provided
        speed_val = request.form.get('speed_bpm', '').strip()
        try:
            speed_val_i = int(speed_val) if speed_val else tab.speed_bpm or 120
        except Exception:
            speed_val_i = tab.speed_bpm or 120

        tab.content = tab_content
        tab.speed_bpm = speed_val_i
        
        db.session.commit()
        flash(f'Таб "{tab.title}" обновлен!', 'success')
        return redirect(url_for('view_tab', id=tab.id))
    
    return render_template('edit.html', tab=tab)

# ========== УДАЛЕНИЕ ==========
@app.route("/delete/<int:id>", methods=['POST'])
def delete_tab(id):
    """Удаление таба"""
    tab = Tab.query.get_or_404(id)
    # Only allow delete for owner
    if tab.user_id and (not session.get('user_id') or int(session.get('user_id')) != int(tab.user_id)):
        flash('У вас нет прав на удаление этого таба', 'error')
        return redirect(url_for('home'))

    title = tab.title
    
    db.session.delete(tab)
    db.session.commit()
    
    flash(f'Таб "{title}" удален!', 'success')
    return redirect(url_for('home'))

# ========== API (для мобильных приложений) ==========
@app.route("/api/tabs", methods=['GET'])
def get_tabs_api():
    """API: Получить все табы"""
    tabs = Tab.query.all()
    result = []
    for t in tabs:
        length_label, _ = get_song_length(t.content)
        result.append({
            "id": t.id,
            "title": t.title,
            "artist": t.artist,
            "difficulty": (t.difficulty if hasattr(t, 'difficulty') and t.difficulty is not None else 3),
            "length": length_label,
            "created_at": t.created_at.isoformat() if t.created_at else None
        })
    return jsonify(result)

       
        
        

# ========== ФУНКЦИЯ ВОССТАНОВЛЕНИЯ БАЗЫ ДАННЫХ ==========
def repair_database():
    """Восстанавливает структуру базы данных при ошибках"""
    with app.app_context():
        print("Восстанавливаем структуру базы данных...")
        try:
            # Удаляем все таблицы
            db.drop_all()
            print("[OK] Старые таблицы удалены")
            
            # Создаем таблицы заново
            db.create_all()
            print("[OK] Таблицы созданы заново")
            
          
            
        except Exception as e:
            print(f"[ERROR] Ошибка восстановления: {e}")

# ========== ЗАПУСК СЕРВЕРА ==========
if __name__ == "__main__":
    print("\nСоздаем таблицы в базе данных...")
    try:
        with app.app_context():
            db.create_all()
        print("[OK] Таблицы созданы успешно!")
        
       
        
        print("\n" + "=" * 50)
        print("[START] СЕРВЕР ЗАПУЩЕН: http://127.0.0.1:5000")
        print("=" * 50)
        
    except Exception as e:
        print(f"[ERROR] Ошибка при создании таблиц: {e}")
        print("\nПытаемся восстановить базу данных...")
        repair_database()
    
    app.run(debug=True, port=5000)