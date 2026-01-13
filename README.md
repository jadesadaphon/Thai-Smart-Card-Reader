# Thai Smart Card Reader

ระบบอ่านข้อมูลบัตรประชาชนไทย พร้อมส่งเหตุการณ์ผ่าน WebSocket ให้แอปพลิเคชันภายนอกรับฟังได้แบบเรียลไทม์

## คุณสมบัติ
- อ่านข้อมูลบัตร (เลขบัตร ชื่อ-นามสกุล วันเกิด เพศ ที่อยู่ หน่วยงานออกบัตร วันออก/วันหมดอายุ และรูปถ่ายในบางรุ่น)
- ตรวจจับการ "เสียบบัตร" และ "ถอดบัตร" ด้วยเหตุการณ์เฉพาะ
- ให้บริการ WebSocket บน `ws://0.0.0.0:8765` โดยค่าเริ่มต้น
- ทำงานเป็น Tray App บน Windows

## การติดตั้ง
```
pip install -r requirements.txt
```

แนะนำให้ติดตั้งไดรเวอร์เครื่องอ่านบัตรและเปิดบริการ Smart Card (`SCardSvr`) ให้พร้อมใช้งานบน Windows

## การใช้งาน
รันโปรแกรมหลัก:
```
python ThaiSmartCardReader.py
```

เมื่อทำงานแล้วจะมี Tray Icon และ WebSocket Server พร้อมเชื่อมต่อที่ `ws://localhost:8765`

### รูปแบบข้อความ (Events) ที่ส่งผ่าน WebSocket
ทุกข้อความเป็น JSON และมีฟิลด์ `version` ระบุเวอร์ชันโปรโตคอล (`"1.0"`). ตัวอย่างเหตุการณ์หลัก:

- `reader_status`: สถานะเครื่องอ่านบัตร
  - ตัวอย่าง (พบเครื่องอ่าน):
    ```json
    {
      "type": "reader_status",
      "version": "1.0",
      "status": "found",
      "reader_name": "ACS ACR122U PICC Reader",
      "timestamp": 1733550000.123
    }
    ```
  - ตัวอย่าง (ไม่พบเครื่องอ่าน):
    ```json
    {
      "type": "reader_status",
      "version": "1.0",
      "status": "not_found",
      "timestamp": 1733550002.456
    }
    ```

- `card_inserted`: ตรวจพบการเสียบบัตร
  ```json
  {
    "type": "card_inserted",
    "version": "1.0",
    "reader_name": "ACS ACR122U PICC Reader",
    "timestamp": 1733550010.789
  }
  ```

- `card_data`: ข้อมูลจากบัตรหลังเสียบและอ่านสำเร็จ
  - โครงสร้าง `data` มีฟิลด์สำคัญ เช่น `cid`, `full_name_th`, `full_name_en`, `birth_th`, `gender_th`, `address`, `issuer`, `issue_date_th`, `expire_date_th`, และ `photo` (Base64 ถ้ามี)
  - ตัวอย่าง (ย่อ):
    ```json
    {
      "type": "card_data",
      "version": "1.0",
      "reader_name": "ACS ACR122U PICC Reader",
      "timestamp": 1733550011.001,
      "data": {
        "cid": "1234567890123",
        "full_name_th": "นาย สมชาย ใจดี",
        "full_name_en": "Mr. Somchai Jaidee",
        "birth_th": "1 มกราคม 2568",
        "gender_th": "ชาย",
        "address": "123 หมู่ที่ 2 ตำบลบางรัก อำเภอบางรัก จังหวัดกรุงเทพ",
        "issuer": "กรมการปกครอง",
        "issue_date_th": "1 มกราคม 2565",
        "expire_date_th": "1 มกราคม 2575",
        "photo": "...base64..."
      }
    }
    ```

- `card_removed`: ตรวจพบการถอดบัตร
  ```json
  {
    "type": "card_removed",
    "version": "1.0",
    "reader_name": "ACS ACR122U PICC Reader",
    "timestamp": 1733550020.234
  }
  ```

- `error`: อ่านบัตรไม่สำเร็จ
  ```json
  {
    "type": "error",
    "version": "1.0",
    "reader_name": "ACS ACR122U PICC Reader",
    "timestamp": 1733550011.500,
    "message": "อ่านบัตรไม่สำเร็จ: ...",
    "error_code": "SCARD_COMM_ERROR",
    "retry_attempts": 3
  }
  ```

### ตัวอย่าง Client แบบง่าย (Python)
```python
import asyncio
import websockets

async def listen():
  async with websockets.connect("ws://localhost:8765") as ws:
    while True:
      msg = await ws.recv()
      print(msg)

asyncio.run(listen())
```

## การตั้งค่าเพิ่มเติมผ่าน Environment Variables
- `WS_HOST`/`WS_PORT`: ตั้งค่าโฮสต์และพอร์ตของ WebSocket
- `SMARTCARD_DEBUG=1`: เปิดโหมดดีบั๊ก
- `READ_PHOTO=0/1`: ปิด/เปิดการอ่านรูปจากบัตร
- `PHOTO_METHOD=parts`: เลือกวิธีอ่านรูปแบบชุดคำสั่งคงที่
- `ENABLE_PHOTO_SCAN=1`: เปิดการสแกนหา offset รูปอัตโนมัติ

## ข้อจำกัด
- รูปภาพอาจอ่านไม่ได้ในบางรุ่นบัตรหรือเครื่องอ่าน
- ต้องติดตั้งและเปิดบริการ Smart Card ของ Windows ให้พร้อมใช้งาน

## ใบอนุญาต
Apache License 2.0

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
