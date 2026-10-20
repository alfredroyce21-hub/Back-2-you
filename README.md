# Back2U — Python backend

Flask + SQLAlchemy backend for the CIT Lost & Found prototype. Reports are stored in PostgreSQL on Render (or SQLite for local development).

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The app uses SQLite by default and creates `back2u.db` automatically.

## Deploy to Render

1. Push this folder's contents to a GitHub repository (make sure `app.py`, `requirements.txt`, `render.yaml`, and `templates/index.html` are at the repository root).
2. In Render, choose **New + → Blueprint** and connect the repository. Render reads `render.yaml` and creates a Python web service plus a PostgreSQL database.
3. Confirm the database and web service are created, then open the service URL.
4. Test `/health` and then submit a lost/found report.

The app's API is `GET /api/reports`, `POST /api/reports`, and `PATCH /api/reports/<id>`. Photos are stored as resized data URLs in the database; for a larger production deployment, use object storage for photos.
