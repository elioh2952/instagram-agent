import sys
import time
import os
import random
import unicodedata
sys.stdout.reconfigure(encoding='utf-8')

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError, ClientConnectionError

from config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
from database import init_db, is_seen, mark_seen, save_message, get_followed_preference, set_followed_preference
from ai import reply

SESSION_FILE = "session.json"

# ── Human behavior simulation ────────────────────────────────────────────────

def human_typing_delay(text: str):
    """Simulate realistic typing time based on message length."""
    chars_per_second = random.uniform(4, 8)  # avg human types 4-8 chars/sec
    base_delay = len(text) / chars_per_second
    # Add random thinking/pause time
    thinking = random.uniform(1.5, 4.0)
    total = min(base_delay + thinking, 12)  # cap at 12s
    time.sleep(total)

def human_read_delay():
    """Simulate time to read the incoming message before typing."""
    time.sleep(random.uniform(1.0, 3.0))

def random_poll_interval() -> float:
    """Slightly randomize polling so it never looks perfectly mechanical."""
    return random.uniform(8, 14)

def notify_elio(username: str, message: str):
    """Send instant push notification to Elio's phone via ntfy.sh."""
    import urllib.request
    topic = os.getenv("NTFY_TOPIC", "")
    if not topic:
        print(f"[!] No NTFY_TOPIC set — skipping notification for @{username}")
        return
    try:
        body = f"@{username} wants to talk to you personally:\n\"{message[:100]}\""
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": f"Instagram: @{username} wants YOU",
                "Priority": "high",
                "Tags": "instagram,speech_balloon"
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        print(f"[NOTIFY] Elio notified about @{username}")
    except Exception as e:
        print(f"[!] Notification failed: {e}")

def is_yes(text: str) -> bool:
    yes_words = {"yes", "yeah", "yep", "sure", "ok", "okay", "fine", "agent", "assistant", "you", "go ahead", "oui", "ouais", "bien sûr"}
    return any(w in text.lower() for w in yes_words)

def is_no(text: str) -> bool:
    no_words = {"no", "nope", "nah", "personally", "elio", "himself", "real", "non", "pas", "lui"}
    return any(w in text.lower() for w in no_words)

# ── Error classifier ─────────────────────────────────────────────────────────

def classify_error(e: Exception) -> str:
    """
    Returns:
      'relogin'   — session dead, re-login and retry
      'ratelimit' — Instagram throttling, wait longer
      'network'   — connection issue, wait and retry
      'skip'      — this specific message/user can't be processed, skip it
      'retry'     — generic transient error, short wait and retry
    """
    msg = str(e).lower()
    if any(x in msg for x in ["login_required", "loginrequired", "not authorized", "401"]):
        return "relogin"
    if any(x in msg for x in ["1545003", "403 forbidden", "user not found"]):
        return "skip"
    if any(x in msg for x in ["429", "throttled", "too many requests", "rate limit", "feedback_required"]):
        return "ratelimit"
    if any(x in msg for x in ["connection", "timeout", "network", "ssl", "remotedisconnected", "connectionreset"]):
        return "network"
    return "retry"

# ── Login ────────────────────────────────────────────────────────────────────

def login(retries: int = 999) -> Client:
    """Login with infinite retries. Reuses existing session if still valid."""
    attempt = 0
    while True:
        attempt += 1
        try:
            cl = Client()
            if os.path.exists(SESSION_FILE):
                cl.load_settings(SESSION_FILE)
                # Test session with a lightweight call before doing full login
                try:
                    cl.private_request("direct_v2/inbox/", params={"limit": "1"})
                    print(f"[OK] Session valid — skipped full login")
                    return cl
                except Exception:
                    pass  # Session dead, fall through to full login
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(SESSION_FILE)
            print(f"[OK] Logged in (attempt {attempt})")
            return cl
        except Exception as e:
            wait = min(30 * attempt, 300)
            print(f"[!] Login failed (attempt {attempt}): {e} — retrying in {wait}s")
            time.sleep(wait)

# ── Instagram API helpers ────────────────────────────────────────────────────

