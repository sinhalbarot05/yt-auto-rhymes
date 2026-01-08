import os
import time
import random
import requests

from gtts import gTTS
from moviepy import ImageClip, AudioFileClip

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ======================================================
# CONFIG
# ======================================================
LANG = "hi"
THEMES = ["दोस्ती", "ईमानदारी", "प्रकृति", "परिवार", "सीख"]

PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

# ======================================================
# STORY (LOCAL, STABLE)
# ======================================================
def long_story(theme):
    return (
        f"एक समय की बात है, {theme} से जुड़ी एक सुंदर कहानी थी। "
        "इस कहानी से बच्चों को यह सीख मिलती है कि सच्चाई और मेहनत "
        "हमेशा सफलता दिलाती है।"
    )

def short_story(theme):
    return f"{theme} से सीखो, अच्छे बनो और हमेशा सच बोलो।"

theme = random.choice(THEMES)
story_long = long_story(theme)
story_short = short_story(theme)

# ======================================================
# IMAGE
# ======================================================
resp = requests.get(
    "https://pixabay.com/api/",
    params={
        "key": PIXABAY_KEY,
        "q": "kids cartoon",
        "image_type": "illustration"
    },
    timeout=20
).json()

img_url = resp["hits"][0]["largeImageURL"]
with open("bg.jpg", "wb") as f:
    f.write(requests.get(img_url).content)

# ======================================================
# VIDEO CREATION (MOVIEPY 2.x)
# ======================================================
def make_video(text, out):
    gTTS(text=text, lang="hi").save("audio.mp3")
    audio = AudioFileClip("audio.mp3")

    clip = (
        ImageClip("bg.jpg")
        .with_duration(audio.duration)
        .with_audio(audio)
        .resized(height=1080)
    )

    clip.write_videofile(
        out,
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

make_video(story_long, "long.mp4")
make_video(story_short, "short.mp4")

# ======================================================
# YOUTUBE AUTH (AUTO REFRESH)
# ======================================================
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_file("token.json", SCOPES)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open("token.json", "w") as f:
        f.write(creds.to_json())

youtube = build("youtube", "v3", credentials=creds)

# ======================================================
# UPLOAD (RETRY SAFE)
# ======================================================
def upload(path, title, is_short=False):
    body = {
        "snippet": {
            "title": title + (" #Shorts" if is_short else ""),
            "description": title,
            "tags": ["हिंदी कहानी", "kids hindi"],
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi",
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    for i in range(5):
        try:
            youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(path, resumable=True)
            ).execute()
            print(f"Uploaded {path}")
            return
        except HttpError:
            time.sleep(2 ** i)

    raise RuntimeError("Upload failed")

upload("long.mp4", "नई हिंदी बच्चों की कहानी")
upload("short.mp4", "मजेदार हिंदी राइम", True)
