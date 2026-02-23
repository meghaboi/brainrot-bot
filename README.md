# Brainrot Automation Studio

A starter web app that:

- Accepts Gemini, Veo, YouTube, and Instagram credentials.
- Generates short-form "rage bait" style ideas using Gemini.
- Schedules multiple automated jobs.
- For each job: generates script -> calls Veo video generation -> attempts upload to YouTube + Instagram.

> ⚠️ This project ships with integration scaffolding. You will likely need to adapt Veo and YouTube upload endpoints/payloads based on your exact API access level and OAuth flow.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Notes

- Keys are stored in local SQLite (`brainrot.db`) for convenience in this prototype.
- Production use should encrypt secrets and use proper OAuth refresh workflows.