def fetch_unread_threads(cl: Client) -> list:
    for attempt in range(5):
        try:
            data = cl.private_request("direct_v2/inbox/", params={
                "visual_message_return_type": "unseen",
                "thread_message_limit": "1",
                "persistentBadging": "true",
                "limit": "10"   # cap at 10 to stay under radar
            })
            return data.get("inbox", {}).get("threads", [])
        except ClientConnectionError as e:
            wait = 5 * (attempt + 1)
            print(f"[!] Network error fetching inbox (attempt {attempt+1}/5) — retrying in {wait}s")
            time.sleep(wait)
        except LoginRequired:
            raise
        except Exception as e:
            err_type = classify_error(e)
            if err_type == "ratelimit":
                print(f"[!] Rate limited — waiting 60s")
                time.sleep(60)
            elif err_type == "relogin":
                raise LoginRequired()
            else:
                print(f"[!] Inbox fetch error: {e}")
                time.sleep(5)
    return []

def get_thread_messages(cl: Client, thread_id: str) -> list:
    for attempt in range(3):
        try:
            data = cl.private_request(f"direct_v2/threads/{thread_id}/", params={"limit": "20"})
            return data.get("thread", {}).get("items", [])
        except Exception:
            time.sleep(3)
    return []

def build_conversation(items: list, my_id: str) -> list:
    messages = []
    for item in reversed(items):
        if item.get("item_type") != "text":
            continue
        text = item.get("text", "").strip()
        if not text:
            continue
        role = "assistant" if str(item.get("user_id")) == my_id else "user"
        messages.append({"role": role, "content": text})
    return messages

def mark_thread_read(cl: Client, thread_id: str, item_id: str):
    try:
        cl.private_request(
            f"direct_v2/threads/{thread_id}/seen/{item_id}/",
            method="POST",
            data={"use_unified_inbox": "true"}
        )
    except Exception:
        pass

def elio_follows(cl: Client, user_id: str) -> bool:
    try:
        friendship = cl.user_friendship_v1(int(user_id))
        return friendship.following
    except Exception:
        return False

def generate_reply(conversation: list) -> str:
    """Generate AI reply — infinite retry until it works."""
    attempt = 0
    while True:
        attempt += 1
        try:
            result = reply(conversation)
            if result:
                return result
        except Exception as e:
            wait = min(5 * attempt, 60)
            print(f"[!] AI error (attempt {attempt}): {e} — retrying in {wait}s")
            time.sleep(wait)

def send_message(cl: Client, response_text: str, thread_id: str, username: str) -> bool:
    """Send DM — infinite retry on transient errors, skip on hard errors."""
    attempt = 0
    while True:
        attempt += 1
        try:
            cl.direct_send(response_text, thread_ids=[thread_id])
            return True
        except Exception as e:
            err_type = classify_error(e)
            if err_type == "skip":
                print(f"[SKIP] @{username}: can't send message ({e})")
                return False
            elif err_type == "relogin":
                raise LoginRequired()
            elif err_type == "ratelimit":
                print(f"[!] Rate limited sending to @{username} — waiting 90s")
                time.sleep(90)
            else:
                wait = min(10 * attempt, 120)
                print(f"[!] Send error to @{username} (attempt {attempt}): {e} — retrying in {wait}s")
                time.sleep(wait)

# ── Core logic ───────────────────────────────────────────────────────────────

def baseline(cl: Client):
    threads = fetch_unread_threads(cl)
    count = 0
    for thread in threads:
        items = thread.get("items", [])
        if items:
            msg_id = str(items[0].get("item_id", ""))
            if msg_id and not is_seen(msg_id):
                mark_seen(msg_id)
                count += 1
    if count:
        print(f"[*] Ignored {count} old unread message(s).")

