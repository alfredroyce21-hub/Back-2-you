# Back2U — Flask + Gemini Flash image matching

Back2U stores lost/found reports in PostgreSQL on Render (or SQLite locally) and uses Gemini Flash to suggest possible matches between report photos.

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set a Gemini API key in your environment before running the app:

**Windows PowerShell**
```powershell
$env:GEMINI_API_KEY="your-google-ai-studio-api-key"
python app.py
```

**macOS/Linux**
```bash
export GEMINI_API_KEY="your-google-ai-studio-api-key"
python app.py
```

Open http://127.0.0.1:5000. SQLite is created automatically for local development.

## Deploy / update on Render

1. Put `app.py`, `requirements.txt`, `render.yaml`, `README.md`, and `templates/index.html` at the root of the GitHub repository (or set Render's Root Directory to the folder containing those files).
2. Push the updated files to GitHub. Render will install the new `google-genai` dependency and redeploy.
3. In Render Dashboard → your Back2U web service → **Environment**, add `GEMINI_API_KEY` with your key from Google AI Studio. Optionally set `GEMINI_MODEL`; default is `gemini-3.8-flash`.
4. Save changes and redeploy. Never put the API key in HTML/JavaScript or commit it to GitHub.
5. Open `/health`; it should return `"status":"ok"` and `"gemini_enabled":true` when the key is configured.

## How image matching works

- When a report with a photo is submitted, the server selects up to 8 recent open reports of the opposite kind that also have photos.
- Gemini compares the submitted image and report details against those candidates, returning evidence-based suggestions with a relevance score.
- Suggestions scoring 60/100 or higher are stored and displayed on the report card. The score is not a probability and is not proof of ownership.
- The report still saves if the Gemini key is missing or the AI call fails. The existing text-based matching continues to work.
- AI suggestions run on report submission; old reports are not automatically reprocessed whenever a new report is posted.

## API

- `GET /api/reports`
- `POST /api/reports`
- `PATCH /api/reports/<id>`
- `GET /health`

Photos are currently stored as resized data URLs in the database. For a larger production deployment, use object storage for photos, add authentication and rate limiting, and avoid exposing contact information to every visitor.
