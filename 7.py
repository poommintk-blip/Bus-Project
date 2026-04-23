from flask import Flask, render_template, request, redirect, url_for, flash
import requests # สำหรับส่งข้อมูลหรือเรียกใช้ API ภายนอก

app = Flask(name)
app.config['SECRET_KEY'] = 'sut_bus_secure_key'

#มมติฐานข้อมูลผู้ใช้ (ในงานจริงควรดึงจาก Database)
USER_DB = {
    "saharatkhemin@gmail.com": "7410"
}

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    # 1. ตรวจสอบข้อมูล Login ในระบบของเราก่อน
    if email in USER_DB and USER_DB[email] == password:
        # 2. หากผ่าน ให้จำลองการส่งข้อมูลการเข้าสู่ระบบไปยัง Server SUT (หรือดึงข้อมูลรถเมล์)
        # ตัวอย่างการส่ง Request ไปยัง API ของรถเมล์ (ตามภาพที่คุณเคยส่งมา)
        try:
            # นี่คือจุดที่คุณจะเอาโค้ด fetch_new_token() มาประยุกต์ใช้
            # flash('เชื่อมต่อกับระบบ SUT BUS สำเร็จ')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการเชื่อมต่อ Server: {e}')
            return redirect(url_for('home'))
    else:
        flash('Email หรือรหัสผ่านไม่ถูกต้อง')
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    return "เข้าร่วมระบบ SUT BUS เรียบร้อยแล้ว - กำลังแสดงตารางรถเมล์..."

if name == 'main':
    app.run(debug=True)