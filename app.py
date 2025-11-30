import sqlite3
import os
import jdatetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your-very-secret-key-here'

# --- تنظیمات Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- داده‌های برنامه ---
PROVINCE_UNITS = {
    "همدان": ["همدان", "ملایر", "تویسرکان", "اسدآباد", "مرکز بهار", "مرکز کبودرآهنگ", "مرکز رزن", "مرکز قروه در گزین", "مرکز سامن"],
    "مرکزی": ["اراک", "ساوه", "آشتیان", "تفرش", "نراق", "کمیجان", "مرکز خنداب", "خمین", "محلات", "دلیجان", "زرندیه", "مرکز جاسب", "مرکز مهاجران", "مرکز شازند", "مرکز آستانه", "فراهان"],
    "کردستان": ["سنندج", "سقز", "مریوان", "قروه", "بیجار", "مرکز بانه"],
    "کرمانشاه": ["کرمانشاه", "اسلام آباد غرب", "کنگاور", "صحنه", "مرکز روانسر", "مرکز هرسین", "گیلانغرب", "مرکز قصر شیرین", "مرکز سنقر کلیایی"],
    "لرستان": ["واحد خرم آباد", "واحد بروجرد", "واحد الیگودرز", "واحد دورود"]
}
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
YEARS = [str(y) for y in range(1400, 1411)]

# --- مدل کاربر ---
class User(UserMixin):
    def __init__(self, id, username, password_hash, display_name):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.display_name = display_name

users = { 1: User(1, 'admin', generate_password_hash('password'), 'مدیر سیستم') }

@login_manager.user_loader
def load_user(user_id): return users.get(int(user_id))

# --- توابع دیتابیس ---
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def ensure_db_exists():
    if not os.path.exists('database.db'):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            province TEXT NOT NULL,
            unit_name TEXT NOT NULL,
            month TEXT NOT NULL,
            year TEXT NOT NULL,
            staff_payment TEXT,
            faculty_payment TEXT,
            arrears_payment TEXT,
            submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_by TEXT
        )
        ''')
        conn.commit()
        conn.close()
ensure_db_exists()

def to_persian_number(s):
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    s = str(s)
    return s.translate(str.maketrans("0123456789", persian_digits))

# --- مسیرهای برنامه ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']
        user = next((u for u in users.values() if u.username == username), None)
        if user and check_password_hash(user.password_hash, password):
            login_user(user); flash('با موفقیت وارد شدید.', 'success'); return redirect(url_for('index'))
        else: flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); flash('با موفقیت خارج شدید.', 'info'); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    filter_province = request.args.get('province', ''); filter_month = request.args.get('month', ''); filter_year = request.args.get('year', '1404')
    query = 'SELECT * FROM reports WHERE 1=1'; params = []
    if filter_province: query += ' AND province = ?'; params.append(filter_province)
    if filter_month: query += ' AND month = ?'; params.append(filter_month)
    if filter_year: query += ' AND year = ?'; params.append(filter_year)
    query += ' ORDER BY year DESC, month DESC, submission_date DESC'
    reports = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('index.html', reports=reports, months=MONTHS, years=YEARS,
                           selected_province=filter_province, selected_month=filter_month, selected_year=filter_year,
                           provinces=PROVINCE_UNITS.keys(), to_persian_number=to_persian_number)

@app.route('/add')
@login_required
def add_report():
    return render_template('add_report.html', months=MONTHS, years=YEARS, provinces=PROVINCE_UNITS.keys())

# مسیر ویرایش
@app.route('/edit/<int:report_id>')
@login_required
def edit_report(report_id):
    conn = get_db_connection()
    report = conn.execute('SELECT * FROM reports WHERE id = ?', (report_id,)).fetchone()
    conn.close()
    if report is None:
        flash('گزارش یافت نشد.', 'danger')
        return redirect(url_for('index'))
    return render_template('add_report.html', report=report, months=MONTHS, years=YEARS, provinces=PROVINCE_UNITS.keys())

# مسیر ثبت (هم برای جدید و هم برای ویرایش)
@app.route('/submit', methods=['POST'])
@login_required
def submit():
    report_id = request.form.get('report_id') # دریافت آیدی در حالت ویرایش
    province = request.form['province']; unit_name = request.form['unit_name']; month = request.form['month']; year = request.form['year']
    staff_payment = request.form['staff_payment']; faculty_payment = request.form['faculty_payment']; arrears_payment = request.form['arrears_payment']

    if province and unit_name and month and year:
        conn = get_db_connection()
        if report_id: # حالت ویرایش
            conn.execute('UPDATE reports SET province = ?, unit_name = ?, month = ?, year = ?, staff_payment = ?, faculty_payment = ?, arrears_payment = ? WHERE id = ?',
                        (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, report_id))
            flash('گزارش با موفقیت ویرایش شد.', 'success')
        else: # حالت ثبت جدید
            conn.execute('INSERT INTO reports (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, submitted_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, current_user.display_name))
            flash('گزارش با موفقیت ثبت شد.', 'success')
        conn.commit(); conn.close()
        return redirect(url_for('index'))
    return "لطفاً فیلدهای ضروری را پر کنید.", 400

# مسیر حذف
@app.route('/delete/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM reports WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()
    flash('گزارش با موفقیت حذف شد.', 'info')
    return redirect(url_for('index'))

# مسیر حذف گروهی
@app.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete():
    report_ids = request.form.getlist('report_ids')
    if not report_ids:
        flash('هیچ گزارشی برای حذف انتخاب نشده است.', 'warning')
        return redirect(url_for('index'))
    
    placeholders = ','.join('?' for _ in report_ids)
    conn = get_db_connection()
    conn.execute(f'DELETE FROM reports WHERE id IN ({placeholders})', report_ids)
    conn.commit()
    conn.close()
    flash(f'{to_persian_number(len(report_ids))} گزارش با موفقیت حذف شدند.', 'info')
    return redirect(url_for('index'))


@app.route('/get_units/<province>')
@login_required
def get_units(province):
    units = PROVINCE_UNITS.get(province, [])
    return jsonify(units)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)