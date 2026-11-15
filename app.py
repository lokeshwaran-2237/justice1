"""Justice - Legal Consultant Platform: Flask + SQLite REST API.

Roles: client, advocate, admin.
Run:  python app.py   (see README.md)
"""
import datetime as dt
import json
import os
import re
import sqlite3
import uuid
from functools import wraps

import jwt
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from chatbot import answer

SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
DB_PATH = os.environ.get("DB_PATH", "justice.db")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@justice.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png"}

COURTS = [
    "Madurai Bench, Madras High Court", "Madurai District Court",
    "Tiruchirappalli District Court", "Chennai - Madras High Court",
    "Chennai City Civil Court", "Coimbatore District Court",
    "Salem District Court", "Tirunelveli District Court",
]
AREAS = ["Criminal", "Family", "Property", "Consumer", "Civil", "Corporate", "Labour", "Cyber"]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB uploads
CORS(app)
os.makedirs(UPLOAD_DIR, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('client','advocate','admin')),
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS advocates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
  bar_no TEXT UNIQUE NOT NULL, council TEXT NOT NULL, court TEXT NOT NULL,
  areas TEXT NOT NULL, languages TEXT NOT NULL,
  experience INTEGER NOT NULL, fee INTEGER NOT NULL, bio TEXT,
  letter_file TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advocate_id INTEGER NOT NULL REFERENCES advocates(id),
  client_id INTEGER NOT NULL REFERENCES users(id),
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  comment TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(advocate_id, client_id));
CREATE TABLE IF NOT EXISTS consultations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advocate_id INTEGER NOT NULL REFERENCES advocates(id),
  client_id INTEGER NOT NULL REFERENCES users(id),
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN ('requested','accepted','declined','closed')),
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER, action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
"""


# ---------------------------------------------------------------- helpers
def now():
    return dt.datetime.utcnow().isoformat(timespec="seconds")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def q(sql, args=(), one=False):
    cur = db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def audit(action, detail=""):
    uid = getattr(g, "user", {}).get("id")
    run("INSERT INTO audit_log(user_id,action,detail,created_at) VALUES(?,?,?,?)",
        (uid, action, detail, now()))


def err(msg, code=400):
    return jsonify({"error": msg}), code


def make_token(uid, role):
    payload = {"sub": str(uid), "role": role,
               "exp": dt.datetime.utcnow() + dt.timedelta(hours=8)}
    return jwt.encode(payload, SECRET, algorithm="HS256")


def auth(*roles):
    """Require a valid JWT, optionally restricted to the given roles."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            h = request.headers.get("Authorization", "")
            if not h.startswith("Bearer "):
                return err("Missing token", 401)
            try:
                data = jwt.decode(h[7:], SECRET, algorithms=["HS256"])
            except jwt.PyJWTError:
                return err("Invalid or expired token", 401)
            g.user = {"id": int(data["sub"]), "role": data["role"]}
            if roles and g.user["role"] not in roles:
                return err("Forbidden for your role", 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def adv_dict(r):
    return {
        "id": r["id"], "name": r["name"], "bar_no": r["bar_no"], "council": r["council"],
        "court": r["court"], "areas": json.loads(r["areas"]),
        "languages": json.loads(r["languages"]), "experience": r["experience"],
        "fee": r["fee"], "bio": r["bio"], "status": r["status"],
        "rating": round(r["rating"] or 0, 2) if "rating" in r.keys() else 0,
        "review_count": r["review_count"] if "review_count" in r.keys() else 0,
        "verified": r["status"] == "approved",
    }


ADV_SELECT = """SELECT a.*, u.name, COALESCE(AVG(r.rating),0) AS rating, COUNT(r.id) AS review_count
                FROM advocates a JOIN users u ON u.id=a.user_id
                LEFT JOIN reviews r ON r.advocate_id=a.id """


def search_advocates(court="", area="", language="", sort="rating", limit=50):
    where, args = ["a.status='approved'"], []
    if court:
        where.append("a.court=?")
        args.append(court)
    rows = q(ADV_SELECT + "WHERE " + " AND ".join(where) + " GROUP BY a.id", args)
    out = [adv_dict(r) for r in rows]
    if area:
        out = [a for a in out if area in a["areas"]]
    if language:
        out = [a for a in out if language in a["languages"]]
    keys = {"rating": lambda a: (-a["rating"], -a["review_count"]),
            "fee": lambda a: a["fee"], "experience": lambda a: -a["experience"]}
    out.sort(key=keys.get(sort, keys["rating"]))
    return out[:limit]


# ---------------------------------------------------------------- public
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return {"courts": COURTS, "areas": AREAS}


@app.post("/api/auth/register")
def register():
    d = request.get_json(silent=True) or {}
    name, email = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower()
    phone, pw, role = (d.get("phone") or "").strip(), d.get("password") or "", d.get("role", "client")
    if role not in ("client", "advocate"):
        return err("Role must be client or advocate")
    if len(name) < 2:
        return err("Name is required")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return err("Valid email is required")
    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return err("Enter a valid 10-digit Indian mobile number")
    if len(pw) < 8:
        return err("Password must be at least 8 characters")
    try:
        uid = run("INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                  (name, email, phone, generate_password_hash(pw), role, now()))
    except sqlite3.IntegrityError:
        return err("Email already registered", 409)
    return {"token": make_token(uid, role), "role": role, "name": name}, 201


@app.post("/api/auth/login")
def login():
    d = request.get_json(silent=True) or {}
    u = q("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),), one=True)
    if not u or not check_password_hash(u["password_hash"], d.get("password") or ""):
        return err("Incorrect email or password", 401)
    return {"token": make_token(u["id"], u["role"]), "role": u["role"], "name": u["name"]}


@app.get("/api/advocates")
def list_advocates():
    return jsonify(search_advocates(
        request.args.get("court", ""), request.args.get("area", ""),
        request.args.get("language", ""), request.args.get("sort", "rating")))


@app.get("/api/advocates/<int:aid>")
def advocate_detail(aid):
    r = q(ADV_SELECT + "WHERE a.id=? AND a.status='approved' GROUP BY a.id", (aid,), one=True)
    if not r or r["id"] is None:
        return err("Advocate not found", 404)
    d = adv_dict(r)
    d["reviews"] = [dict(x) for x in q(
        """SELECT v.rating, v.comment, v.created_at, u.name AS client
           FROM reviews v JOIN users u ON u.id=v.client_id
           WHERE v.advocate_id=? ORDER BY v.id DESC""", (aid,))]
    return d


@app.post("/api/chat")
def chat():
    d = request.get_json(silent=True) or {}
    res = answer(d.get("message", ""))
    court = d.get("court", "")
    suggestions = []
    if res["area"]:
        suggestions = search_advocates(court, res["area"], limit=3) or search_advocates("", res["area"], limit=3)
    return {"reply": res["reply"], "area": res["area"], "suggested_advocates": suggestions}


# ---------------------------------------------------------------- advocate
@app.post("/api/advocates/enroll")
@auth("advocate")
def enroll():
    if q("SELECT 1 FROM advocates WHERE user_id=?", (g.user["id"],), one=True):
        return err("You have already submitted an enrollment", 409)
    f = request.form
    bar_no, council = f.get("bar_no", "").strip(), f.get("council", "").strip()
    court, bio = f.get("court", ""), f.get("bio", "").strip()[:500]
    areas = [a for a in f.get("areas", "").split(",") if a in AREAS]
    langs = [l.strip() for l in f.get("languages", "").split(",") if l.strip()]
    try:
        exp, fee = int(f.get("experience", "")), int(f.get("fee", ""))
    except ValueError:
        return err("Experience and fee must be numbers")
    if not re.fullmatch(r"[A-Za-z0-9/\-]{5,30}", bar_no):
        return err("Invalid Bar Council enrollment number")
    if court not in COURTS:
        return err("Select a valid court")
    if not areas or not langs or not council:
        return err("Practice areas, languages and Bar Council are required")
    if not (0 <= exp <= 60) or fee < 0:
        return err("Invalid experience or fee")
    file = request.files.get("letter")
    if not file or not file.filename:
        return err("Bar Council approval letter is required")
    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return err("Letter must be PDF, JPG or PNG")
    stored = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, stored))
    try:
        aid = run("""INSERT INTO advocates(user_id,bar_no,council,court,areas,languages,experience,fee,bio,letter_file,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (g.user["id"], bar_no, council, court, json.dumps(areas), json.dumps(langs),
                   exp, fee, bio, stored, now()))
    except sqlite3.IntegrityError:
        os.remove(os.path.join(UPLOAD_DIR, stored))
        return err("This enrollment number is already registered", 409)
    audit("ADVOCATE_ENROLLED", f"advocate {aid}")
    return {"id": aid, "status": "pending"}, 201


@app.get("/api/me/advocate")
@auth("advocate")
def my_profile():
    r = q(ADV_SELECT + "WHERE a.user_id=? GROUP BY a.id", (g.user["id"],), one=True)
    if not r or r["id"] is None:
        return err("No enrollment yet", 404)
    return adv_dict(r)


# ---------------------------------------------------------------- client
@app.post("/api/advocates/<int:aid>/reviews")
@auth("client")
def add_review(aid):
    d = request.get_json(silent=True) or {}
    if not q("SELECT 1 FROM advocates WHERE id=? AND status='approved'", (aid,), one=True):
        return err("Advocate not found", 404)
    try:
        rating = int(d.get("rating"))
    except (TypeError, ValueError):
        return err("Rating must be 1 to 5")
    comment = (d.get("comment") or "").strip()[:500]
    if not 1 <= rating <= 5 or len(comment) < 3:
        return err("Rating 1-5 and a comment are required")
    try:
        run("INSERT INTO reviews(advocate_id,client_id,rating,comment,created_at) VALUES(?,?,?,?,?)",
            (aid, g.user["id"], rating, comment, now()))
    except sqlite3.IntegrityError:
        return err("You have already reviewed this advocate", 409)
    audit("REVIEW_ADDED", f"advocate {aid}")
    return {"ok": True}, 201


@app.post("/api/advocates/<int:aid>/consult")
@auth("client")
def consult(aid):
    d = request.get_json(silent=True) or {}
    msg = (d.get("message") or "").strip()[:1000]
    if len(msg) < 5:
        return err("Please describe your case")
    if not q("SELECT 1 FROM advocates WHERE id=? AND status='approved'", (aid,), one=True):
        return err("Advocate not found", 404)
    cid = run("INSERT INTO consultations(advocate_id,client_id,message,created_at) VALUES(?,?,?,?)",
              (aid, g.user["id"], msg, now()))
    audit("CONSULT_REQUESTED", f"consultation {cid}")
    return {"id": cid, "status": "requested"}, 201


@app.get("/api/consultations")
@auth("client", "advocate")
def my_consultations():
    if g.user["role"] == "client":
        rows = q("""SELECT c.*, u.name AS advocate FROM consultations c
                    JOIN advocates a ON a.id=c.advocate_id JOIN users u ON u.id=a.user_id
                    WHERE c.client_id=? ORDER BY c.id DESC""", (g.user["id"],))
    else:
        rows = q("""SELECT c.*, u.name AS client, u.phone AS client_phone FROM consultations c
                    JOIN advocates a ON a.id=c.advocate_id JOIN users u ON u.id=c.client_id
                    WHERE a.user_id=? ORDER BY c.id DESC""", (g.user["id"],))
    return jsonify([dict(r) for r in rows])


@app.patch("/api/consultations/<int:cid>")
@auth("advocate")
def update_consultation(cid):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("accepted", "declined", "closed"):
        return err("Invalid status")
    c = q("""SELECT c.id FROM consultations c JOIN advocates a ON a.id=c.advocate_id
             WHERE c.id=? AND a.user_id=?""", (cid, g.user["id"]), one=True)
    if not c:
        return err("Consultation not found", 404)
    run("UPDATE consultations SET status=? WHERE id=?", (status, cid))
    audit("CONSULT_" + status.upper(), f"consultation {cid}")
    return {"ok": True}


# ---------------------------------------------------------------- admin
@app.get("/api/admin/pending")
@auth("admin")
def pending():
    rows = q("""SELECT a.*, u.name, u.email, u.phone FROM advocates a
                JOIN users u ON u.id=a.user_id WHERE a.status='pending' ORDER BY a.id""")
    out = []
    for r in rows:
        d = adv_dict(r)
        d.update(email=r["email"], phone=r["phone"], letter_url=f"/api/admin/letters/{r['letter_file']}")
        out.append(d)
    return jsonify(out)


@app.get("/api/admin/letters/<path:fname>")
@auth("admin")
def letter(fname):
    return send_from_directory(UPLOAD_DIR, secure_filename(fname))


@app.post("/api/admin/advocates/<int:aid>/verify")
@auth("admin")
def verify(aid):
    approve = bool((request.get_json(silent=True) or {}).get("approve"))
    if not q("SELECT 1 FROM advocates WHERE id=?", (aid,), one=True):
        return err("Advocate not found", 404)
    run("UPDATE advocates SET status=? WHERE id=?", ("approved" if approve else "rejected", aid))
    audit("ADVOCATE_APPROVED" if approve else "ADVOCATE_REJECTED", f"advocate {aid}")
    return {"ok": True, "status": "approved" if approve else "rejected"}


@app.get("/api/admin/audit")
@auth("admin")
def audit_log():
    return jsonify([dict(r) for r in q("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")])


# ---------------------------------------------------------------- startup
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            c.execute("INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                      ("Administrator", ADMIN_EMAIL, "", generate_password_hash(ADMIN_PASSWORD), "admin", now()))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
