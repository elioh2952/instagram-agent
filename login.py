"""Run this ONCE to log in using your browser session cookie."""
from instagrapi import Client

SESSION_ID = input("Paste your Instagram sessionid cookie value: ").strip()

cl = Client()
cl.login_by_sessionid(SESSION_ID)
cl.dump_settings("session.json")

print(f"\nLogged in as @{cl.username}")
print("Session saved! Now run: python bot.py")
