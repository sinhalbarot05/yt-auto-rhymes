import os
import random
import json
import requests

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

from google.generativeai import configure, GenerativeModel
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ---------------- ENV ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_KEY")

# ---------------- GEMINI ----------------
configure(api_key=GEMINI_API_KEY)
model = GenerativeModel("gemini-1.5-flash")

# ---------------- YOUTUBE AUTH ----------------
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

creds = Credentials.from_authorized_user_file("token.json", SCOPES)
youtube = build("youtube", "v3", credentials=creds)

# ---------------- THEME ----------------
themes = [
    "जानवरों की दोस्ती",
    "प्रकृति की सुंदरता",
    "सीखने की कहानी",
    "मजेदार साहसिक",
    "परिवार का प्यार",
    "स्कूल के दिन",
    "खेलकूद की मस्ती"
]
theme = random.choice(themes)

# ---------------- CONTENT ----------------
story = model.generate_content(
    f"300-500 शब्दों की एक नई हिंदी बच्चों की कहानी लिखो। थीम: {theme}"
).text

rhyme = model.generate_content(
    f"100 शब्दों की मजेदार हिंदी बच्चों की राइम लिखो। थीम: {theme}"
).text

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

# ---------------- VIDEO ----------------
def make_video(text, out):
    gTTS(text=text, lang="hi").save("audio.mp3")

    audio = AudioFileClip("audio.mp3")
    img = ImageClip("bg.jpg").set_duration(audio.duration)

    txt = TextClip(
        text[:120] + "...",
        fontsize=30,
        color="white",
        font="DejaVu-Sans"
    ).set_position("center").set_duration(audio.duration)

    CompositeVideoClip([img, txt]) \
        .set_audio(audio) \
        .write_videofile(out, fps=24)

make_video(story, "long.mp4")
make_video(rhyme, "short.mp4")

# ---------------- UPLOAD ----------------
def upload(file, title, desc, shorts=False):
    body = {
        "snippet": {
            "title": title + (" #Shorts" if shorts else ""),
            "description": desc,
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(file)
    ).execute()

upload("long.mp4", f"नई हिंदी कहानी | {theme}", story)
upload("short.mp4", f"हिंदी राइम | {theme}", rhyme, True)
