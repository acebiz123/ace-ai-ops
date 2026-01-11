# Ace AI Ops Agent Server (Option 1: Single Model)

This is a lightweight HTTP server that:
- Receives events from Zapier (blowup, missed post, shadowban, revenue update)
- Uses an LLM to generate actions, ComfyUI prompt variants, and concise plans
- Writes outputs into Airtable (Notes table) and returns JSON to Zapier (so Zapier can create Tasks + send SMS)

## Deploy to Railway (recommended)
1. Create a new Railway project → Deploy from GitHub (or upload this folder).
2. Set environment variables (see `.env.example`).
3. Railway will detect the Dockerfile and deploy.
4. Copy the public URL. You'll use it in Zapier Webhooks.

## Environment variables
- OPENAI_API_KEY
- OPENAI_MODEL (recommended: gpt-4.1-mini)
- AIRTABLE_API_KEY
- AIRTABLE_BASE_ID
- AIRTABLE_TABLE_NOTES (default "AI Notes")
- AIRTABLE_TABLE_PROFILES (default "Profiles")

Optional:
- AGENT_SHARED_SECRET (protect endpoints; Zapier sends header X-AGENT-KEY)

## Endpoints
- POST /events/blowup
- POST /events/missed_post
- POST /events/shadowban
- POST /events/revenue_update
- POST /ask

See `zapier_payload_examples/` for JSON payload samples.

Security:
If you set AGENT_SHARED_SECRET, include header:
X-AGENT-KEY: <secret>
