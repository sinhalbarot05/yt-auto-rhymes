import os
import time
import random
import requests

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip

import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ======================================================
# CONFIG
# ======================================================
LANG = "hi"
THEMES = [
    "दोस्ती", "ईमानदारी", "प्रकृति", "परिवार", "सीखने की कहानी"
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_KEY")

# ======================================================
# STORY (GEMINI + FALLBACK)
# ======================================================
def fallback_story(long=True):
    if long:
        return (
            "एक समय की बात है, एक प्यारा सा बच्चा था जो हर दिन कुछ नया सीखना चाहता था। "
            "उसके माता-पिता ने उसे सिखाया कि सच्चाई और मेहनत से जीवन में हमेशा सफलता मिलती है। "
            "उसने अपने दोस्तों के साथ मिलकर समझा कि अच्छाई सबसे बड़ी ताकत होती है।"
        )
    return "सीखो, खेलो और हमेशा सच बोलो। यही है सबसे बड़ी जीत।"

story_long = None
story_short = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-pro")

        theme = random.choice(THEMES)

        story_long = model.generate_content(
            f"300 शब्दों की हिंदी बच्चों की कहानी लिखो विषय: {theme}"
        ).text

        story_short = model.generate_content(
            f"30 शब्दों की हिंदी बच्चों की कविता लिखो विषय: {theme}"
        ).text
    except Exception:
        story_long = None
        story_short = None

if not story_long:
    story_long = fallback_story(True)
if not story_short:
    story_short = fallback_story(False)

# ======================================================
# IMAGE
# ======================================================
img = requests.get(
    "https://pixabay.com/api/",
    params={
        "key": PIXABAY_KEY,
        "q": "kids cartoon",
        "image_type": "illustration"
    },
    timeout=20
).json()["hits"][0]["largeImageURL"]

open("bg.jpg", "wb").write(requests.get(img).content)

# ======================================================
# VIDEO CREATOR
# ======================================================
def make_video(text, out):
    gTTS(text=text, lang="hi").save("audio.mp3")
    audio = AudioFileClip("audio.mp3")

    ImageClip("bg.jpg") \
        .set_duration(audio.duration) \
        .set_audio(audio) \
        .resize(height=1080) \
        .write_videofile(
            out,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None
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
    open("token.json", "w").write(creds.to_json())

yt = build("youtube", "v3", credentials=creds)

# ======================================================
# UPLOAD (RETRY SAFE)
# ======================================================
def upload(path, title, is_short=False):
    body = {
        "snippet": {
            "title": title + (" #Shorts" if is_short else ""),
            "description": title,
            "tags": ["हिंदी कहानी", "kids hindi", "moral story"],
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi",
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    for i in range(5):
        try:
            yt.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(path, resumable=True)
            ).execute()
            return
        except HttpError:
            time.sleep(2 ** i)

    raise RuntimeError("Upload failed")

upload("long.mp4", "नई हिंदी बच्चों की कहानी")
upload("short.mp4", "मजेदार हिंदी राइम", True)
