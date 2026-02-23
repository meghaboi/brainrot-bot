from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import httpx

from app.db import get_conn


class PipelineError(RuntimeError):
    pass


def get_settings() -> dict[str, str | None]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return dict(row) if row else {}


def update_settings(payload: dict[str, str]) -> None:
    fields = [
        "gemini_api_key",
        "veo_api_key",
        "youtube_access_token",
        "instagram_access_token",
        "youtube_channel_id",
        "instagram_account_id",
    ]
    sets = ", ".join(f"{f} = ?" for f in fields)
    values = [payload.get(f, "").strip() or None for f in fields]
    with get_conn() as conn:
        conn.execute(f"UPDATE settings SET {sets} WHERE id = 1", values)


async def generate_ideas(topic: str, count: int = 8) -> list[str]:
    settings = get_settings()
    gemini_key = settings.get("gemini_api_key")
    if not gemini_key:
        raise PipelineError("Gemini API key is missing.")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
    prompt = (
        "Generate viral, short-form, high-retention but policy-safe video ideas. "
        f"Topic: {topic}. Return exactly {count} concise ideas as a JSON array of strings."
    )

    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            f"{url}?key={gemini_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        response.raise_for_status()
        data = response.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError("Gemini response was not valid JSON.") from exc

    return [str(item) for item in parsed][:count]


async def generate_script(job: dict[str, Any]) -> str:
    settings = get_settings()
    gemini_key = settings.get("gemini_api_key")
    if not gemini_key:
        raise PipelineError("Gemini API key is missing.")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
    prompt = (
        "Write a 35-50 second short-video script with hook, payoff, and CTA. "
        "Tone: energetic but compliant. "
        f"Niche: {job['niche']}. Title concept: {job['title']}. Tone style: {job['tone']}. "
        f"Extra constraints: {job['prompt_extra'] or 'none'}"
    )

    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            f"{url}?key={gemini_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        response.raise_for_status()
        data = response.json()

    return data["candidates"][0]["content"]["parts"][0]["text"]


async def generate_video_with_veo(script: str) -> str:
    settings = get_settings()
    veo_key = settings.get("veo_api_key")
    if not veo_key:
        raise PipelineError("Veo API key is missing.")

    # Placeholder endpoint: replace with official Veo endpoint when available to your account.
    url = "https://veo.googleapis.com/v1/videos:generate"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {veo_key}"},
            json={"prompt": script, "format": "vertical_9_16", "duration_seconds": 45},
        )

    if response.status_code >= 400:
        raise PipelineError(
            "Veo generation failed. Update the endpoint/payload for your Veo account access."
        )

    data = response.json()
    return data.get("video_url", "")


async def upload_to_youtube(video_url: str, title: str, description: str) -> str:
    settings = get_settings()
    token = settings.get("youtube_access_token")
    channel_id = settings.get("youtube_channel_id")
    if not token or not channel_id:
        raise PipelineError("YouTube token or channel id missing.")

    # Simplified metadata create call; actual media upload is resumable and multi-step.
    url = "https://www.googleapis.com/youtube/v3/videos?part=snippet,status"
    payload = {
        "snippet": {"channelId": channel_id, "title": title, "description": description},
        "status": {"privacyStatus": "public"},
    }

    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )

    if response.status_code >= 400:
        raise PipelineError("YouTube upload failed (metadata call).")

    data = response.json()
    return f"https://youtube.com/watch?v={data.get('id', 'pending')}"


async def upload_to_instagram(video_url: str, caption: str) -> str:
    settings = get_settings()
    token = settings.get("instagram_access_token")
    account_id = settings.get("instagram_account_id")
    if not token or not account_id:
        raise PipelineError("Instagram token or account id missing.")

    # Graph API flow simplified into single call for demo architecture.
    url = f"https://graph.facebook.com/v20.0/{account_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    }

    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(url, data=payload)

    if response.status_code >= 400:
        raise PipelineError("Instagram publish request failed.")

    data = response.json()
    return f"https://instagram.com/reel/{data.get('id', 'pending')}"


async def run_job(job_id: int) -> None:
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return

    job_dict = dict(job)
    try:
        script = await generate_script(job_dict)
        video_url = await generate_video_with_veo(script)
        yt_url = await upload_to_youtube(video_url, job_dict["title"], script)
        ig_url = await upload_to_instagram(video_url, script[:2200])
        status = "posted"
        log = f"[{datetime.now(timezone.utc).isoformat()}] Script generated and posted.\nYT: {yt_url}\nIG: {ig_url}"
    except Exception as exc:  # keep scheduler alive
        status = "failed"
        log = f"[{datetime.now(timezone.utc).isoformat()}] Failed: {exc}"

    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, output_log = ? WHERE id = ?",
            (status, log, job_id),
        )
