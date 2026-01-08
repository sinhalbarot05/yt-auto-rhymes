import os
import random
import time
import json
import requests

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip
from google.generativeai import configure, GenerativeModel
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------- CONFIG ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_KEY")

LANGUAGES = {
    "hi": {
        "name": "Hindi",
        "voice": "hi",
        "title_suffix": "हिंदी",
        "tags": ["hindi kids", "kids stories"]
    },
    "en": {
        "name": "English",
        "voice": "en",
        "title_suffix": "English",
        "tags": ["english kids", "kids stories"]
    }
}

THEMES = [
    "Friendship",
    "Nature",
    "Learning",
    "Adventure",
    "Family",
    "School",
    "Sports"
]

# ---------------- GEMINI ----------------
configure(api_key=GEMINI_API_KEY)
model = GenerativeModel("gemini-1.0-pro")

# ---------------- AUTH (AUTO REFRESH) ----------------
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_file("token.json", SCOPES)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open("token.json", "w") as f:
        f.write(creds.to_json())

youtube = build("youtube", "v3", credentials=creds)

# ---------------- LANGUAGE PICK ----------------
lang_code = random.choice(list(LANGUAGES.keys()))
lang = LANGUAGES[lang_code]
theme = random.choice(THEMES)

# ---------------- CONTENT ----------------
prompt = f"Write a 300 word kids story about {theme} in {lang['name']}."
story = model.generate_content(prompt).text

# ---------------- IMAGE ----------------
pix = requests.get(
    "https://pixabay.com/api/",
    params={
        "key": PIXABAY_KEY,
        "q": "kids cartoon",
        "image_type": "illustration"
    }
).json()

img_url = pix["hits"][0]["largeImageURL"]
open("bg.jpg", "wb").write(requests.get(img_url).content)

# ---------------- VIDEO (FAST) ----------------
gTTS(text=story, lang=lang["voice"]).save("audio.mp3")

audio = AudioFileClip("audio.mp3")
ImageClip("bg.jpg") \
    .set_duration(audio.duration) \
    .set_audio(audio) \
    .write_videofile("video.mp4", fps=24)

# ---------------- UPLOAD WITH RETRY ----------------
def upload_with_retry():
    body = {
        "snippet": {
            "title": f"{theme} Story | {lang['title_suffix']}",
            "description": story,
            "tags": lang["tags"],
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    for attempt in range(5):
        try:
            youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload("video.mp4")
            ).execute()
            print("Upload successful")
            return
        except HttpError as e:
            wait = 2 ** attempt
            print(f"Upload failed, retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError("Upload failed after retries")

upload_with_retry()
