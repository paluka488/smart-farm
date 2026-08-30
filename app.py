# Smart Farm — ระบบควบคุมโรงเรือนผักอัจฉริยะ (POC) — รองรับ Multi-Site
#
# Flask app:
#  - หน้าเลือกรายการโรงเรือน (/)
#  - Dashboard ต่อโรงเรือน: /site/<site_id>
#  - API รับข้อมูลเซ็นเซอร์จาก ESP32: POST /api/sensor {"site":1,"temp":28.5,"hum":70,"soil":55,"light":300}
#  - API อ่าน/สั่งควบคุม (ต่อ site): GET/POST /api/control?site=1
#  - หลังบ้านจัดการโรงเรือน: /admin (เพิ่ม/แก้/ลบ)
#  - โหมดจำลอง (SIM=1): สร้างข้อมูลเซ็นเซอร์เองทุก site
#
# Run: DB_PATH=smartfarm.db PORT=5052 SIM=1 python app.py

import os, sqlite3, time, random, threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g, redirect, url_for, flash, Response
from contextlib import closing

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DB_PATH", os.path.join(BASE, "smartfarm.db"))
PORT = int(os.environ.get("PORT", 5052))
SIM = os.environ.get("SIM", "1") == "1"
SECRET = os.environ.get("SECRET_KEY", "smartfarm-poc-secret")

