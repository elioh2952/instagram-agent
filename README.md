# Instagram AI Agent — Elio Hanna

## Setup

### 1. Install dependencies
```bash
cd instagram-agent
pip install -r requirements.txt
```

### 2. Fill in .env
```
INSTAGRAM_ACCESS_TOKEN=   # From Meta Developer App → Page Access Token
INSTAGRAM_PAGE_ID=        # Your Facebook Page ID
WEBHOOK_VERIFY_TOKEN=     # Any secret string you choose (e.g. "elio_secret_2025")
ANTHROPIC_API_KEY=        # From console.anthropic.com
```

### 3. Run the server
```bash
uvicorn main:app --reload --port 8000
```

### 4. Expose with ngrok (for Meta webhook setup)
```bash
ngrok http 8000
```
Copy the HTTPS URL (e.g. https://abc123.ngrok.io)

### 5. Configure Meta Webhook
1. Go to developers.facebook.com → Your App → Webhooks
2. Set Callback URL: `https://abc123.ngrok.io/webhook`
3. Set Verify Token: same as WEBHOOK_VERIFY_TOKEN in .env
4. Subscribe to: `messages`

---

## How It Works

### Auto-replies
Any DM to your Instagram gets automatically handled by Claude.
Claude knows who Elio is, what he offers, and how to qualify leads.

### Lead Management
```bash
# See all leads
GET /leads

# Add a lead manually
POST /leads
{ "instagram_id": "123456", "username": "someuser", "notes": "Found via hashtag #UIDesign" }

# Get conversation with someone
GET /conversations/123456
```

### Outreach (for people who messaged you first, within 24h)
```bash
# Generate a message
POST /generate-outreach
{ "context": "Runs a food brand in Beirut, posted about needing a content creator", "notes": "" }
# Returns: suggested message

# Send it
POST /send
{ "instagram_id": "123456", "message": "Hey! Saw your post about content — I do exactly that..." }
```

---

## Important: Instagram API Limits

- You can only send DMs to people who messaged you first (within 24 hours)
- Cold outreach to strangers is against Meta ToS and will get your account banned
- Use this tool for: responding to inbound leads, following up with warm leads

---

## Finding Leads (Manual Workflow)

Since the API can't auto-scrape leads, here's the recommended workflow:
1. Search relevant hashtags on Instagram manually (#UIDesignBeirut, #VideoEditorLebanon, etc.)
2. Find accounts that look like potential clients
3. Add them to your lead list with notes: `POST /leads`
4. When they message you (or you engage with their content and they reply), the bot handles the DM

For accounts you find manually, generate an outreach message with `/generate-outreach` then send it through Instagram's app directly (not API) — this keeps you within ToS.
