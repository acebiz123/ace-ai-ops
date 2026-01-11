import os, json, datetime as dt
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
TBL_NOTES = os.getenv("AIRTABLE_TABLE_NOTES", "AI Notes")
TBL_PROFILES = os.getenv("AIRTABLE_TABLE_PROFILES", "Profiles")

AGENT_SHARED_SECRET = os.getenv("AGENT_SHARED_SECRET", "")

def guard_secret(x_agent_key: Optional[str]) -> None:
    if AGENT_SHARED_SECRET and x_agent_key != AGENT_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_env() -> None:
    missing = []
    if not OPENAI_API_KEY: missing.append("OPENAI_API_KEY")
    if not AIRTABLE_API_KEY: missing.append("AIRTABLE_API_KEY")
    if not AIRTABLE_BASE_ID: missing.append("AIRTABLE_BASE_ID")
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing env vars: {', '.join(missing)}")

def airtable_url(table: str) -> str:
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}"

async def airtable_find_profile(profile_key: str) -> Optional[Dict[str, Any]]:
    formula = f"{{Profile Key}}='{profile_key}'"
    params = {"filterByFormula": formula, "maxRecords": 1}
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(airtable_url(TBL_PROFILES), params=params, headers=headers)
        r.raise_for_status()
        recs = r.json().get("records", [])
        return recs[0] if recs else None

async def airtable_create_note(fields: Dict[str, Any]) -> None:
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    payload = {"fields": fields}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(airtable_url(TBL_NOTES), headers=headers, json=payload)
        r.raise_for_status()

async def openai_json(system: str, user_obj: Dict[str, Any]) -> Dict[str, Any]:
    url = "https://api.openai.com/v1/responses"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_obj)},
        ],
        "text": {"format": {"type": "json_object"}}
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        out = r.json()
        text = out["output"][0]["content"][0]["text"]
        return json.loads(text)

SYS_INSIGHTS = "You are the Insights Agent. Return JSON only."
SYS_STRATEGY = "You are the Strategy Agent. Return JSON only."
SYS_PRODUCTION = "You are the Production Agent for ComfyUI/FLUX. Return JSON only."
SYS_REVENUE = "You are the Revenue Agent. Return JSON only."
SYS_OPS = "You are the Ops Agent. Return JSON only."
SYS_CEO = "You are the CEO Copilot. Return JSON with keys: answer, recommended_actions, risks_alerts."

app = FastAPI(title="Ace AI Ops Agent Server", version="0.1.0")

class BlowupEvent(BaseModel):
    profile_key: str
    platform: str
    handle: str
    hook_text: Optional[str] = None
    media_type: str = "video"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    baseline: Dict[str, Any] = Field(default_factory=dict)

class MissedPostItem(BaseModel):
    profile_key: str
    platform: str
    handle: str
    hours_since_last_post: float

class MissedPostEvent(BaseModel):
    items: List[MissedPostItem]

class ShadowbanEvent(BaseModel):
    profile_key: str
    platform: str
    handle: str
    flag_reason: Optional[str] = None

class RevenueEvent(BaseModel):
    date: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)

class AskRequest(BaseModel):
    question: str
    context: Dict[str, Any] = Field(default_factory=dict)

@app.get("/health")
async def health():
    return {"ok": True, "ts": dt.datetime.utcnow().isoformat()}

@app.post("/events/blowup")
async def blowup(payload: BlowupEvent, x_agent_key: Optional[str] = Header(default=None)):
    guard_secret(x_agent_key); require_env()
    insights = await openai_json(SYS_INSIGHTS, payload.model_dump())
    strategy = await openai_json(SYS_STRATEGY, {"insights": insights, "constraints": {"one_to_one": True, "daily_posting": True}})
    production = await openai_json(SYS_PRODUCTION, {"strategy": strategy, "tooling": {"comfyui": True, "flux": True}})
    prof = await airtable_find_profile(payload.profile_key)
    note = {
        "Created At": dt.datetime.utcnow().isoformat(),
        "Event Type": "Blowup",
        "Summary": f"{payload.platform} {payload.handle}: plan generated",
        "JSON": json.dumps({"insights": insights, "strategy": strategy, "production": production}, ensure_ascii=False),
    }
    if prof: note["Profile"] = [prof["id"]]
    await airtable_create_note(note)
    return {"insights": insights, "strategy": strategy, "production": production}

@app.post("/events/missed_post")
async def missed_post(payload: MissedPostEvent, x_agent_key: Optional[str] = Header(default=None)):
    guard_secret(x_agent_key); require_env()
    ops = await openai_json(SYS_OPS, payload.model_dump())
    await airtable_create_note({
        "Created At": dt.datetime.utcnow().isoformat(),
        "Event Type": "MissedPost",
        "Summary": f"Missed posts: {len(payload.items)}",
        "JSON": json.dumps({"ops": ops}, ensure_ascii=False),
    })
    return {"ops": ops}

@app.post("/events/shadowban")
async def shadowban(payload: ShadowbanEvent, x_agent_key: Optional[str] = Header(default=None)):
    guard_secret(x_agent_key); require_env()
    plan = await openai_json(SYS_STRATEGY, {"event": payload.model_dump(), "goal": "mitigation"})
    prof = await airtable_find_profile(payload.profile_key)
    note = {
        "Created At": dt.datetime.utcnow().isoformat(),
        "Event Type": "Shadowban",
        "Summary": f"{payload.platform} {payload.handle}: mitigation plan generated",
        "JSON": json.dumps({"plan": plan}, ensure_ascii=False),
    }
    if prof: note["Profile"] = [prof["id"]]
    await airtable_create_note(note)
    return {"plan": plan}

@app.post("/events/revenue_update")
async def revenue_update(payload: RevenueEvent, x_agent_key: Optional[str] = Header(default=None)):
    guard_secret(x_agent_key); require_env()
    rev = await openai_json(SYS_REVENUE, payload.model_dump())
    await airtable_create_note({
        "Created At": dt.datetime.utcnow().isoformat(),
        "Event Type": "Revenue",
        "Summary": f"Revenue update {payload.date}",
        "JSON": json.dumps({"revenue": rev}, ensure_ascii=False),
    })
    return {"revenue": rev}

@app.post("/ask")
async def ask(payload: AskRequest, x_agent_key: Optional[str] = Header(default=None)):
    guard_secret(x_agent_key); require_env()
    out = await openai_json(SYS_CEO, payload.model_dump())
    return out
