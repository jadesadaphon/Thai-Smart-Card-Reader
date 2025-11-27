# Thai Smart Card WebSocket Reader (Tray App)

แอป Windows แบบถาดระบบ (System Tray) ที่อ่านข้อมูลบัตรประชาชนไทยผ่าน PC/SC และให้บริการผ่าน WebSocket API เพื่อส่งข้อมูลบัตรไปยังแอปของคุณแบบเรียลไทม์ พร้อมรองรับการอ่านรูปถ่ายบนบัตร และควบคุมด้วยตัวแปรสภาพแวดล้อม

## คุณสมบัติหลัก
- รอพบเครื่องอ่านบัตร → รอเสียบบัตร → อ่านและส่งข้อมูลบัตร (รวมรูป) → รอถอดบัตร → ทำงานวนต่อเนื่อง
- ส่งอีเวนต์ WebSocket ถึงลูกค้าทุกตัวที่เชื่อมต่อพร้อมกัน
- แจ้งสถานะเครื่องอ่าน (`reader_status`), ข้อมูลบัตร (`card_data`), และข้อผิดพลาด (`error`)
- Tray icon, ทำงานแบบไม่มี Console, ป้องกันการรันซ้ำ (single instance)
- แจ้งเตือนตอนเริ่มทำงาน/เปิดซ้ำ พร้อม URL ของ WebSocket
- Build เป็น .exe ด้วย PyInstaller ได้ง่าย

## ข้อกำหนดระบบ
- Windows 10/11
- Python 3.9 ขึ้นไป (แนะนำ 3.10/3.11)
- PC/SC Service ทำงานอยู่ (Windows Smart Card Service)
- เครื่องอ่านบัตรประชาชนไทยที่รองรับ

## ติดตั้ง
```cmd
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## การใช้งาน (โหมดพัฒนา)
รันแอปถาดระบบที่โฮสต์ WebSocket server:
```cmd
venv\Scripts\activate
python ThaiSmartCardReader.py
```
เมื่อเริ่มทำงาน จะมีการแจ้งเตือนชื่อเครื่องและ URL เช่น `ws://127.0.0.1:8765`

หยุดโปรแกรม: คลิกขวาที่ Tray icon แล้วเลือก Exit

## WebSocket API
- ค่าเริ่มต้น: `ws://127.0.0.1:8765`
- โปรโตคอลข้อความ: JSON (UTF-8)

### ประเภทข้อความ
- `reader_status`: สถานะเครื่องอ่าน
  ```json
  {
    "type": "reader_status",
    "status": "connected" | "disconnected",
    "reader_name": "..."
  }
  ```
- `card_data`: ข้อมูลบัตร (ส่งทันทีหลังอ่านสำเร็จ)
  - โครงสร้างตัวอย่าง (เขตข้อมูลอาจมีมากกว่านี้ขึ้นกับบัตร/เวอร์ชัน):
  ```json
  {
    "type": "card_data",
    "cid": "1234567890123",
    "title_th": "นาย",
    "first_name_th": "สมชาย",
    "last_name_th": "ใจดี",
    "title_en": "Mr.",
    "first_name_en": "Somchai",
    "last_name_en": "Jaidee",
    "gender_th": "ชาย",
    "gender_en": "Male",
    "dob_th": "01/01/2530",
    "dob_en": "1987-01-01",
    "house_no": "99/9",
    "village": "-",
    "subdistrict": "ลุมพินี",
    "district": "ปทุมวัน",
    "province": "กรุงเทพมหานคร",
    "issue_date_en": "2022-01-01",
    "expiry_date_en": "2032-01-01",
    "photo_base64": "<BASE64 JPEG>"
  }
  ```
- `error`: บอกข้อผิดพลาดที่เกิดขึ้น (รวมรหัส SCARD เมื่อมี)
  ```json
  {
    "type": "error",
    "message": "Transmit failed",
    "code": "SCARD_E_COMM_DATA_LOST",
    "detail": "..."
  }
  ```