app = Flask(__name__)
app.secret_key = SECRET

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    with closing(sqlite3.connect(DB)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            location TEXT DEFAULT '',
            created_at INTEGER
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS sensor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            temp REAL, hum REAL, soil REAL, light REAL,
            site_id INTEGER DEFAULT 1
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS control (
            key TEXT, val INTEGER DEFAULT 0, updated INTEGER, site_id INTEGER DEFAULT 1,
            PRIMARY KEY (key, site_id)
        )""")
        # migration: เพิ่ม site_id ถ้ายังไม่มี (DB เดิมจาก version เก่า)
        for tbl in ("sensor", "control"):
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({tbl})").fetchall()]
            if "site_id" not in cols:
                db.execute(f"ALTER TABLE {tbl} ADD COLUMN site_id INTEGER DEFAULT 1")
        # seed โรงเรือนตัวอย่าง ถ้ายังว่าง
        c = db.execute("SELECT COUNT(*) c FROM sites").fetchone()[0]
        if c == 0:
            now = int(time.time())
            for nm, loc in [("โรงเรือน A", "แปลง 1 ข้างบ้าน"), ("โรงเรือน B", "แปลง 2 หลังสวน")]:
                db.execute("INSERT INTO sites (name, location, created_at) VALUES (?,?,?)", (nm, loc, now))
        for k in ("pump", "fan", "light"):
            for sid in range(1, 100):  # ครอบคลุมทุก site อนาคต (SQLite ไม่มี INSERT..SELECT ง่าย)
                db.execute("INSERT OR IGNORE INTO control (key, val, updated, site_id) VALUES (?,0,?,?)",
                           (k, int(time.time()), sid))
        db.commit()

# ---------- โหมดจำลอง: สร้างข้อมูลเซ็นเซอร์เองทุก site ----------
def _sim_loop():
    while True:
        h = datetime.now().hour
        base = 24 + (4 if 8 <= h <= 17 else -2)
        with closing(sqlite3.connect(DB)) as db:
            sites = db.execute("SELECT id FROM sites").fetchall()
            for s in sites:
                sid = s[0]  # row เป็น tuple (เชื่อมตรง ไม่ผ่าน row_factory)
                # site B เย็นกว่า/ชื้นกว่าเล็กน้อย (จำลองความต่าง)
                off = (sid - 1) * 1.5
                row = {
                    "temp": round(base + off + random.uniform(-1.5, 1.5), 1),
                    "hum": round(65 + random.uniform(-8, 8) - off, 1),
                    "soil": round(55 + random.uniform(-10, 10), 1),
                    "light": round(300 + random.uniform(-80, 80), 1) if 6 <= h <= 19 else round(random.uniform(5, 40), 1),
                }
                db.execute("INSERT INTO sensor (ts, temp, hum, soil, light, site_id) VALUES (?,?,?,?,?,?)",
                           (int(time.time()), row["temp"], row["hum"], row["soil"], row["light"], sid))
            db.commit()
        time.sleep(5)

if SIM:
    threading.Thread(target=_sim_loop, daemon=True).start()

# ---------- หน้าเลือกรายการโรงเรือน ----------
@app.route("/")
def index():
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        sites = db.execute("SELECT * FROM sites ORDER BY id").fetchall()
        cards = []
        for s in sites:
            last = db.execute("SELECT * FROM sensor WHERE site_id=? ORDER BY id DESC LIMIT 1", (s["id"],)).fetchone()
            ctl = {r["key"]: r["val"] for r in db.execute(
                "SELECT key,val FROM control WHERE site_id=?", (s["id"],)).fetchall()}
            cards.append({"site": s, "last": last, "ctl": ctl})
    return render_template("sites.html", cards=cards, sim=SIM)

# ---------- Dashboard ต่อโรงเรือน ----------
@app.route("/site/<int:sid>")
def dashboard(sid):
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        site = db.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone()
        if not site:
            return "ไม่พบโรงเรือน", 404
        last = db.execute("SELECT * FROM sensor WHERE site_id=? ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        ctl = {r["key"]: r["val"] for r in db.execute(
            "SELECT key,val FROM control WHERE site_id=?", (sid,)).fetchall()}
        rows = db.execute("SELECT * FROM sensor WHERE site_id=? ORDER BY id DESC LIMIT 10", (sid,)).fetchall()
        def fmt(r):
            return {"t": datetime.fromtimestamp(r["ts"]).strftime("%H:%M"),
                    "temp": r["temp"], "hum": r["hum"], "soil": r["soil"], "light": r["light"]}
        history = [fmt(r) for r in reversed(rows)]
    return render_template("dashboard.html", site=site, last=last, ctl=ctl, sim=SIM, history=history)

# ---------- API รับข้อมูลจาก ESP32 (รองรับ site) ----------
@app.route("/api/sensor", methods=["POST"])
def api_sensor():
    d = request.get_json(silent=True) or request.form
    try:
        temp = float(d.get("temp", 0)); hum = float(d.get("hum", 0))
        soil = float(d.get("soil", 0)); light = float(d.get("light", 0))
        sid = int(d.get("site", d.get("site_id", 1)))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad value"}), 400
    with closing(sqlite3.connect(DB)) as db:
        # site ต้องมีอยู่ (กันส่งมั่ว)
        ok = db.execute("SELECT 1 FROM sites WHERE id=?", (sid,)).fetchone()
        if not ok:
            return jsonify({"ok": False, "error": "no site"}), 404
        db.execute("INSERT INTO sensor (ts, temp, hum, soil, light, site_id) VALUES (?,?,?,?,?,?)",
                   (int(time.time()), temp, hum, soil, light, sid))
        db.commit()
    return jsonify({"ok": True})

# ---------- ESP32 ดึงสถานะควบคุม (ต่อ site) ----------
@app.route("/api/control", methods=["GET"])
def control_get():
    sid = request.args.get("site", request.args.get("site_id", 1), type=int)
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        ctl = {r["key"]: r["val"] for r in db.execute(
            "SELECT key,val FROM control WHERE site_id=?", (sid,)).fetchall()}
    return jsonify(ctl)

# ---------- ควบคุมอุปกรณ์จากเว็บ (ต่อ site) ----------
@app.route("/api/control", methods=["POST"])
def control_set():
    d = request.get_json(silent=True) or request.form
    sid = int(d.get("site", d.get("site_id", 1)))
    with closing(sqlite3.connect(DB)) as db:
        for k, v in d.items():
            if k in ("pump", "fan", "light"):
                try: v = 1 if int(v) else 0
                except: v = 0
                db.execute("UPDATE control SET val=?, updated=? WHERE key=? AND site_id=?",
                           (v, int(time.time()), k, sid))
        db.commit()
    return jsonify({"ok": True})

# ---------- API กราฟ (ข้อมูลย้อนหลัง ต่อ site) ----------
@app.route("/api/history")
def api_history():
    sid = request.args.get("site", request.args.get("site_id", 1), type=int)
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM sensor WHERE site_id=? ORDER BY id DESC LIMIT 120", (sid,)).fetchall()
    rows = list(reversed(rows))
    def fmt(r):
        return {"t": datetime.fromtimestamp(r["ts"]).strftime("%H:%M"),
                "temp": r["temp"], "hum": r["hum"], "soil": r["soil"], "light": r["light"]}
    return jsonify([fmt(r) for r in rows])

# ---------- สถิติรายเดือน (ต่อ site) ----------
def _month_stats(sid, month):
    """คืนสถิติรายวันของเดือน: [{date, temp_avg,temp_max,temp_min,hum_avg,soil_avg,light_avg}, ...] + สรุป"""
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT date(ts,'unixepoch') d,
                   ROUND(AVG(temp),1) t_avg, ROUND(MAX(temp),1) t_max, ROUND(MIN(temp),1) t_min,
                   ROUND(AVG(hum),1) h_avg, ROUND(AVG(soil),1) s_avg, ROUND(AVG(light),1) l_avg,
                   COUNT(*) n
            FROM sensor WHERE site_id=? AND date(ts,'unixepoch') LIKE ?
            GROUP BY d ORDER BY d""", (sid, month + "%")).fetchall()
        # สรุปรวมเดือน
        row = db.execute("""
            SELECT ROUND(AVG(temp),1) t_avg, ROUND(MAX(temp),1) t_max, ROUND(MIN(temp),1) t_min,
                   ROUND(AVG(hum),1) h_avg, ROUND(MAX(hum),1) h_max, ROUND(MIN(hum),1) h_min,
                   ROUND(AVG(soil),1) s_avg, ROUND(AVG(light),1) l_avg, COUNT(*) n
            FROM sensor WHERE site_id=? AND date(ts,'unixepoch') LIKE ?""",
            (sid, month + "%")).fetchone()
    days = [{"date": r["d"], "temp_avg": r["t_avg"], "temp_max": r["t_max"], "temp_min": r["t_min"],
             "hum_avg": r["h_avg"], "soil_avg": r["s_avg"], "light_avg": r["l_avg"], "n": r["n"]}
            for r in rows]
    return days, row

