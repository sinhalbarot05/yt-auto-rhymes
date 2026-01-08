import os
import time
import random
import requests
import datetime

from gtts import gTTS
from moviepy import (
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
    CompositeVideoClip,
    TextClip
)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ======================================================
# CONFIG
# ======================================================
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

# ======================================================
# FESTIVAL CHECK
# ======================================================
FESTIVALS = {
    "Holi": (3, 14),
    "Diwali": (11, 1),
    "Raksha Bandhan": (8, 19),
    "Janmashtami": (8, 26),
}

def upcoming_festival():
    today = datetime.date.today()
    for name, (m, d) in FESTIVALS.items():
        f = datetime.date(today.year, m, d)
        if 0 <= (f - today).days <= 2:
            return name
    return None

# ======================================================
# SAFE IMAGE FETCH
# ======================================================
def fetch_images(query, count=6):
    images = []
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_KEY,
                "q": query,
                "image_type": "illustration",
                "safesearch": "true",
                "per_page": count
            },
            timeout=20
        )
        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            raise RuntimeError("No images")

        for i, h in enumerate(hits[:count]):
            p = f"img_{i}.jpg"
            with open(p, "wb") as f:
                f.write(requests.get(h["largeImageURL"], timeout=20).content)
            images.append(p)

    except Exception:
        fallback = "fallback.jpg"
        if not os.path.exists(fallback):
            ImageClip((1280, 720), color=(255, 200, 200)).save_frame(fallback)
        images = [fallback] * count

    return images

# ======================================================
# STORY & RHYME
# ======================================================
def rhyme():
    f = upcoming_festival()
    if f:
        return f"{f} आई खुशियाँ लाई,\nप्यार बाँटो सब भाई-भाई।\nसीख यही है बच्चों प्यारी,\nमिलकर रहना सबसे भारी।"
    return "नन्ही चिड़िया उड़ना सीखे,\nमेहनत से सपने लिखे।\nसीख मिले हर दिन हमें,\nअच्छे बनें जीवन में।"

def story():
    f = upcoming_festival()
    if f:
        return f"{f} के दिन बच्चों ने जाना,\nप्यार ही सबसे बड़ा खजाना।\nमिल-जुलकर खुशियाँ बांटी,\nयही कहानी हमें सिखाती।"
    return "एक गाँव में बच्चा रहता था।\nवह सच्चाई से कभी नहीं डरता था।\nमेहनत से उसने सब पाया,\nकहानी ने यही सिखाया।"

# ======================================================
# TTS
# ======================================================
def tts(text, path):
    gTTS(text=text, lang="hi").save(path)

# ======================================================
# VIDEO
# ======================================================
def make_video(images, audio_path, size, out):
    audio = AudioFileClip(audio_path)
    d = audio.duration / len(images)
    clips = [
        ImageClip(img).with_duration(d).resized(height=size[1])
        for img in images
    ]
    concatenate_videoclips(clips, method="compose") \
        .with_audio(audio) \
        .write_videofile(out, fps=24)

# ======================================================
# THUMBNAIL
# ======================================================
def make_thumbnail(text, img):
    bg = ImageClip(img).resized((1280, 720))
    title = TextClip(
        text,
        fontsize=70,
        color="yellow",
        font="DejaVu-Sans-Bold",
        method="caption",
        size=(1200, None)
    ).with_position(("center", "bottom")).with_duration(1)
    CompositeVideoClip([bg, title]).save_frame("thumbnail.jpg", 0)

# ======================================================
# YOUTUBE AUTH
# ======================================================
creds = Credentials.from_authorized_user_file(
    "token.json",
    ["https://www.googleapis.com/auth/youtube.upload"]
)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())

yt = build("youtube", "v3", credentials=creds)

def upload(path, title, desc, tags, thumb=None):
    res = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": desc,
                "tags": tags,
                "categoryId": "24"
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(path)
    ).execute()

    if thumb:
        yt.thumbnails().set(
            videoId=res["id"],
            media_body=MediaFileUpload(thumb)
        ).execute()

# ======================================================
# RUN
# ======================================================
# SHORT
r = rhyme()
tts(r, "s.mp3")
imgs = fetch_images("kids rhyme illustration")
make_video(imgs, "s.mp3", (1080, 1920), "short.mp4")

upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes #Shorts",
    r,
    ["hindi rhymes", "kids shorts"]
)

# LONG
s = story()
tts(s, "l.mp3")
imgs = fetch_images("kids story illustration")
make_video(imgs, "l.mp3", (1920, 1080), "long.mp4")

make_thumbnail(
    "नई हिंदी बच्चों की कहानी\nNew Hindi Kids Story",
    imgs[0]
)

upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    s,
    ["hindi kids story", "moral story"],
    "thumbnail.jpg"
)
