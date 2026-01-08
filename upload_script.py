import os
import random
import time
import json
import requests

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip

import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------- ENV ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

# ---------------- LANG CONFIG ----------------
LANGUAGES = {
    "hi": {
        "name": "Hindi",
        "voice": "hi",
        "suffix": "हिंदी",
        "tags": ["hindi kids", "kids stories"]
    },
    "en": {
        "name": "English",
        "voice": "en",
        "suffix": "English",
        "tags": ["english kids", "kids stories"]
    }
}

THEMES = ["Friendship", "Nature", "Learning", "Adventure", "Family"]

# ---------------- GEMINI (FIXED) ----------------
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(
    model_name="gemini-pro",
    generation_config={
        "temperature": 0.7,
        "max_output_tokens": 800
    }
)

def generate_story(prompt):
    for attempt in range(5):
        try:
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            wait = 2 ** attempt
            print(f"Gemini retry {attempt+1}, wait {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini generation failed")

# ---------------- AUTH (AUTO REFRESH) ----------------
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

creds = Credentials.from_authorized_user_file("token.json", SCOPES)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open("token.json", "w") as f:
        f.write(creds.to_json())

youtube = build("youtube", "v3", credentials=creds)

# ---------------- PICK LANG ----------------
lang_code = random.choice(list(LANGUAGES))
lang = LANGUAGES[lang_code]
theme = random.choice(THEMES)

# ---------------- STORY ----------------
prompt = f"Write a 250 word kids story about {theme} in {lang['name']}."
story = generate_story(prompt)

# ---------------- IMAGE ----------------
pix = requests.get(
    "https://pixabay.com/api/",
    params={
        "key": PIXABAY_KEY,
        "q": "kids cartoon",
        "image_type": "illustration",
        "per_page": 3
    },
    timeout=20
).json()

img_url = pix["hits"][0]["largeImageURL"]
open("bg.jpg", "wb").write(requests.get(img_url, timeout=20).content)

# ---------------- AUDIO ----------------
gTTS(text=story, lang=lang["voice"]).save("audio.mp3")

audio = AudioFileClip("audio.mp3")

# ---------------- VIDEO (FAST) ----------------
ImageClip("bg.jpg") \
    .set_duration(audio.duration) \
    .set_audio(audio) \
    .write_videofile(
        "video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        verbose=False,
        logger=None
    )

# ---------------- UPLOAD (HARDENED) ----------------
def upload_video():
    body = {
        "snippet": {
            "title": f"{theme} Story | {lang['suffix']}",
            "description": story[:4500],
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
                media_body=MediaFileUpload("video.mp4", resumable=True)
            ).execute()
            print("Upload successful")
            return
        except HttpError as e:
            wait = 2 ** attempt
            print(f"Upload retry {attempt+1}, wait {wait}s")
            time.sleep(wait)

    raise RuntimeError("Upload failed")

upload_video()
