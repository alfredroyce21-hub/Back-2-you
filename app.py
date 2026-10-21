import base64
import json
import os
import re
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

class AiMatch(db.Model):
    """AI suggestions generated when a new report is submitted."""
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.String(64), db.ForeignKey("report.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = db.Column(db.String(64), db.ForeignKey("report.id", ondelete="CASCADE"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), default="")

with app.app_context():
    db.create_all()


def attach_ai_matches(report_dicts):
    if not report_dicts:
        return report_dicts
    ids = [r["id"] for r in report_dicts]
    matches = AiMatch.query.filter(AiMatch.report_id.in_(ids)).all()
    by_report = {}
    for match in matches:
        by_report.setdefault(match.report_id, []).append({
            "id": match.candidate_id, "score": match.score, "reason": match.reason or ""
        })
    for report in report_dicts:
        report["ai_matches"] = sorted(by_report.get(report["id"], []), key=lambda m: m["score"], reverse=True)
    return report_dicts


def image_parts(data_url):
    """Decode a data URL safely for Gemini. Images are resized by the browser already."""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or "," not in data_url:
        return None
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    if not raw or len(raw) > 2 * 1024 * 1024:
        return None
    return raw, mime


def ai_compare_report(report, candidates):
    """Ask Gemini Flash to rank only the supplied candidate reports; fail safely."""
    api_key = os.environ.get("GEMINI_API_KEY")
    target_image = image_parts(report.img)
    if not api_key or not target_image or not candidates:
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = (
            "You help match lost and found property reports at a college. Compare the target image "
            "with each candidate image and the provided text. Return ONLY valid JSON in this shape: "
            '{"matches":[{"id":"exact candidate ID","score":0,"reason":"short evidence-based reason"}]}. '
            "Score visual/textual compatibility from 0 to 100; this is a rough relevance score, NOT a probability. "
            "Consider item type, color, shape, brand, visible markings, and report descriptions. Similar generic objects "
            "are not enough for a high score. Never invent a candidate ID. Include only plausible matches with score >= 60, "
            "at most 5 matches, and explain any uncertainty. Do not infer or expose private information.\n\n"
            f"TARGET ({report.kind}): id={report.id}; type={report.type}; name={report.name}; "
            f"colour={report.colour or 'unspecified'}; description={report.desc or 'none'}; "
            f"place={report.place or 'unspecified'}; date/time={report.when or 'unspecified'}.\n"
            "The target image follows, then candidate entries with IDs and details."
        )
        contents = [prompt, types.Part.from_bytes(data=target_image[0], mime_type=target_image[1])]
        for candidate in candidates:
            parsed = image_parts(candidate.img)
            if not parsed:
                continue
            contents.append(
                f"CANDIDATE id={candidate.id}; kind={candidate.kind}; type={candidate.type}; "
                f"name={candidate.name}; colour={candidate.colour or 'unspecified'}; "
                f"description={candidate.desc or 'none'}; place={candidate.place or 'unspecified'}; "
                f"date/time={candidate.when or 'unspecified'}. Candidate ID must be copied exactly."
            )
            contents.append(types.Part.from_bytes(data=parsed[0], mime_type=parsed[1]))

        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1200,
            ),
        )
        raw_text = (response.text or "").strip()
        data = json.loads(raw_text)
        allowed = {c.id for c in candidates}
        clean = []
        seen = set()
        for item in data.get("matches", []):
            candidate_id = str(item.get("id", ""))
            if candidate_id not in allowed or candidate_id in seen:
                continue
            try:
                score = max(0, min(100, int(item.get("score", 0))))
            except (TypeError, ValueError):
                continue
            if score < 60:
                continue
            reason = re.sub(r"\s+", " ", str(item.get("reason", ""))).strip()[:500]
            clean.append({"id": candidate_id, "score": score, "reason": reason})
            seen.add(candidate_id)
        return sorted(clean, key=lambda m: m["score"], reverse=True)[:5]
    except Exception:
        app.logger.exception("Gemini image matching failed; report will still be saved")
        return []


@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok", "gemini_enabled": bool(os.environ.get("GEMINI_API_KEY"))})

@app.get("/api/reports")
def list_reports():
    rows = Report.query.order_by(Report.ts.desc()).limit(500).all()
    return jsonify(attach_ai_matches([row.as_dict() for row in rows]))

@app.post("/api/reports")
def create_report():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind", "")).lower()
    name = str(data.get("name", "")).strip()
    item_type = str(data.get("type", "")).strip()
    contact = str(data.get("contact", "")).strip()
    if kind not in {"lost", "found"} or not name or not item_type or not contact:
        return jsonify({"error": "kind, type, name and contact are required"}), 400
    img = str(data.get("img", ""))
    if img and len(img) > 3_800_000:
        return jsonify({"error": "photo is too large; please upload a smaller image"}), 413

    report = Report(
        id="r" + uuid.uuid4().hex, kind=kind, type=item_type[:80], name=name[:160],
        colour=str(data.get("colour", ""))[:80], desc=str(data.get("desc", ""))[:2000],
        place=str(data.get("place", ""))[:200], when=str(data.get("when", ""))[:80],
        contact=contact[:200], img=img,
        ts=int(data.get("ts") or datetime.now(timezone.utc).timestamp() * 1000), status="open")

    # Candidate filtering is done before calling Gemini to control latency and API usage.
    candidates = []
    if os.environ.get("GEMINI_API_KEY") and image_parts(report.img):
        candidates = (Report.query.filter_by(kind="found" if kind == "lost" else "lost", status="open")
                      .filter(Report.img.isnot(None), Report.img != "")
                      .order_by(Report.ts.desc()).limit(30).all())
        # Prefer the same item type, but keep a few different-type candidates in case reports were categorized differently.
        candidates.sort(key=lambda c: (c.type.lower() != report.type.lower(), -c.ts))
        candidates = [c for c in candidates if image_parts(c.img)][:8]

    db.session.add(report)
    db.session.commit()

    if candidates:
        matches = ai_compare_report(report, candidates)
        for match in matches:
            db.session.add(AiMatch(report_id=report.id, candidate_id=match["id"],
                                   score=match["score"], reason=match["reason"]))
        if matches:
            db.session.commit()

    result = report.as_dict()
    result["ai_matches"] = [
        {"id": m.candidate_id, "score": m.score, "reason": m.reason or ""}
        for m in sorted(AiMatch.query.filter_by(report_id=report.id).all(), key=lambda x: x.score, reverse=True)
    ]
    result["ai_matching_enabled"] = bool(os.environ.get("GEMINI_API_KEY"))
    return jsonify(result), 201

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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
