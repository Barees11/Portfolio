# Sunil Kumar Portfolio Site

Single-page portfolio (`index.html`) for global trade compliance work, with a small Flask backend for owner-managed posts and visitor likes/comments.

## Stack
- **Frontend**: Static `index.html` (vanilla HTML/CSS/JS), served by Flask.
- **Backend**: Flask (`app.py`) on port 5000.
- **Database**: Replit-managed Postgres (uses `DATABASE_URL`).
- **Auth**: Single-admin (owner) login via `ADMIN_PASSWORD` secret + signed session cookie.

## Static assets
- `static/profile.jpg` — hero profile photo (hard-coded; no upload UI on the frontend).
- `static/SUNIL_KUMAR_CV.pdf` — resume; downloaded by the "Hire Me → Download Resume" link.

## API
- `POST /api/admin/login` `{password}` · `POST /api/admin/logout` · `GET /api/admin/me`
- `GET /api/posts` (public) · `POST /api/posts` (admin) · `DELETE /api/posts/{id}` (admin)
- `POST /api/posts/{id}/like` (anonymous, dedup by client IP — toggles)
- `GET /api/posts/{id}/comments` · `POST /api/posts/{id}/comments` `{name, body}` (anonymous)

## Database schema
Tables auto-created on startup: `posts`, `post_likes(post_id, ip)`, `post_comments`. Seeded with one Lean Six Sigma update post on first run.

## Run
- Workflow `Start application`: `python3 app.py` on port 5000 (binds 0.0.0.0).
- Deployment: autoscale, `gunicorn -b 0.0.0.0:5000 --workers 2 app:app`.

## Secrets
- `ADMIN_PASSWORD` — owner login password.
- `SESSION_SECRET` — Flask session cookie signing key (auto-managed).
- `DATABASE_URL` — Postgres connection (auto-managed).

## Custom domain
- `www.sunilkumarb.in` (CNAME).
