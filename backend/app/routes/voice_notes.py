import json
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User, Job, ActivityTimeline
from app.routes.auth import get_current_user
from app.services import llm
from app.routes.voice import sarvam_stt

router = APIRouter(prefix="/api/voice-notes", tags=["voice-notes"])
settings = get_settings()


async def transcribe_audio(audio_base64: str) -> str:
    # Shared, verified Sarvam STT helper (multipart, en-IN). Empty on failure.
    return await sarvam_stt(audio_base64)


async def parse_job_report(transcript: str) -> dict:
    # ─── Central LLM first (heuristic fallback, never 500) ───
    if llm.is_configured():
        try:
            llm_prompt = (
                "You are an expert UK field service job report parser. Given the engineer's "
                "voice transcript below, extract a structured JSON report.\n"
                f"Transcript: {transcript}\n"
                "Return ONLY valid JSON with keys: "
                '{"work_performed": [str], "parts_used": [{name: str, quantity: int}], '
                '"findings": [str], "recommendations": [str], "duration_minutes": int, '
                '"follow_up_required": bool, "follow_up_details": str}. Use UK English."'
            )
            llm_system = (
                "You are an expert UK field service job report parser. "
                "Return ONLY valid JSON, no markdown. Use UK English spelling."
            )
            raw = await llm.complete_json(llm_prompt, system=llm_system, max_tokens=1200, temperature=0.2)

            def _str_list(v) -> list:
                if not isinstance(v, list):
                    return []
                return [str(x).strip() for x in v if str(x).strip()]

            parts: list = []
            if isinstance(raw.get("parts_used"), list):
                for p in raw["parts_used"]:
                    if isinstance(p, dict):
                        name = str(p.get("name", "") or "").strip()
                        if not name:
                            continue
                        try:
                            qty = int(p.get("quantity", 1))
                        except (TypeError, ValueError):
                            qty = 1
                        cond = str(p.get("condition", "new") or "new").strip().lower()
                        if cond not in ("new", "reused"):
                            cond = "new"
                        parts.append({"name": name, "quantity": max(qty, 1), "condition": cond})
                    elif isinstance(p, str) and p.strip():
                        parts.append({"name": p.strip(), "quantity": 1, "condition": "new"})

            try:
                duration = int(raw.get("duration_minutes", 0) or 0)
            except (TypeError, ValueError):
                duration = 0

            follow_up = bool(raw.get("follow_up_required", False))

            return {
                "work_performed": _str_list(raw.get("work_performed")),
                "parts_used": parts,
                "findings": _str_list(raw.get("findings")),
                "recommendations": _str_list(raw.get("recommendations")),
                "duration_minutes": max(duration, 0),
                "follow_up_required": follow_up,
                "follow_up_details": str(raw.get("follow_up_details", "") or ""),
            }
        except Exception:
            pass
    # (Unverified Sarvam chat endpoint removed — DeepSeek above is the
    # reasoning path. Empty report fallback below.)
    return {
        "work_performed": [],
        "parts_used": [],
        "findings": [],
        "recommendations": [],
        "duration_minutes": 0,
        "follow_up_required": False,
        "follow_up_details": ""
    }


def build_report_markdown(data: dict) -> str:
    lines = ["# Job Report\n"]

    if data.get("work_performed"):
        lines.append("## Work Performed")
        for item in data["work_performed"]:
            lines.append(f"- [x] {item}")
        lines.append("")

    if data.get("parts_used"):
        lines.append("## Parts Used")
        lines.append("| Part | Qty | Condition |")
        lines.append("|------|-----|-----------|")
        for part in data["parts_used"]:
            lines.append(f"| {part['name']} | {part['quantity']} | {part['condition']} |")
        lines.append("")

    if data.get("findings"):
        lines.append("## Findings")
        for f in data["findings"]:
            lines.append(f"- {f}")
        lines.append("")

    if data.get("recommendations"):
        lines.append("## Recommendations")
        for r in data["recommendations"]:
            lines.append(f"- {r}")
        lines.append("")

    duration = data.get("duration_minutes", 0)
    if duration:
        hrs = duration // 60
        mins = duration % 60
        lines.append(f"## Duration\n{hrs}h {mins}m\n")

    if data.get("follow_up_required"):
        lines.append(f"## Follow-up Required\n{data.get('follow_up_details', 'Yes')}\n")

    return "\n".join(lines)


async def refine_transcript_ai(transcript: str, style: str) -> str:
    style_instructions = {
        "professional": "Rewrite in a professional, formal tone suitable for customer-facing reports. Use clear, precise language.",
        "casual": "Rewrite in a casual, friendly tone while keeping all technical details accurate.",
        "detailed": "Expand and add more detail to every observation. Be thorough and descriptive about each finding and action."
    }
    # ─── Central LLM first (heuristic fallback, never 500) ───
    if llm.is_configured():
        try:
            instruction = style_instructions.get(style, style_instructions["professional"])
            system = (
                "Rewrite as a professional UK trades job note. "
                f"{instruction} Preserve all technical accuracy. Use UK English spelling. "
                "Return only the refined text."
            )
            refined = await llm.complete(transcript, system=system, max_tokens=1200, temperature=0.4)
            if refined and refined.strip():
                return refined.strip()
        except Exception:
            pass
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sarvam.ai/chat-completions",
                headers={
                    "api-subscription-key": settings.SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sarvam-2b-v0.5",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are a UK field service report editor. {style_instructions.get(style, style_instructions['professional'])} Preserve all technical accuracy. Return only the refined text."
                        },
                        {"role": "user", "content": transcript}
                    ],
                    "temperature": 0.4
                }
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return transcript


@router.post("/transcribe-job")
async def transcribe_job(
    audio_base64: Optional[str] = None,
    transcript: Optional[str] = None,
    job_id: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not audio_base64 and not transcript:
        raise HTTPException(status_code=400, detail="No audio or transcript provided")

    if audio_base64 and not transcript:
        transcript = await transcribe_audio(audio_base64)

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcription failed")

    report_data = await parse_job_report(transcript)
    report_data["report_markdown"] = build_report_markdown(report_data)

    if job_id:
        try:
            result = await db.execute(select(Job).where(Job.id == UUID(job_id)))
            job = result.scalar_one_or_none()
            if job:
                job.notes = report_data["report_markdown"]
                job.ai_summary = json.dumps(report_data, default=str)
                timeline = ActivityTimeline(
                    job_id=job.id,
                    user_id=current_user.id,
                    action="voice_notes_added",
                    description="Voice job notes recorded and structured"
                )
                db.add(timeline)
                await db.commit()
        except Exception:
            pass

    return report_data


@router.post("/save")
async def save_voice_notes(
    job_id: str,
    notes: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(Job).where(Job.id == UUID(job_id)))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        report_md = build_report_markdown(notes)
        job.notes = report_md
        job.ai_summary = json.dumps(notes, default=str)

        timeline = ActivityTimeline(
            job_id=job.id,
            user_id=current_user.id,
            action="voice_notes_saved",
            description="Voice job notes saved"
        )
        db.add(timeline)
        await db.commit()
        return {"message": "Voice notes saved", "job_id": str(job.id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}")
async def get_voice_notes(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    structured = None
    if job.ai_summary:
        try:
            structured = json.loads(job.ai_summary)
        except Exception:
            pass

    return {
        "job_id": str(job.id),
        "report_markdown": job.notes,
        "structured_data": structured
    }


@router.post("/refine")
async def refine_transcript(
    transcript: str,
    style: str = "professional",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="No transcript provided")

    refined = await refine_transcript_ai(transcript, style)
    return {"refined_text": refined}
