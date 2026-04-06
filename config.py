import os
from dotenv import load_dotenv

load_dotenv()

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
