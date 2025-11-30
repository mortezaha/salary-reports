import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# این کلید مخفی برای مدیریت نشست‌ها (sessions) ضروری است
app.secret_key = 'your-very-secret-key-here' 

# --- تنظیمات Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # اگر کاربر وارد نبود، او را به صفحه لاگین بفرست

# --- داده‌های برنامه ---
PROVINCE_UNITS = { # ... (بدون تغییر) }
    "همدان": ["همدان", "ملایر", "تویسرکان", "اسدآباد", "مرکز بهار", "مرکز کبودرآهنگ", "مرکز رزن", "مرکز قروه در گزین", "مرکز سامن"],
    "مرکزی": ["اراک", "ساوه", "آشتیان", "تفرش", "نراق", "کمیجان", "مرکز خنداب", "خمین", "محلات", "دلیجان", "زرندیه", "مرکز جاسب", "مرکز مهاجران", "مرکز شازند", "مرکز آستانه", "فراهان"],
    "کردستان": ["سنندج", "سقز", "مریوان", "قروه", "بیجار", "مرکز بانه"],
    "کرمانشاه": ["کرمانشاه", "اسلام آباد غرب", "کنگاور", "صحنه", "مرکز روانسر", "مرکز هرسین", "گیلانغرب", "مرکز قصر شیرین", "مرکز سنقر کلیایی"],
    "لرستان": ["واحد خرم آباد", "واحد بروجرد", "واحد الیگودرز", "واحد دورود"]
}
MONTHS = [ # ... (بدون تغییر) ]
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# --- مدل کاربر ساده ---
# در یک برنامه واقعی، این اطلاعات باید از دیتابیس خوانده شوند
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# یک کاربر نمونه برای ورود (شما می‌توانید کاربران بیشتری اضافه کنید)
# نام کاربری: admin , رمز عبور: password
users = {
    1: User(1, 'admin', generate_password_hash('password'))
}

@login_manager.user_loader
def load_user(user_id):
    return users.get(int(user_id))

# --- توابع دیتابیس و مسیرهای برنامه ---
def get_db_connection(): # ... (بدون تغییر)
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db(): # ... (بدون تغییر)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS reports')
    cursor.execute('''
    CREATE TABLE reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        province TEXT NOT NULL,
        unit_name TEXT NOT NULL,
        month TEXT NOT NULL,
        year TEXT NOT NULL,
        staff_payment TEXT,
        faculty_payment TEXT,
        submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

# مسیر ورود
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # جستجوی کاربر
        user = next((u for u in users.values() if u.username == username), None)
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('با موفقیت وارد شدید.', 'success')
            return redirect(url_for('index'))
        else:
            flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
            
    return render_template('login.html')

# مسیر خروج
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('با موفقیت خارج شدید.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required # این مسیر فقط برای کاربران وارد شده قابل دسترسی است
def index():
    # ... (کد قبلی اینجا بدون تغییر قرار می‌گیرد)
    conn = get_db_connection()
    filter_province = request.args.get('province', '')
    filter_month = request.args.get('month', '')
    filter_year = request.args.get('year', '1404')
    query = 'SELECT * FROM reports WHERE 1=1'
    params = []
    if filter_province: query += ' AND province = ?'; params.append(filter_province)
    if filter_month: query += ' AND month = ?'; params.append(filter_month)
    if filter_year: query += ' AND year = ?'; params.append(filter_year)
    query += ' ORDER BY year DESC, month DESC, submission_date DESC'
    reports = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('index.html', reports=reports, months=MONTHS, 
                           selected_province=filter_province, selected_month=filter_month, selected_year=filter_year,
                           provinces=PROVINCE_UNITS.keys())

@app.route('/add')
@login_required # این مسیر هم محافظت می‌شود
def add_report():
    return render_template('add_report.html', months=MONTHS, provinces=PROVINCE_UNITS.keys())

@app.route('/submit', methods=['POST'])
@login_required # این مسیر هم محافظت می‌شود
def submit():
    # ... (کد قبلی اینجا بدون تغییر قرار می‌گیرد)
    province = request.form['province']; unit_name = request.form['unit_name']; month = request.form['month']; year = request.form['year']
    staff_payment = request.form['staff_payment']; faculty_payment = request.form['faculty_payment']
    if province and unit_name and month and year:
        conn = get_db_connection()
        conn.execute('INSERT INTO reports (province, unit_name, month, year, staff_payment, faculty_payment) VALUES (?, ?, ?, ?, ?, ?)', (province, unit_name, month, year, staff_payment, faculty_payment))
        conn.commit(); conn.close()
        return redirect(url_for('index'))
    return "لطفاً فیلدهای ضروری را پر کنید.", 400

@app.route('/get_units/<province>')
@login_required # این مسیر هم محافظت می‌شود
def get_units(province):
    units = PROVINCE_UNITS.get(province, [])
    return jsonify(units)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)