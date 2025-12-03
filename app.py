import sqlite3
import os
import jdatetime
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-very-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # محدودیت حجم آپلود 16 مگابایت

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

# --- مدل کاربر (برای Flask-Login) ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['id'])
        self.username = user_data['username']
        self.password_hash = user_data['password_hash']
        self.display_name = user_data['display_name']
        self.role = user_data['role']

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(user_data)
    return None

# --- توابع دیتابیس ---
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def ensure_db_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')
    
    # جدول گزارش‌ها
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
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
    
    # ایجاد کاربر ادمین پیش‌فرض اگر وجود نداشته باشد
    admin_user = cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
    if not admin_user:
        cursor.execute('INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)',
                       ('admin', generate_password_hash('password'), 'مدیر سیستم', 'admin'))
    
    conn.commit()
    conn.close()

ensure_db_exists()

def to_persian_number(s):
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    s = str(s)
    return s.translate(str.maketrans("0123456789", persian_digits))

# --- توابع بررسی سطح دسترسی ---
def is_admin():
    return current_user.is_authenticated and current_user.role == 'admin'

def is_editor_or_admin():
    return current_user.is_authenticated and current_user.role in ['admin', 'editor']

# --- مسیرهای برنامه ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user_data and check_password_hash(user_data['password_hash'], password):
            login_user(User(user_data))
            flash('با موفقیت وارد شدید.', 'success')
            return redirect(url_for('index'))
        else:
            flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('با موفقیت خارج شدید.', 'info')
    return redirect(url_for('login'))

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
    
    reports_db = conn.execute(query, params).fetchall()
    
    # تبدیل تاریخ به شمسی و اعداد به فارسی
    reports = []
    for report in reports_db:
        report_list = dict(report)
        if report_list['submission_date']:
            g_date = jdatetime.datetime.strptime(report_list['submission_date'], '%Y-%m-%d %H:%M:%S')
            report_list['submission_date_persian'] = g_date.strftime('%Y/%m/%d %H:%M')
        reports.append(report_list)

    conn.close()
    
    # <<<< توجه به این خط >>>
    # اینجا ما خود تابع را ارسال می‌کنیم، نه نتیجه آن را
    return render_template('index.html', reports=reports, months=MONTHS, years=YEARS,
                           selected_province=filter_province, selected_month=filter_month, selected_year=filter_year,
                           provinces=PROVINCE_UNITS.keys(), to_persian_number=to_persian_number, 
                           is_admin=is_admin, is_editor_or_admin=is_editor_or_admin) # <-- این خط صحیح است

@app.route('/add')
@login_required
def add_report():
    return render_template('add_report.html', months=MONTHS, years=YEARS, provinces=PROVINCE_UNITS.keys())

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