### ลำดับการทำงานของเซิร์ฟเวอร์
1. ตรวจหาเครื่องอ่านและส่ง `reader_status` ทุกครั้งที่เชื่อมต่อ/หลุด
2. รอเสียบบัตร (ไม่ส่งอีเวนต์ระหว่างรอ)
3. เมื่อมีบัตร: อ่านข้อมูลทั้งหมดแล้วส่ง `card_data` หนึ่งครั้ง
4. รอถอดบัตร (ไม่ส่งอีเวนต์ระหว่างรอ)
5. วนกลับข้อ 2

## ตัวแปรสภาพแวดล้อม (Environment Variables)
- `WS_HOST`: โฮสต์ของ WebSocket (ค่าเริ่มต้น `127.0.0.1`)
- `WS_PORT`: พอร์ตของ WebSocket (ค่าเริ่มต้น `8765`)
- `SMARTCARD_DEBUG`: ตั้ง `1` เพื่อเปิด log ดีบักเพิ่มเติม
- `SETTLE_DELAY_MS`: หน่วงระหว่างเลือกไฟล์/ก่อนส่ง APDU (เช่น `50`)
- `FIELD_RETRIES`: จำนวน retry ต่อฟิลด์ (เช่น `3`)
- ตัวเลือกอ่านรูป: อาจมีโหมดอ่านแบบสแกนหรืออ่านเป็นช่วงตามที่โค้ดกำหนด

## ตัวอย่างไคลเอนต์ JavaScript (ทดสอบเร็ว)
```html
<!doctype html>
<html>
  <body>
    <pre id="log"></pre>
    <script>
      const log = m => document.getElementById('log').textContent += m + "\n";
      const ws = new WebSocket('ws://127.0.0.1:8765');
      ws.onopen = () => log('connected');
      ws.onmessage = ev => log(ev.data);
      ws.onclose = () => log('closed');
      ws.onerror = e => log('error ' + e.message);
    </script>
  </body>
</html>
```

## สร้างไฟล์ .exe ด้วย PyInstaller
แนะนำรันใน venv ที่ติดตั้ง dependencies เรียบร้อย
```cmd
venv\Scripts\activate
pyinstaller --noconsole --onefile ^
  --icon icon.ico ^
  --add-data "icon.ico;." ^
  --name ThaiSmartCardReader ^
  ThaiSmartCardReader.py
```
ไฟล์ผลลัพธ์จะอยู่ใน `dist/ThaiSmartCardReader.exe`

หมายเหตุ:
- ในโหมด onefile โค้ดใช้ `_MEIPASS` เพื่อหาไฟล์ไอคอนอัตโนมัติ
- แอปป้องกันการรันซ้ำด้วย named mutex และจะแจ้งเตือนพร้อม URL หากเปิดซ้ำ

## การแก้ปัญหาเบื้องต้น
- ลบโฟลเดอร์ build/ dist/ และลอง build ใหม่หากติดค้าง
- หาก `output/ThaiSmartCardReader.exe` ล็อกอยู่ ให้ปิดโปรเซสก่อนลบโฟลเดอร์
  ```cmd
  taskkill /IM ThaiSmartCardReader.exe /F
  rmdir /S /Q output
  ```
- ถ้า WebSocket ต่อไม่ได้ ตรวจสอบ firewall และว่าพอร์ต `8765` ว่าง
- ถ้าข้อมูลบัตรว่าง/อ่านไม่ครบ ลองตั้ง `SETTLE_DELAY_MS=50` และเพิ่ม `FIELD_RETRIES`
- ตรวจสอบว่า Smart Card Service ทำงาน: Services → Smart Card → Running

## โครงสร้างโปรเจกต์
- `ThaiSmartCardReader.py` — แอปหลัก (Tray + WebSocket + SmartCard)
- `requirements.txt` — รายการไลบรารี
- `icon.ico` — ไอคอนถาดระบบ
- `.gitignore` — ไฟล์/โฟลเดอร์ที่ไม่ต้องการขี้น repo

---
พัฒนาเพื่อการใช้งานภายใน อาจต้องปรับ APDU ให้เหมาะกับเครื่องอ่าน/การ์ดบางรุ่น
