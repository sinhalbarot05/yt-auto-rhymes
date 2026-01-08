import os
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
# FESTIVAL CHECK (STATIC + SAFE)
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
# SAFE PIXABAY IMAGE FETCH (NO CRASH)
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
            path = f"img_{i}.jpg"
            with open(path, "wb") as f:
                f.write(requests.get(h["largeImageURL"], timeout=20).content)
            images.append(path)

    except Exception:
        fallback = "fallback.jpg"
        if not os.path.exists(fallback):
            ImageClip((1280, 720), color=(255, 200, 200)).save_frame(fallback)
        images = [fallback] * count

    return images

# ======================================================
# STORY & RHYME (NO REPETITION LOGIC)
# ======================================================
def rhyme():
    f = upcoming_festival()
    if f:
        return (
            f"{f} आई खुशियाँ लाई,\n"
            "प्यार बाँटो सब भाई-भाई।\n"
            "सीख यही है बच्चों प्यारी,\n"
            "मिलकर रहना सबसे भारी।"
        )

    return (
        "नन्ही चिड़िया उड़ना सीखे,\n"
        "मेहनत से सपने लिखे।\n"
        "हर दिन कुछ अच्छा करें,\n"
        "सच और प्यार से जियें।"
    )

def story():
    f = upcoming_festival()
    if f:
        return (
            f"{f} के दिन बच्चों ने जाना,\n"
            "प्यार ही सबसे बड़ा खजाना।\n"
            "मिल-जुलकर खुशियाँ बांटी,\n"
            "यही कहानी हमें सिखाती।"
        )

    return (
        "एक गाँव में एक बच्चा रहता था।\n"
        "वह सच्चाई से कभी नहीं डरता था।\n"
        "मेहनत से उसने नाम कमाया,\n"
        "कहानी ने यही सिखाया।"
    )

# ======================================================
# TEXT TO SPEECH
# ======================================================
def tts(text, path):
    gTTS(text=text, lang="hi", slow=False).save(path)

# ======================================================
# VIDEO CREATION (MULTI IMAGE)
# ======================================================
def make_video(images, audio_path, size, out):
    audio = AudioFileClip(audio_path)
    per_img = audio.duration / len(images)

    clips = []
    for img in images:
        clips.append(
            ImageClip(img)
            .with_duration(per_img)
            .resized(height=size[1])
        )

    concatenate_videoclips(clips, method="compose") \
        .with_audio(audio) \
        .write_videofile(out, fps=24)

# ======================================================
# THUMBNAIL (MOVIEPY 2.x SAFE)
# ======================================================
def make_thumbnail(text, img):
    bg = ImageClip(img).resized((1280, 720))

    title = TextClip(
        text,
        fontsize=70,
        color="yellow",
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
                "categoryId": "24",
                "defaultLanguage": "hi",
                "defaultAudioLanguage": "hi"
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
# RUN PIPELINE
# ======================================================

# ---------- SHORT (REEL) ----------
short_text = rhyme()
tts(short_text, "short.mp3")

short_imgs = fetch_images("kids rhyme illustration")
make_video(short_imgs, "short.mp3", (1080, 1920), "short.mp4")

upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes #Shorts",
    short_text,
    ["hindi rhymes", "kids shorts", "nursery rhyme"]
)

# ---------- LONG (STORY) ----------
long_text = story()
tts(long_text, "long.mp3")

long_imgs = fetch_images("kids story illustration")
make_video(long_imgs, "long.mp3", (1920, 1080), "long.mp4")

make_thumbnail(
    "नई हिंदी बच्चों की कहानी\nNew Hindi Kids Story",
    long_imgs[0]
)

upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    long_text,
    ["hindi kids story", "moral story", "bedtime story"],
    "thumbnail.jpg"
)
