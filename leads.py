"""
Lead tools — run these manually when you want to reach out.

Usage:
  python leads.py list                          — show all leads
  python leads.py search <hashtag>              — find accounts by hashtag
  python leads.py draft "they run a food brand" — generate an outreach message
  python leads.py send <username> "<message>"   — send a DM to someone
"""

import sys
from instagrapi import Client
from config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
from database import init_db, add_lead, get_leads
from ai import draft_outreach

SESSION_FILE = "session.json"

def get_client() -> Client:
    cl = Client()
    try:
        cl.load_settings(SESSION_FILE)
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    except Exception:
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        cl.dump_settings(SESSION_FILE)
    return cl

def cmd_list():
    leads = get_leads()
    if not leads:
        print("No leads yet.")
        return
    print(f"{'Username':<25} {'Status':<12} Notes")
    print("-" * 60)
    for l in leads:
        print(f"@{l['username']:<24} {l['status']:<12} {l['notes']}")

def cmd_search(hashtag: str):
    print(f"[*] Searching #{hashtag}...")
    cl = get_client()
    medias = cl.hashtag_medias_top(hashtag, amount=10)
    print(f"\nTop accounts posting #{hashtag}:\n")
    for m in medias:
        user = cl.user_info(m.user.pk)
        print(f"  @{user.username:<25} {user.full_name:<20} {user.follower_count:,} followers")
        print(f"    Bio: {user.biography[:80] if user.biography else 'N/A'}")
        print()

def cmd_draft(context: str):
    msg = draft_outreach(context)
    print(f"\nSuggested message:\n\n  {msg}\n")

def cmd_send(username: str, message: str):
    cl = get_client()
    user_id = cl.user_id_from_username(username)
    cl.direct_send(message, user_ids=[user_id])
    add_lead(str(user_id), username, "manual outreach")
    print(f"[✓] Message sent to @{username}")

if __name__ == "__main__":
    init_db()
    args = sys.argv[1:]

    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "search" and len(args) > 1:
        cmd_search(args[1])
    elif args[0] == "draft" and len(args) > 1:
        cmd_draft(" ".join(args[1:]))
    elif args[0] == "send" and len(args) > 2:
        cmd_send(args[1], " ".join(args[2:]))
    else:
        print(__doc__)
