# -*- coding: utf-8 -*-
"""
# Copyright 2025 NOVELBIZ CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""

from smartcard.System import readers
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.Exceptions import NoCardException
from smartcard.util import toHexString
from smartcard.scard import SCARD_PROTOCOL_T0, SCARD_PROTOCOL_T1, SCARD_SHARE_SHARED
import subprocess
import time
import asyncio
import json
import threading
import os
from websockets import serve
import base64
import pystray
from PIL import Image
import sys
import ctypes
from ctypes import wintypes
try:
    from win10toast import ToastNotifier
except Exception:
    ToastNotifier = None


MESSAGE_VERSION = "1.0"


class IDCardReader:
    """Thai National ID Card Reader (WebSocket Event Producer)"""

    def __init__(self):
        self.cardservice = None  # maintained only while reading a card
        # Enable debug via environment variable SMARTCARD_DEBUG=1
        self.debug = os.environ.get('SMARTCARD_DEBUG', '0') == '1'
        # Delay (seconds) after card insertion before first APDU to allow stabilization
        self.settle_delay = float(os.environ.get('SMARTCARD_SETTLE_DELAY', '0.25'))
        # Per-field retry count
        self.field_retries = int(os.environ.get('SMARTCARD_FIELD_RETRIES', '2'))
        # Global read attempts already handled outside (3). Here we just refine per field.

    # ------------------- Helper Functions -------------------
    def decode_text(self, data):
        """แปลง bytes เป็น text"""
        try:
            return bytes(data).decode('tis-620', errors='ignore').strip()
        except:
            return ''.join(chr(b) if b < 128 else '?' for b in data).strip()

    def send_apdu_with_get_response(self, connection, apdu):
        """ส่ง APDU command และจัดการ GET_RESPONSE"""
        response, sw1, sw2 = connection.transmit(apdu)
        if sw1 == 0x61:
            get_response = [0x00, 0xC0, 0x00, 0x00, sw2]
            response, sw1, sw2 = connection.transmit(get_response)
        return response, sw1, sw2

    def apdu_retry(self, connection, apdu, retries):
        """Retry APDU on communication errors."""
        last_err = None
        for i in range(1, retries + 2):  # initial try + retries
            try:
                resp, sw1, sw2 = self.send_apdu_with_get_response(connection, apdu)
                if self.debug:
                    print(f"[DEBUG] APDU #{i} -> SW={sw1:02X} {sw2:02X} len={len(resp)}")
                return resp, sw1, sw2
            except Exception as e:
                msg = str(e)
                last_err = e
                if self.debug:
                    print(f"[DEBUG] APDU error try {i}: {msg}")
                if '0x8010002F' in msg or 'communications error' in msg.lower():
                    time.sleep(0.15)
                    continue
                else:
                    break
        raise last_err

    def parse_thai_date(self, date_str):
        """แปลงวันที่จากรูปแบบ YYYYMMDD เป็นรูปแบบที่อ่านง่าย"""
        if date_str == '99999999':
            return "ตลอดชีพ", "LIFELONG"
            
        if len(date_str) == 8 and date_str.isdigit():
            try:
                year = date_str[0:4]
                month = date_str[4:6]
                day = date_str[6:8]
                
                thai_year = int(year)
                eng_year = thai_year - 543
                
                thai_months = ['', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                            'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
                
                eng_months = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                            'July', 'August', 'September', 'October', 'November', 'December']
                
                month_int = int(month)
                if 1 <= month_int <= 12:
                    thai_date = f"{int(day)} {thai_months[month_int]} {thai_year}"
                    eng_date = f"{int(day)} {eng_months[month_int]} {eng_year}"
                    return thai_date, eng_date
            except Exception as e:
                print(f"[ผิดพลาด] แปลงวันที่ไม่สำเร็จ: {e}")
                return "ไม่ระบุ", "Not specified"
        else:
            return "ไม่ระบุ", "Not specified"

    def disconnect_card(self):
        """ตัดการเชื่อมต่อจากบัตร"""
        if self.cardservice:
            try:
                self.cardservice.connection.disconnect()
                print("[ตัดการเชื่อมต่อ] ตัดการเชื่อมต่อบัตรสำเร็จ")
            except Exception as e:
                print(f"[ผิดพลาด] ไม่สามารถตัดการเชื่อมต่อ: {e}")
            finally:
                self.cardservice = None

    # ------------------- Card Reader Functions -------------------
    def check_service_status(self):
        """ตรวจสอบสถานะ Smart Card Service"""
        try:
            result = subprocess.run(
                ["sc", "query", "SCardSvr"],
                capture_output=True, text=True, shell=True
            )
            return "RUNNING" in result.stdout
        except Exception as e:
            print(f"[ผิดพลาด] ตรวจสอบ Service ไม่สำเร็จ: {e}")
            return False

    def check_reader_status(self):
        """ตรวจสอบสถานะเครื่องอ่านบัตร"""
        if not self.check_service_status():
            print("[สถานะ] บริการ Smart Card ไม่ทำงาน")
            return False

        r = readers()
        if r:
            print(f"[สถานะ] พบเครื่องอ่านบัตร: {r[0]}")
            return True
        else:
            print("[สถานะ] ไม่พบเครื่องอ่านบัตร")
            return False

    # ------------------- Read ID Card -------------------
    def read_card_data(self, cardservice):
        """อ่านข้อมูลและคืนค่า dict แทนการพิมพ์"""
        data = {}
        try:
            cardservice.connection.connect(
                protocol=SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1,
                mode=SCARD_SHARE_SHARED
            )
            atr = cardservice.connection.getATR()
            data['atr'] = toHexString(atr)
            if self.debug:
                print(f"[DEBUG] Connected ATR={data['atr']}")
        except Exception as e:
            raise RuntimeError(f"ไม่สามารถเชื่อมต่อบัตร: {e}")

        SELECT = [0x00, 0xA4, 0x04, 0x00, 0x08]
        THAI_ID_CARD = [0xA0, 0x00, 0x00, 0x00, 0x54, 0x48, 0x00, 0x01]
        response, sw1, sw2 = cardservice.connection.transmit(SELECT + THAI_ID_CARD)
        if sw1 == 0x61:
            get_response = [0x00, 0xC0, 0x00, 0x00, sw2]
            response, sw1, sw2 = cardservice.connection.transmit(get_response)
        if sw1 != 0x90:
            raise RuntimeError(f"เลือก Applet ไม่สำเร็จ SW: {sw1:02x} {sw2:02x}")
        if self.debug:
            print(f"[DEBUG] Applet selected SW={sw1:02X} {sw2:02X}")

        # Settle delay before heavy reads
        if self.settle_delay > 0:
            time.sleep(self.settle_delay)
            if self.debug:
                print(f"[DEBUG] Settled for {self.settle_delay}s before field reads")

        commands = {
            'cid': [0x80, 0xb0, 0x00, 0x04, 0x02, 0x00, 0x0d],
            'name_th': [0x80, 0xb0, 0x00, 0x11, 0x02, 0x00, 0x64],
            'name_en': [0x80, 0xb0, 0x00, 0x75, 0x02, 0x00, 0x64],
            'birth': [0x80, 0xb0, 0x00, 0xD9, 0x02, 0x00, 0x08],
            'gender': [0x80, 0xb0, 0x00, 0xE1, 0x02, 0x00, 0x01],
            'issuer': [0x80, 0xb0, 0x00, 0xF6, 0x02, 0x00, 0x64],
            'issue_date': [0x80, 0xb0, 0x01, 0x67, 0x02, 0x00, 0x08],
            'expire_date': [0x80, 0xb0, 0x01, 0x6F, 0x02, 0x00, 0x08],
            'address': [0x80, 0xb0, 0x15, 0x79, 0x02, 0x00, 0x64],
            'request_number': [0x80, 0xB0, 0x16, 0x19, 0x02, 0x00, 0x0E]
        }

        def read_field(key):
            apdu = commands[key]
            resp, sw1_, sw2_ = self.apdu_retry(cardservice.connection, apdu, self.field_retries)
            txt = self.decode_text(resp)
            if self.debug:
                print(f"[DEBUG] Field {key} -> '{txt}'")
            return txt

        data['cid'] = read_field('cid')
        full_name_th_raw = read_field('name_th').replace('#', ' ').strip()
        full_name_en_raw = read_field('name_en').replace('#', ' ').strip()

        def parse_thai_name(full):
            # Split by spaces collapsing duplicates
            parts = [p for p in full.split(' ') if p]
            title = ''
            first = ''
            last = ''
            thai_titles = {'นาย','นาง','นางสาว','เด็กชาย','เด็กหญิง'}
            if parts:
                if parts[0] in thai_titles:
                    title = parts[0]
                    remaining = parts[1:]
                else:
                    remaining = parts
                if remaining:
                    first = remaining[0]
                if len(remaining) >= 2:
                    last = remaining[-1]
            return title, first, last

        def parse_english_name(full):
            parts = [p for p in full.split(' ') if p]
            title = ''
            first = ''
            last = ''
            english_titles = {'Mr.','Mrs.','Miss','Ms.','Master'}
            if parts:
                if parts[0] in english_titles:
                    title = parts[0]
                    remaining = parts[1:]
                else:
                    remaining = parts
                if remaining:
                    first = remaining[0]
                if len(remaining) >= 2:
                    last = remaining[-1]
            return title, first, last

        title_th, first_th, last_th = parse_thai_name(full_name_th_raw)
        title_en, first_en, last_en = parse_english_name(full_name_en_raw)

        data['full_name_th'] = full_name_th_raw
        data['title_th'] = title_th
        data['name_th'] = first_th
        data['last_name_th'] = last_th
        data['full_name_en'] = full_name_en_raw
        data['title_en'] = title_en
        data['name_en'] = first_en
        data['last_name_en'] = last_en

        birth_raw = read_field('birth')
        birth_th, birth_en = self.parse_thai_date(birth_raw)
        data['birth_raw'] = birth_raw
        data['birth_th'] = birth_th
        data['birth_en'] = birth_en

        gender_code = read_field('gender')
        gender_th = "ชาย" if gender_code == "1" else "หญิง" if gender_code == "2" else gender_code
        gender_en = "Male" if gender_code == "1" else "Female" if gender_code == "2" else gender_code
        data['gender_th'] = gender_th
        data['gender_en'] = gender_en

        issue_raw = read_field('issue_date')
        issue_th, issue_en = self.parse_thai_date(issue_raw)
        data['issue_date_raw'] = issue_raw
        data['issue_date_th'] = issue_th
        data['issue_date_en'] = issue_en

        expire_raw = read_field('expire_date')
        expire_th, expire_en = self.parse_thai_date(expire_raw)
        data['expire_date_raw'] = expire_raw
        data['expire_date_th'] = expire_th
        data['expire_date_en'] = expire_en

        issuer_name = read_field('issuer').strip()
        data['issuer'] = issuer_name

        address = read_field('address').replace('#', ' ').strip()
        data['address'] = address
        # Address parsing (Thai typical format)
        import re
        no_match = re.search(r'^(\d+)', address)
        moo_match = re.search(r'หมู่(?:ที่)?\s*(\d+)', address)
        tumbol_match = re.search(r'ตำบล([^\s]+)', address)
        amphur_match = re.search(r'อำเภอ([^\s]+)', address)
        province_match = re.search(r'จังหวัด([^\s]+)', address)
        data['address_no'] = no_match.group(1) if no_match else ''
        data['address_moo'] = moo_match.group(1) if moo_match else ''
        data['address_tumbol'] = tumbol_match.group(1) if tumbol_match else ''
        data['address_amphur'] = amphur_match.group(1) if amphur_match else ''
        data['address_province'] = province_match.group(1) if province_match else ''

        request_number = read_field('request_number').strip()
        data['request_number'] = request_number

        # รูปภาพ: พยายามอ่านหากกำหนดค่าเริ่มต้น offset ผ่าน ENV (PHOTO_START_OFFSET_HIGH/LOW)
        try:
            data['photo'] = ''
            read_photo_flag = os.environ.get('READ_PHOTO', '1') == '1'
            if read_photo_flag:
                photo_bytes = b''
                # 1) วิธีตาม main.py: อ่านเป็น 20 ส่วนที่ offset คงที่
                if os.environ.get('PHOTO_METHOD', 'parts') == 'parts':
                    if self.debug:
                        print("[DEBUG] Try photo read by predefined parts (main.py method)")
                    photo_bytes = self.read_photo_by_parts(cardservice.connection)
                # 2) วิธีกำหนด offset
                if not photo_bytes:
                    photo_high = os.environ.get('PHOTO_START_OFFSET_HIGH')
                    photo_low = os.environ.get('PHOTO_START_OFFSET_LOW')
                    if photo_high and photo_low:
                        if self.debug:
                            print(f"[DEBUG] Try photo read from offsets H={photo_high} L={photo_low}")
                        photo_bytes = self.read_photo(cardservice.connection, int(photo_high, 16), int(photo_low, 16))
                # 3) วิธี scan auto
                if not photo_bytes and os.environ.get('ENABLE_PHOTO_SCAN', '0') == '1':
                    if self.debug:
                        print("[DEBUG] Scanning for photo start offset...")
                    found = self.scan_for_photo_start(cardservice.connection)
                    if found:
                        ph, pl = found
                        if self.debug:
                            print(f"[DEBUG] Found JPEG header at H=0x{ph:02X} L=0x{pl:02X}")
                        photo_bytes = self.read_photo(cardservice.connection, ph, pl)
                if photo_bytes:
                    data['photo'] = base64.b64encode(photo_bytes).decode('ascii')
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] อ่านรูปภาพไม่สำเร็จ: {e}")
            data['photo'] = ''

        return data

    def read_card_data_with_retry(self, attempts: int, delay: float, cardservice):
        """พยายามอ่านข้อมูลบัตรซ้ำ หากเกิด SCARD communications error"""
        last_err = None
        for i in range(1, attempts + 1):
            try:
                return self.read_card_data(cardservice)
            except Exception as e:
                msg = str(e)
                last_err = e
                # หากพบ error การสื่อสารให้ retry ตามจำนวนที่กำหนด
                if '0x8010002F' in msg or 'communications error' in msg.lower():
                    time.sleep(delay)
                    continue
                else:
                    break
        raise last_err

    def read_photo(self, connection, start_high: int, start_low: int):
        """อ่านรูปภาพจากบัตรแบบ chunk (ไม่ทราบความยาวแน่นอน)
        การใช้งาน: กำหนดตัวแปร ENV PHOTO_START_OFFSET_HIGH / PHOTO_START_OFFSET_LOW เป็นค่า hex (เช่น 0x17, 0xA9)
        หมายเหตุ: โครงสร้างคำสั่งอาจแตกต่างตามรุ่นบัตร หากมีสเปค APDU ควรปรับให้ตรง.
        """
        max_chunks = int(os.environ.get('PHOTO_MAX_CHUNKS', '40'))
        chunk_len = int(os.environ.get('PHOTO_CHUNK_LEN', '0xFF'), 16)
        data_acc = bytearray()
        # รูปภาพคาดว่ามี header JPEG (FFD8) และสิ้นสุดด้วย FFD9
        for i in range(max_chunks):
            offset_high = start_high
            offset_low = start_low + i * chunk_len
            if offset_low > 0xFFFF:
                break
            # APDU รูปแบบเดียวกับ field อื่น: CLA 0x80 INS 0xB0 P1 P2 0x02 0x00 Lc
            apdu = [0x80, 0xB0, (offset_high & 0xFF), (offset_low & 0xFF), 0x02, 0x00, chunk_len & 0xFF]
            try:
                resp, sw1, sw2 = self.send_apdu_with_get_response(connection, apdu)
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] PHOTO chunk {i} transmit error: {e}")
                break
            if sw1 != 0x90:
                if self.debug:
                    print(f"[DEBUG] PHOTO chunk {i} SW={sw1:02X}{sw2:02X} stop")
                break
            data_acc.extend(resp)
            if self.debug:
                print(f"[DEBUG] PHOTO chunk {i} size={len(resp)} total={len(data_acc)}")
            # ตรวจสอบ JPEG end marker
            if len(data_acc) >= 2 and data_acc[-2] == 0xFF and data_acc[-1] == 0xD9:
                if self.debug:
                    print("[DEBUG] JPEG end detected")
                break
        # ตรวจสอบว่ามี header JPEG
        if len(data_acc) > 4 and data_acc[0] == 0xFF and data_acc[1] == 0xD8:
            return bytes(data_acc)
        return b''

    def read_photo_by_parts(self, connection):
        """อ่านรูปภาพตามชุดคำสั่ง APDU ที่กำหนดไว้ล่วงหน้า (อิง main.py)"""
        parts = [
            [0x80, 0xB0, 0x01, 0x7B, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x02, 0x7A, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x03, 0x79, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x04, 0x78, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x05, 0x77, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x06, 0x76, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x07, 0x75, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x08, 0x74, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x09, 0x73, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0A, 0x72, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0B, 0x71, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0C, 0x70, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0D, 0x6F, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0E, 0x6E, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x0F, 0x6D, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x10, 0x6C, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x11, 0x6B, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x12, 0x6A, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x13, 0x69, 0x02, 0x00, 0xFF],
            [0x80, 0xB0, 0x14, 0x68, 0x02, 0x00, 0xFF],
        ]
        data_acc = bytearray()
        for idx, apdu in enumerate(parts, start=1):
            try:
                resp, sw1, sw2 = self.send_apdu_with_get_response(connection, apdu)
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] PHOTO parts transmit error at part {idx}: {e}")
                return b''
            if sw1 != 0x90:
                if self.debug:
                    print(f"[DEBUG] PHOTO parts SW={sw1:02X}{sw2:02X} at part {idx}")
                return b''
            data_acc.extend(resp)
            if self.debug:
                print(f"[DEBUG] PHOTO part {idx}/20 size={len(resp)} total={len(data_acc)}")
        # Validate JPEG
        if len(data_acc) > 4 and data_acc[0] == 0xFF and data_acc[1] == 0xD8:
            # If tail not exactly FFD9, still return; client can decode
            return bytes(data_acc)
        return b''

    def scan_for_photo_start(self, connection):
        """สแกนหา JPEG header (FFD8) ในช่วง offset ที่พอเป็นไปได้
        ระยะสแกนควบคุมได้ด้วย ENV: SCAN_P1_START, SCAN_P1_END, SCAN_STEP
        """
        p1_start = int(os.environ.get('SCAN_P1_START', '0x15'), 16)
        p1_end = int(os.environ.get('SCAN_P1_END', '0x20'), 16)
        step = int(os.environ.get('SCAN_STEP', '0x20'), 16)
        probe_len = int(os.environ.get('SCAN_PROBE_LEN', '0x40'), 16)
        for p1 in range(p1_start, p1_end + 1):
            for p2 in range(0x00, 0x100, step):
                apdu = [0x80, 0xB0, p1 & 0xFF, p2 & 0xFF, 0x02, 0x00, probe_len & 0xFF]
                try:
                    resp, sw1, sw2 = self.send_apdu_with_get_response(connection, apdu)
                except Exception as e:
                    if self.debug:
                        print(f"[DEBUG] Scan error P1=0x{p1:02X} P2=0x{p2:02X}: {e}")
                    continue
                if sw1 != 0x90 or not resp:
                    continue
                # Find JPEG SOI
                for i in range(len(resp) - 1):
                    if resp[i] == 0xFF and resp[i + 1] == 0xD8:
                        # Compute absolute offset of header within file: we align to this block start
                        # Re-read from the exact block start (p2 + i might cross 0xFF boundary; keep simple and use this block start)
                        return p1, p2
        return None

    # ------------------- Main Loop -------------------
    # ------------------- Event Producer Loop -------------------
    def event_producer(self, loop, queue: asyncio.Queue, state: dict):
        """ตัวสร้างเหตุการณ์ตาม Flow ที่กำหนด เติมข้อความลงใน queue (thread)"""
        while True:
            # 1. ตรวจหาเครื่องอ่านบัตร (loop จนเจอ ส่งสถานะ not_found ทุกครั้งที่ยังไม่เจอ)
            reader_name = None
            while True:
                try:
                    rlist = readers()
                    if not rlist:
                        status_event = {
                            'type': 'reader_status',
                            'version': MESSAGE_VERSION,
                            'status': 'not_found',
                            'timestamp': time.time()
                        }
                        state['last_reader_status'] = status_event
                        loop.call_soon_threadsafe(queue.put_nowait, status_event)
                        time.sleep(2)
                        continue
                    reader_name = str(rlist[0])
                    status_event = {
                        'type': 'reader_status',
                        'version': MESSAGE_VERSION,
                        'status': 'found',
                        'reader_name': reader_name,
                        'timestamp': time.time()
                    }
                    state['last_reader_status'] = status_event
                    loop.call_soon_threadsafe(queue.put_nowait, status_event)
                    break
                except Exception:
                    time.sleep(2)
                    continue

            # 2.1 Loop รอการเสียบบัตร (ไม่ส่ง socket ระหว่างรอ)
            while True:
                cardtype = AnyCardType()
                cardrequest = CardRequest(timeout=1, cardType=cardtype)
                try:
                    cardservice = cardrequest.waitforcard()
                    # 2.2 เจอบัตร -> อ่าน ส่งข้อมูล แล้วไปขั้นตอน 3
                    try:
                        card_data = self.read_card_data_with_retry(attempts=3, delay=0.4, cardservice=cardservice)
                        loop.call_soon_threadsafe(queue.put_nowait, {
                            'type': 'card_data',
                            'version': MESSAGE_VERSION,
                            'reader_name': reader_name,
                            'timestamp': time.time(),
                            'data': card_data
                        })
                    except Exception as e:
                        emsg = str(e)
                        error_code = None
                        if '0x8010002F' in emsg:
                            error_code = 'SCARD_COMM_ERROR'
                        elif '0x80100068' in emsg:
                            error_code = 'SCARD_W_RESET_CARD'
                        elif 'เลือก Applet' in emsg:
                            error_code = 'APPLET_SELECT_FAILED'
                        if self.debug:
                            print(f"[DEBUG] Card read failure error_code={error_code} msg={emsg}")
                        loop.call_soon_threadsafe(queue.put_nowait, {
                            'type': 'error',
                            'version': MESSAGE_VERSION,
                            'reader_name': reader_name,
                            'timestamp': time.time(),
                            'message': f'อ่านบัตรไม่สำเร็จ: {e}',
                            'error_code': error_code,
                            'retry_attempts': 3
                        })
                    finally:
                        try:
                            cardservice.connection.disconnect()
                        except Exception:
                            pass

                    # 3 Loop เพื่อรอการถอดบัตร (ไม่ส่ง socket ขณะรอ)
                    while True:
                        cardtype2 = AnyCardType()
                        cardrequest2 = CardRequest(timeout=1, cardType=cardtype2)
                        try:
                            cardrequest2.waitforcard()
                            time.sleep(0.5)
                            continue  # ยังเสียบอยู่
                        except NoCardException:
                            # 3.1 ถอดบัตร -> กลับไป 2.1
                            break
                        except Exception:
                            break
                    # กลับไปเริ่มรอเสียบบัตรใหม่
                    continue
                except NoCardException:
                    # ยังไม่มีบัตร เสียบบัตรไม่เจอ loop ต่อ
                    pass
                except Exception:
                    # ตรวจสอบว่าเครื่องอ่านยังอยู่ไหม ถ้าหาย -> กลับไปข้อ 1
                    try:
                        if not readers():
                            break  # กลับไปตรวจหาเครื่องอ่านใหม่
                    except Exception:
                        break
                # ให้ CPU พักเล็กน้อย
                time.sleep(0.3)

            # 4 เครื่องอ่านหาย -> กลับไปข้อ 1
            # loop while True จะทำงานต่อ
            time.sleep(1)


# ------------------- WebSocket Server -------------------
async def websocket_handler(websocket, clients, state):
    clients.add(websocket)
    # ส่ง snapshot สถานะล่าสุดของเครื่องอ่านให้ client ใหม่ทันที
    last_status = state.get('last_reader_status')
    if last_status:
        try:
            await websocket.send(json.dumps(last_status, ensure_ascii=False))
        except Exception:
            pass
    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)


async def broadcaster(queue: asyncio.Queue, clients: set):
    while True:
        event = await queue.get()
        if not clients:
            continue
        msg = json.dumps(event, ensure_ascii=False)
        to_remove = set()
        for ws in list(clients):
            try:
                await ws.send(msg)
            except Exception:
                to_remove.add(ws)
        for ws in to_remove:
            clients.discard(ws)


async def main_async(host: str = '0.0.0.0', port: int = 8765):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    clients: set = set()
    state: dict = {'last_reader_status': None}
    reader = IDCardReader()

    # เริ่ม thread สำหรับผลิต event
    producer_thread = threading.Thread(target=reader.event_producer, args=(loop, queue, state), daemon=True)
    producer_thread.start()

    async with serve(lambda ws: websocket_handler(ws, clients, state), host, port):
        print(f"[WS] WebSocket server started on ws://{host}:{port}")
        await broadcaster(queue, clients)


# ------------------- Tray App -------------------
def _run_server_in_thread(host: str, port: int):
    def runner():
        asyncio.run(main_async(host, port))
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


def tray_main():
    host = os.environ.get('WS_HOST', '0.0.0.0')
    port = int(os.environ.get('WS_PORT', '8765'))
    server_thread = _run_server_in_thread(host, port)

    def resource_path(relpath: str) -> str:
        try:
            base_path = getattr(sys, '_MEIPASS')  # PyInstaller ONEFILE temp dir
        except Exception:
            base_path = os.path.abspath('.')
        return os.path.join(base_path, relpath)

    # Resolve tray icon path robustly for PyInstaller onefile
    icon_candidates = []
    env_icon = os.environ.get('TRAY_ICON_PATH', '').strip()
    if env_icon:
        icon_candidates.append(env_icon)
    icon_candidates.append(resource_path('icon.ico'))
    icon_candidates.append(os.path.join(os.getcwd(), 'icon.ico'))

    image = None
    for p in icon_candidates:
        if p and os.path.exists(p):
            try:
                image = Image.open(p)
                break
            except Exception:
                continue
    if image is None:
        # Fallback: simple 16x16 green dot
        image = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
        for x in range(16):
            for y in range(16):
                if (x-8)**2 + (y-8)**2 <= 36:
                    image.putpixel((x, y), (0, 160, 0, 255))

    def on_open(icon, item):
        # No-op; server already running
        pass

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(text='Open (ws://{}:{})'.format(host, port), action=on_open, default=True),
        pystray.MenuItem(text='Exit', action=on_quit)
    )

    tray_icon = pystray.Icon('ThaiSmartCardReader', image, 'Thai Smart Card Reader', menu)

    def on_ready(icon):
        try:
            # Ensure icon visible before notify
            icon.visible = True
            icon.notify(title='Thai Smart Card Reader',
                        message=f'เริ่มทำงานแล้ว\nเชื่อมต่อ: ws://{host}:{port}')
        except Exception:
            # Fallback to MessageBox if notify not supported
            try:
                ctypes.windll.user32.MessageBoxW(0,
                    f"Thai Smart Card Reader เริ่มทำงานแล้ว\nเชื่อมต่อ: ws://{host}:{port}",
                    "Thai Smart Card Reader", 0x00000040)
            except Exception:
                pass

    tray_icon.run(setup=on_ready)


# ------------------- Main -------------------
if __name__ == "__main__":
    # Ensure single instance via Windows named mutex
    ERROR_ALREADY_EXISTS = 183
    mutex_name = "Local\\ThaiSmartCardReader_Mutex"
    CreateMutexW = ctypes.windll.kernel32.CreateMutexW
    GetLastError = ctypes.windll.kernel32.GetLastError
    CloseHandle = ctypes.windll.kernel32.CloseHandle
    handle = CreateMutexW(None, False, mutex_name)
    if handle and GetLastError() == ERROR_ALREADY_EXISTS:
        # Show non-blocking toast instead of modal popup
        try:
            host = os.environ.get('WS_HOST', '0.0.0.0')
            port = int(os.environ.get('WS_PORT', '8765'))
            title = "Thai Smart Card Reader"
            message = f"กำลังทำงานอยู่แล้ว\nเชื่อมต่อ: ws://{host}:{port}"
            if ToastNotifier is not None:
                try:
                    tn = ToastNotifier()
                    tn.show_toast(title, message, duration=5, threaded=True)
                except Exception:
                    pass
            else:
                # Silent fallback: no-op if toast lib missing
                pass
        except Exception:
            pass
        os._exit(0)
    # Keep handle referenced for process lifetime
    _SINGLE_INSTANCE_HANDLE = handle
    # Run as tray app to avoid console window
    tray_main()