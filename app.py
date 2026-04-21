import os
import secrets
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory, session, abort

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
              id SERIAL PRIMARY KEY,
              type TEXT NOT NULL DEFAULT 'note',
              title TEXT,
              body TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS post_likes (
              post_id INT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              ip TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (post_id, ip)
            );
            CREATE TABLE IF NOT EXISTS post_comments (
              id SERIAL PRIMARY KEY,
              post_id INT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              body TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS news_items (
              id SERIAL PRIMARY KEY,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              url TEXT NOT NULL,
              source TEXT,
              topic TEXT NOT NULL DEFAULT 'all',
              published_at DATE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute("SELECT COUNT(*) FROM posts;")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO posts (type, title, body, created_at) VALUES (%s,%s,%s,%s);",
                (
                    "update",
                    "Lean Six Sigma Green Belt — Earned!",
                    "Excited to have earned my Lean Six Sigma Green Belt while managing a full-time demanding role at EY. Looking forward to applying structured process-improvement thinking more formally to trade compliance workflows — there's a huge opportunity to make operations leaner and smarter.",
                    datetime(2025, 3, 15),
                ),
            )


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("is_admin"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*a, **k)
    return w


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else request.remote_addr) or "unknown"


# ---------- Pages ----------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.after_request
def _no_cache_in_dev(resp):
    if os.environ.get("REPLIT_DEPLOYMENT") != "1":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# ---------- Admin auth ----------
@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    pw = data.get("password", "")
    if not ADMIN_PASSWORD or pw != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid password"}), 401
    session["is_admin"] = True
    session.permanent = True
    return jsonify({"ok": True})


@app.post("/api/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@app.get("/api/admin/me")
def admin_me():
    return jsonify({"is_admin": bool(session.get("is_admin"))})


# ---------- Posts ----------
def serialize_post(row, ip):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM post_likes WHERE post_id=%s;", (row["id"],))
        likes = cur.fetchone()[0]
        cur.execute(
            "SELECT 1 FROM post_likes WHERE post_id=%s AND ip=%s;", (row["id"], ip)
        )
        liked = cur.fetchone() is not None
        cur.execute("SELECT COUNT(*) FROM post_comments WHERE post_id=%s;", (row["id"],))
        ccount = cur.fetchone()[0]
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "created_at": row["created_at"].isoformat(),
        "likes": likes,
        "liked": liked,
        "comment_count": ccount,
    }


@app.get("/api/posts")
def list_posts():
    ip = client_ip()
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM posts ORDER BY created_at DESC, id DESC;")
        rows = cur.fetchall()
    return jsonify([serialize_post(r, ip) for r in rows])


@app.post("/api/posts")
@admin_required
def create_post():
    data = request.get_json(silent=True) or {}
    ptype = (data.get("type") or "note").strip().lower()
    if ptype not in ("note", "blog", "update"):
        ptype = "note"
    title = (data.get("title") or "").strip() or None
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO posts (type, title, body) VALUES (%s,%s,%s) RETURNING *;",
            (ptype, title, body),
        )
        row = cur.fetchone()
    return jsonify(serialize_post(row, client_ip())), 201


@app.delete("/api/posts/<int:post_id>")
@admin_required
def delete_post(post_id):
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM posts WHERE id=%s;", (post_id,))
    return jsonify({"ok": True})


# ---------- Likes ----------
@app.post("/api/posts/<int:post_id>/like")
def toggle_like(post_id):
    ip = client_ip()
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM posts WHERE id=%s;", (post_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        cur.execute(
            "SELECT 1 FROM post_likes WHERE post_id=%s AND ip=%s;", (post_id, ip)
        )
        existed = cur.fetchone() is not None
        if existed:
            cur.execute(
                "DELETE FROM post_likes WHERE post_id=%s AND ip=%s;", (post_id, ip)
            )
            liked = False
        else:
            cur.execute(
                "INSERT INTO post_likes (post_id, ip) VALUES (%s,%s);", (post_id, ip)
            )
            liked = True
        cur.execute("SELECT COUNT(*) FROM post_likes WHERE post_id=%s;", (post_id,))
        count = cur.fetchone()[0]
    return jsonify({"liked": liked, "likes": count})


# ---------- Comments ----------
@app.get("/api/posts/<int:post_id>/comments")
def list_comments(post_id):
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, body, created_at FROM post_comments "
            "WHERE post_id=%s ORDER BY created_at ASC;",
            (post_id,),
        )
        rows = cur.fetchall()
    return jsonify(
        [
            {
                "id": r["id"],
                "name": r["name"],
                "body": r["body"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    )


@app.post("/api/posts/<int:post_id>/comments")
def add_comment(post_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:80]
    body = (data.get("body") or "").strip()[:2000]
    if not name or not body:
        return jsonify({"error": "name and comment required"}), 400
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT 1 FROM posts WHERE id=%s;", (post_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        cur.execute(
            "INSERT INTO post_comments (post_id, name, body) VALUES (%s,%s,%s) "
            "RETURNING id, name, body, created_at;",
            (post_id, name, body),
        )
        r = cur.fetchone()
    return jsonify(
        {
            "id": r["id"],
            "name": r["name"],
            "body": r["body"],
            "created_at": r["created_at"].isoformat(),
        }
    ), 201


# ---------- Curated News ----------
ALLOWED_TOPICS = {"all", "export controls", "tariffs", "sanctions", "fta", "customs"}


@app.get("/api/news")
def list_news():
    topic = (request.args.get("topic") or "").strip().lower()
    sql = "SELECT id, title, summary, url, source, topic, published_at, created_at FROM news_items"
    args = []
    if topic and topic != "all" and topic in ALLOWED_TOPICS:
        sql += " WHERE topic = %s"
        args.append(topic)
    sql += " ORDER BY COALESCE(published_at, created_at::date) DESC, id DESC LIMIT 60;"
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, args)
        rows = cur.fetchall()
    return jsonify(
        [
            {
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"],
                "url": r["url"],
                "source": r["source"],
                "topic": r["topic"],
                "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    )


@app.post("/api/news")
@admin_required
def create_news():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()[:240]
    summary = (data.get("summary") or "").strip()[:600]
    url = (data.get("url") or "").strip()[:1000]
    source = (data.get("source") or "").strip()[:120] or None
    topic = (data.get("topic") or "all").strip().lower()
    published_at = (data.get("published_at") or "").strip() or None
    if topic not in ALLOWED_TOPICS:
        topic = "all"
    if not title or not summary or not url:
        return jsonify({"error": "title, summary, url required"}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "url must start with http(s)://"}), 400
    pub = None
    if published_at:
        try:
            pub = datetime.strptime(published_at, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "published_at must be YYYY-MM-DD"}), 400
    with db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO news_items (title, summary, url, source, topic, published_at) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, title, summary, url, source, topic, published_at, created_at;",
            (title, summary, url, source, topic, pub),
        )
        r = cur.fetchone()
    return jsonify(
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
            "url": r["url"],
            "source": r["source"],
            "topic": r["topic"],
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "created_at": r["created_at"].isoformat(),
        }
    ), 201


@app.delete("/api/news/<int:news_id>")
@admin_required
def delete_news(news_id):
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM news_items WHERE id=%s;", (news_id,))
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
