import os
import uuid
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
raw_database_url = os.environ.get("DATABASE_URL", "sqlite:///back2u.db")
if raw_database_url.startswith("postgres://"):
    raw_database_url = raw_database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif raw_database_url.startswith("postgresql://"):
    raw_database_url = raw_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = raw_database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

db = SQLAlchemy(app)

class Report(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    kind = db.Column(db.String(10), nullable=False)
    type = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    colour = db.Column(db.String(80), default="")
    desc = db.Column(db.Text, default="")
    place = db.Column(db.String(200), default="")
    when = db.Column(db.String(80), default="")
    contact = db.Column(db.String(200), nullable=False)
    img = db.Column(db.Text, default="")
    ts = db.Column(db.BigInteger, nullable=False)
    status = db.Column(db.String(20), default="open", nullable=False)

    def as_dict(self):
        return {"id": self.id, "kind": self.kind, "type": self.type, "name": self.name,
                "colour": self.colour or "", "desc": self.desc or "", "place": self.place or "",
                "when": self.when or "", "contact": self.contact, "img": self.img or "",
                "ts": self.ts, "status": self.status}

with app.app_context():
    db.create_all()

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/api/reports")
def list_reports():
    rows = Report.query.order_by(Report.ts.desc()).limit(500).all()
    return jsonify([row.as_dict() for row in rows])

@app.post("/api/reports")
def create_report():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind", "")).lower()
    name = str(data.get("name", "")).strip()
    item_type = str(data.get("type", "")).strip()
    contact = str(data.get("contact", "")).strip()
    if kind not in {"lost", "found"} or not name or not item_type or not contact:
        return jsonify({"error": "kind, type, name and contact are required"}), 400
    report = Report(
        id="r" + uuid.uuid4().hex, kind=kind, type=item_type[:80], name=name[:160],
        colour=str(data.get("colour", ""))[:80], desc=str(data.get("desc", "")),
        place=str(data.get("place", ""))[:200], when=str(data.get("when", ""))[:80],
        contact=contact[:200], img=str(data.get("img", "")),
        ts=int(data.get("ts") or datetime.now(timezone.utc).timestamp() * 1000), status="open")
    db.session.add(report)
    db.session.commit()
    return jsonify(report.as_dict()), 201

@app.patch("/api/reports/<report_id>")
def update_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        return jsonify({"error": "report not found"}), 404
    data = request.get_json(silent=True) or {}
    if "status" in data:
        status = str(data["status"])
        if status not in {"open", "recovered"}:
            return jsonify({"error": "invalid status"}), 400
        report.status = status
    db.session.commit()
    return jsonify(report.as_dict())

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "request too large; please use a smaller photo"}), 413

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
