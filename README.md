# 🌱 Smart Farm — ระบบควบคุมโรงเรือนผักอัจฉริยะ (IoT)

ระบบควบคุมโรงเรือนผักโอเพนซอร์ส: ดูค่าอุณหภูมิ/ความชื้น/ดิน/แสงสด ควบคุมปั๊มน้ำ/พัดลม/ไฟจากเว็บ
รับข้อมูลจาก ESP32 (DHT22 + เซ็นเซอร์ความชื้นดิน + LDR) ผ่าน REST API พร้อมสถิติรายเดือน + Export CSV

![Python](https://img.shields.io/badge/Python-3.10+-blueviolet) ![Flask](https://img.shields.io/badge/Flask-3.x-green) ![ESP32](https://img.shields.io/badge/ESP32-Arduino-orange) ![License](https://img.shields.io/badge/License-MIT-brightgreen)

## ✨ ฟีเจอร์
- 🏭 **รองรับหลายโรงเรือน (Multi-Site)** — แต่ละโรงเรือนมีเซ็นเซอร์/อุปกรณ์/Dashboard/สถิติแยกกัน
- 📊 **Dashboard สด** — อุณหภูมิ/ความชื้นอากาศ/ความชื้นดิน/แสง + กราฟย้อนหลัง 120 จุด (อัปเดตอัตโนมัติ)
- 🎛️ **ควบคุมอุปกรณ์จากเว็บ** — ปั๊มน้ำ 🚿 / พัดลม 🌀 / ไฟปลูก 💡 (ESP32 รับคำสั่ง)
- 📅 **สถิติรายเดือน** — การ์ดสรุป (เฉลี่ย/สูงสุด/ต่ำสุด) + กราฟรายวัน + ตาราง + ⬇️ Export CSV (เปิด Excel ได้)
- 🧪 **โหมดจำลอง (SIM=1)** — สร้างข้อมูลเซ็นเซอร์เอง เห็นภาพทุกอย่างก่อนมีฮาร์ดแวร์
- 🔌 **REST API** — รับข้อมูลเซ็นเซอร์/ส่งคำสั่งควบคุม (ESP32 หรือบอร์ดอื่นๆ)

## 🖥️ หน้าจอ
![รายการโรงเรือน](screenshots/sites.png)
![สถิติรายเดือน](screenshots/stats.png)
![Dashboard](screenshots/dashboard-live.png)

## 🚀 เริ่มใช้ (รันบนเครื่อง/เซิร์ฟเวอร์ใดก็ได้)

```bash
git clone https://github.com/paluka488/smart-farm.git
cd smart-farm
pip install flask

# โหมดจำลอง (ไม่ต้องมีฮาร์ดแวร์ — เห็นค่าจำลองทันที)
DB_PATH=smartfarm.db PORT=5052 SIM=1 python app.py

# โหมดจริง (รอข้อมูลจาก ESP32)
DB_PATH=smartfarm.db PORT=5052 SIM=0 python app.py
```

เปิด `http://<ip>:5052` — หน้าแรกคือรายการโรงเรือน

## 🔌 REST API

| Method | Path | รายละเอียด |
|---|---|---|
| GET | `/` | รายการโรงเรือนทั้งหมด |
| GET | `/site/<id>` | Dashboard โรงเรือน |
| GET | `/site/<id>/stats` | สถิติรายเดือน (`?month=2026-08`) |
| GET | `/site/<id>/stats.csv` | Export สถิติเป็น CSV |
| POST | `/api/sensor` | ESP32 ส่งค่าจากเซ็นเซอร์ |
| GET | `/api/control?site=<id>` | ESP32 ดึงสถานะอุปกรณ์ |
| POST | `/api/control` | เปิด/ปิดอุปกรณ์ |
| GET | `/api/history?site=<id>` | ข้อมูลย้อนหลัง (กราฟ) |
| GET | `/api/stats?site=<id>&month=` | ข้อมูลสถิติ (JSON) |
| GET | `/admin` | จัดการโรงเรือน (เพิ่ม/ลบ) |

### ตัวอย่าง ESP32 ส่งข้อมูล
```json
POST /api/sensor
{"site": 1, "temp": 28.5, "hum": 70, "soil": 55, "light": 300}
```

### ตัวอย่างควบคุมอุปกรณ์
```json
POST /api/control
{"site": 1, "pump": 1, "fan": 0, "light": 1}
```
- `site` = id โรงเรือน (เริ่ม 1)
- `pump` / `fan` / `light` = 1 เปิด, 0 ปิด

## 🔧 ฮาร์ดแวร์ (ESP32)

โค้ด Arduino ใน [`esp32/smartfarm.ino`](esp32/smartfarm.ino) — อ่าน DHT22 + เซ็นเซอร์ความชื้นดิน + LDR + ควบคุม Relay 3 ตัว

| อุปกรณ์ | พิน |
|---|---|
| DHT22 (อุณหภูมิ/ความชื้น) | GPIO 4 |
| ความชื้นดิน (analog) | GPIO 34 |
| LDR (แสง) | GPIO 35 |
| Relay ปั๊มน้ำ | GPIO 25 |
| Relay พัดลม | GPIO 26 |
| Relay ไฟปลูก | GPIO 27 |

**ตั้งค่าก่อนอัปโหลด** (ในไฟล์ `.ino`):
```cpp
const char* WIFI_SSID = "ชื่อ WiFi";
const char* WIFI_PASS = "รหัส WiFi";
const char* SERVER   = "http://192.168.1.100:5052";  // URL เซิร์ฟเวอร์ Smart Farm
```
หลายโรงเรือน: เปลี่ยน `"site": 2` ใน `sendSensor()` ตาม id โรงเรือน

## 📁 โครงสร้าง
```
app.py                   # Flask server (Dashboard + API + SQLite + โหมดจำลอง + Multi-Site)
templates/               # UI (sites / dashboard / stats / admin)
esp32/smartfarm.ino      # Firmware ESP32
screenshots/             # ภาพตัวอย่าง
```

## 📝 License
MIT — นำไปใช้/ต่อยอด/ขายได้ฟรี (เครดิตผู้พัฒนาไว้ด้วยนะ 😊)