def process_inbox(cl: Client):
    my_id = str(cl.user_id)
    unread_threads = fetch_unread_threads(cl)

    if not unread_threads:
        return

    for thread in unread_threads:
        username = "unknown"
        try:
            thread_id = thread.get("thread_id", "")
            users = thread.get("users", [])
            username = users[0].get("username", "unknown") if users else "unknown"
            sender_id = str(users[0].get("pk", "")) if users else ""
            items = thread.get("items", [])
            if not items:
                continue

            latest = items[0]
            msg_id = str(latest.get("item_id", ""))
            item_type = latest.get("item_type", "?")
            from_me = str(latest.get("user_id")) == my_id

            if is_seen(msg_id) or from_me:
                continue

            if elio_follows(cl, sender_id):
                pref = get_followed_preference(sender_id)

                if pref == "agent":
                    # They chose agent — fall through to normal reply below
                    pass

                elif pref == "personal":
                    # They want Elio personally — notify and ignore
                    notify_elio(username, latest_text)
                    mark_seen(msg_id)
                    mark_thread_read(cl, thread_id, msg_id)
                    continue

                elif pref == "pending":
                    # Already asked, waiting for answer — check if this is the answer
                    if is_yes(latest_text):
                        set_followed_preference(sender_id, username, "agent")
                        response = "great, i'm here whenever you need anything"
                        human_read_delay()
                        human_typing_delay(response)
                        send_message(cl, response, thread_id, username)
                        mark_seen(msg_id)
                        mark_thread_read(cl, thread_id, msg_id)
                        continue
                    elif is_no(latest_text):
                        set_followed_preference(sender_id, username, "personal")
                        response = "got it, i'll let Elio know — he'll get back to you directly"
                        human_read_delay()
                        human_typing_delay(response)
                        send_message(cl, response, thread_id, username)
                        notify_elio(username, latest_text)
                        mark_seen(msg_id)
                        mark_thread_read(cl, thread_id, msg_id)
                        continue
                    else:
                        # Still unclear — re-ask once
                        mark_seen(msg_id)
                        continue

                else:
                    # First time this followed user DMs — ask their preference
                    set_followed_preference(sender_id, username, "pending")
                    question = "hey, do you want to chat with Elio's assistant or would you prefer to talk to Elio directly?"
                    human_read_delay()
                    human_typing_delay(question)
                    send_message(cl, question, thread_id, username)
                    mark_seen(msg_id)
                    mark_thread_read(cl, thread_id, msg_id)
                    continue

            if item_type != "text":
                mark_seen(msg_id)
                mark_thread_read(cl, thread_id, msg_id)
                continue

            latest_text = latest.get("text", "").strip()
            if not latest_text:
                mark_seen(msg_id)
                continue

            non_emoji = [c for c in latest_text if not unicodedata.category(c).startswith('So')]
            if not ''.join(non_emoji).strip():
                mark_seen(msg_id)
                mark_thread_read(cl, thread_id, msg_id)
                continue

            print(f"[IN]  @{username}: {latest_text[:80]}")

            # Simulate reading the message before responding
            human_read_delay()

            all_items = get_thread_messages(cl, thread_id)
            conversation = build_conversation(all_items, my_id)

            if not conversation:
                conversation = [{"role": "user", "content": latest_text}]
            elif conversation[-1]["role"] != "user":
                conversation.append({"role": "user", "content": latest_text})

            response_text = generate_reply(conversation)

            # Simulate typing time before sending
            human_typing_delay(response_text)

            sent = send_message(cl, response_text, thread_id, username)

            if sent:
                save_message(sender_id, "user", latest_text)
                save_message(sender_id, "assistant", response_text)
                print(f"[OUT] @{username}: {response_text[:80]}")

            mark_seen(msg_id)
            mark_thread_read(cl, thread_id, msg_id)
            time.sleep(2)  # human-like delay between replies

        except LoginRequired:
            raise
        except Exception as e:
            print(f"[!] Error on @{username}: {e}")

# ── Entry points ─────────────────────────────────────────────────────────────

def run():
    """GitHub Actions: loop for 4.5 minutes checking every 10s, self-healing."""
    init_db()
    print("[*] Logging into Instagram...")
    cl = login()
    print("[*] Polling inbox every 10s for 4.5 minutes...")
    deadline = time.time() + 270  # 4.5 minutes
    while time.time() < deadline:
        try:
            process_inbox(cl)
        except LoginRequired:
            print("[!] Session expired — re-logging in...")
            cl = login()
        except Exception as e:
            err_type = classify_error(e)
            wait = 15 if err_type == "ratelimit" else 5
            print(f"[!] Error ({err_type}): {e} — retrying in {wait}s")
            time.sleep(wait)
            continue
        time.sleep(random_poll_interval())
    print("[*] Done.")

def run_loop():
    """Local: self-healing infinite loop."""
    init_db()
    print("[*] Logging into Instagram...")
    cl = login()
    baseline(cl)
    print(f"[*] Bot is live. Checking every {POLL_INTERVAL}s. Ctrl+C to stop.\n")

    while True:
        try:
            process_inbox(cl)
        except LoginRequired:
            print("[!] Session expired — re-logging in...")
            cl = login()
        except Exception as e:
            err_type = classify_error(e)
            if err_type == "ratelimit":
                print(f"[!] Rate limited — waiting 90s")
                time.sleep(90)
            elif err_type == "network":
                print(f"[!] Network error — waiting 15s")
                time.sleep(15)
            else:
                print(f"[!] Error ({err_type}): {e}")
        time.sleep(random_poll_interval())

if __name__ == "__main__":
    if os.getenv("GITHUB_ACTIONS"):
        run()
    else:
        run_loop()