@app.route('/submit', methods=['POST'])
@login_required
def submit():
    report_id = request.form.get('report_id')
    province = request.form['province']; unit_name = request.form['unit_name']; month = request.form['month']; year = request.form['year']
    staff_payment = request.form['staff_payment']; faculty_payment = request.form['faculty_payment']; arrears_payment = request.form['arrears_payment']
    if province and unit_name and month and year:
        conn = get_db_connection()
        if report_id:
            conn.execute('UPDATE reports SET province = ?, unit_name = ?, month = ?, year = ?, staff_payment = ?, faculty_payment = ?, arrears_payment = ? WHERE id = ?',
                        (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, report_id))
            flash('گزارش با موفقیت ویرایش شد.', 'success')
        else:
            conn.execute('INSERT INTO reports (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, submitted_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, current_user.display_name))
            flash('گزارش با موفقیت ثبت شد.', 'success')
        conn.commit(); conn.close()
        return redirect(url_for('index'))
    return "لطفاً فیلدهای ضروری را پر کنید.", 400

@app.route('/delete/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM reports WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()
    flash('گزارش با موفقیت حذف شد.', 'info')
    return redirect(url_for('index'))

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

# --- مسیرهای مدیریت کاربران (فقط ادمین) ---
@app.route('/users')
@login_required
def manage_users():
    if not is_admin(): return redirect(url_for('index'))
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, display_name, role FROM users').fetchall()
    conn.close()
    return render_template('manage_users.html', users=users, to_persian_number=to_persian_number)

@app.route('/add_user')
@login_required
def add_user():
    if not is_admin(): return redirect(url_for('index'))
    return render_template('user_form.html', user=None, roles=['admin', 'editor', 'viewer'])

@app.route('/edit_user/<int:user_id>')
@login_required
def edit_user(user_id):
    if not is_admin(): return redirect(url_for('index'))
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user is None:
        flash('کاربر یافت نشد.', 'danger')
        return redirect(url_for('manage_users'))
    return render_template('user_form.html', user=user, roles=['admin', 'editor', 'viewer'])

@app.route('/submit_user', methods=['POST'])
@login_required
def submit_user():
    if not is_admin(): return redirect(url_for('index'))
    user_id = request.form.get('user_id')
    username = request.form['username']; display_name = request.form['display_name']; role = request.form['role']; password = request.form['password']
    if username and display_name and role:
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)',
                       (username, generate_password_hash(password), display_name, role))
            flash('کاربر با موفقیت اضافه شد.', 'success')
        except sqlite3.IntegrityError:
            flash('نام کاربری تکراری است.', 'danger')
        finally:
            conn.close()
    return redirect(url_for('manage_users'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not is_admin(): return redirect(url_for('index'))
    if str(user_id) == current_user.id: flash('نمی‌توانید حساب خود را حذف کنید.', 'warning'); return redirect(url_for('manage_users'))
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('کاربر با موفقیت حذف شد.', 'info')
    return redirect(url_for('manage_users'))

# --- مسیرهای پشتیبان‌گیری و بازیابی ---
@app.route('/backup')
@login_required
def backup_db():
    if not is_admin(): return redirect(url_for('index'))
    return send_file('database.db', as_attachment=True, download_name=f'backup_{jdatetime.datetime.now().strftime("%Y-%m-%d")}.db')

@app.route('/restore', methods=['POST'])
@login_required
def restore_db():
    if not is_admin(): return redirect(url_for('index'))
    if 'file' not in request.files: flash('فایلی انتخاب نشده است.', 'danger'); return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '': flash('فایلی انتخاب نشده است.', 'danger'); return redirect(url_for('index'))
    if file and file.filename.endswith('.db'):
        file.save('database.db')
        flash('پشتیبان با موفقیت بازیابی شد.', 'success')
    else:
        flash('فایل نامعتبر است. فقط فایل‌های .db مجاز هستند.', 'danger')
    return redirect(url_for('index'))

# --- مسیر آپلود گروهی ---
@app.route('/bulk_upload')
@login_required
def bulk_upload_page():
    if not is_editor_or_admin(): return redirect(url_for('index'))
    return render_template('bulk_upload.html')

@app.route('/process_bulk_upload', methods=['POST'])
@login_required
def process_bulk_upload():
    if not is_editor_or_admin(): return redirect(url_for('index'))
    if 'file' not in request.files: flash('فایلی انتخاب نشده است.', 'danger'); return redirect(url_for('bulk_upload_page'))
    file = request.files['file']
    if file.filename == '': flash('فایلی انتخاب نشده است.', 'danger'); return redirect(url_for('bulk_upload_page'))
    
    try:
        df = pd.read_excel(file)
        conn = get_db_connection()
        for index, row in df.iterrows():
            conn.execute('INSERT INTO reports (province, unit_name, month, year, staff_payment, faculty_payment, arrears_payment, submitted_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (row['استان'], row['واحد/مرکز'], row['ماه'], row['سال'], row['درصد کارکنان'], row['درصد هیات علمی'], row['درصد معوقات'], current_user.display_name))
        conn.commit()
        conn.close()
        flash(f'{to_persian_number(len(df))} گزارش با موفقیت آپلود شدند.', 'success')
    except Exception as e:
        flash(f'خطا در پردازش فایل: {e}', 'danger')
    return redirect(url_for('index'))

# --- مسیر گزارش معوقات ---
@app.route('/arrears_report')
@login_required
def arrears_report():
    if not is_editor_or_admin(): return redirect(url_for('index'))
    conn = get_db_connection()
    reports_db = conn.execute("SELECT * FROM reports WHERE arrears_payment IS NOT NULL AND arrears_payment != '100%' ORDER BY province, unit_name, year DESC, month DESC").fetchall()
    conn.close()
    
    reports = []
    for report in reports_db:
        report_list = dict(report)
        if report_list['submission_date']:
            g_date = jdatetime.datetime.strptime(report_list['submission_date'], '%Y-%m-%d %H:%M:%S')
            report_list['submission_date_persian'] = g_date.strftime('%Y/%m/%d %H:%M')
        reports.append(report_list)

    return render_template('arrears_report.html', reports=reports, to_persian_number=to_persian_number)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)