@app.route("/site/<int:sid>/stats")
def site_stats(sid):
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        site = db.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone()
        if not site:
            return "ไม่พบโรงเรือน", 404
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    if len(month) != 7 or month[4] != "-":
        month = datetime.now().strftime("%Y-%m")
    days, summary = _month_stats(sid, month)
    return render_template("stats.html", site=site, month=month, days=days, summary=summary, sim=SIM)

@app.route("/api/stats")
def api_stats():
    sid = request.args.get("site", 1, type=int)
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    if len(month) != 7 or month[4] != "-":
        month = datetime.now().strftime("%Y-%m")
    days, summary = _month_stats(sid, month)
    return jsonify({"site": sid, "month": month, "days": days, "summary": dict(summary) if summary else None})

@app.route("/site/<int:sid>/stats.csv")
def site_stats_csv(sid):
    """Export สถิติรายเดือนเป็น CSV (Thai BOM เปิด Excel ได้)"""
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    if len(month) != 7 or month[4] != "-":
        month = datetime.now().strftime("%Y-%m")
    days, _ = _month_stats(sid, month)
    import io, csv as csvmod
    buf = io.StringIO()
    w = csvmod.writer(buf)
    w.writerow(["วันที่", "อุณหภูมิเฉลี่ย(°C)", "สูงสุด(°C)", "ต่ำสุด(°C)", "ความชื้นเฉลี่ย(%)", "ดินเฉลี่ย(%)", "แสงเฉลี่ย(lux)", "จำนวนจุด"])
    for d in days:
        w.writerow([d["date"], d["temp_avg"], d["temp_max"], d["temp_min"], d["hum_avg"], d["soil_avg"], d["light_avg"], d["n"]])
    resp = Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f"attachment; filename=stats_{sid}_{month}.csv"
    return resp

# ---------- หลังบ้าน: จัดการโรงเรือน ----------
@app.route("/admin")
def admin():
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory = sqlite3.Row
        sites = db.execute("SELECT * FROM sites ORDER BY id").fetchall()
        stats = []
        for s in sites:
            n = db.execute("SELECT COUNT(*) c FROM sensor WHERE site_id=?", (s["id"],)).fetchone()["c"]
            ctl = {r["key"]: r["val"] for r in db.execute(
                "SELECT key,val FROM control WHERE site_id=?", (s["id"],)).fetchall()}
            stats.append({"site": s, "count": n, "ctl": ctl})
    return render_template("admin.html", stats=stats)

@app.route("/admin/add", methods=["POST"])
def admin_add():
    name = request.form.get("name", "").strip()
    loc = request.form.get("location", "").strip()
    if name:
        with closing(sqlite3.connect(DB)) as db:
            db.execute("INSERT INTO sites (name, location, created_at) VALUES (?,?,?)", (name, loc, int(time.time())))
            db.commit()
    return redirect(url_for("admin"))

@app.route("/admin/del/<int:sid>", methods=["POST"])
def admin_del(sid):
    with closing(sqlite3.connect(DB)) as db:
        db.execute("DELETE FROM sites WHERE id=?", (sid,))
        db.execute("DELETE FROM sensor WHERE site_id=?", (sid,))
        db.execute("DELETE FROM control WHERE site_id=?", (sid,))
        db.commit()
    return redirect(url_for("admin"))

init_db()

if __name__ == "__main__":
    print(f"Smart Farm (multi-site) running :{PORT} SIM={SIM} DB={DB}")
    app.run(host="0.0.0.0", port=PORT, debug=True)