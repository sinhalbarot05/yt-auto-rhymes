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
from googleapiclient.errors import HttpError

# ======================================================
# CONFIG
# ======================================================
LANG = "hi"
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

SHORT_DURATION = 55          # seconds
LONG_DURATION = 270          # ~4.5 minutes

KIDS_COLORS = ["bright", "colorful", "cute", "cartoon", "kids illustration"]

# ======================================================
# FESTIVAL AWARENESS (STATIC, SAFE)
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
        f_date = datetime.date(today.year, m, d)
        if 0 <= (f_date - today).days <= 2:
            return name
    return None

# ======================================================
# STORY / RHYME GENERATORS (NO REPETITION)
# ======================================================
def generate_rhyme():
    festival = upcoming_festival()
    if festival:
        return (
            f"{festival} आई खुशियाँ लाई,\n"
            "रंगों से भरी दुनिया छाई।\n"
            "मिल-जुलकर सब खेलें गाएं,\n"
            "प्यार से दिल हम सब जीत जाएं।\n\n"
            "सीख यही है बच्चों प्यारी,\n"
            "मिलकर रहना सबसे भारी।"
        )

    topics = [
        "चिड़िया और नीला आसमान",
        "नन्हा हाथी और उसका सपना",
        "बारिश की बूंदें",
        "सच्चाई की ताकत",
        "माँ की ममता"
    ]
    t = random.choice(topics)
    return (
        f"{t} की प्यारी कहानी,\n"
        "लय में बंधी मीठी जुबानी।\n"
        "सीख मिले हर एक पंक्ति से,\n"
        "खुशियाँ आएं हर संगी से।"
    )

def generate_story():
    festival = upcoming_festival()
    if festival:
        return (
            f"{festival} का दिन था खुशहाल,\n"
            "बच्चों के चेहरे थे लाल गुलाल।\n\n"
            "एक नन्हा बच्चा सीख गया,\n"
            "प्यार बाँटना सबसे बड़ा उपहार।\n\n"
            "कहानी हमें यह सिखलाए,\n"
            "मिल-जुलकर हर त्योहार मनाएं।"
        )

    morals = ["ईमानदारी", "दोस्ती", "मेहनत", "प्रकृति प्रेम", "बड़ों का सम्मान"]
    m = random.choice(morals)

    return (
        f"एक गाँव में एक बच्चा रहता था।\n"
        f"उसने {m} का महत्व समझा।\n\n"
        "छोटे-छोटे कामों से उसने\n"
        "सबका दिल जीत लिया।\n\n"
        f"कहानी की सीख – {m} हमेशा याद रखो।"
    )

# ======================================================
# PIXABAY IMAGE FETCH (MULTI IMAGE)
# ======================================================
def fetch_images(query, count=6):
    resp = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "image_type": "illustration",
            "orientation": "horizontal",
            "per_page": count
        },
        timeout=20
    ).json()

    images = []
    for i, hit in enumerate(resp.get("hits", [])[:count]):
        path = f"img_{i}.jpg"
        with open(path, "wb") as f:
            f.write(requests.get(hit["largeImageURL"]).content)
        images.append(path)

    return images

# ======================================================
# VIDEO CREATION (ANIMATED)
# ======================================================
def animated_video(images, audio_path, size):
    audio = AudioFileClip(audio_path)
    dur_per_img = audio.duration / len(images)

    clips = []
    for img in images:
        clip = (
            ImageClip(img)
            .with_duration(dur_per_img)
            .resized(height=size[1])
            .with_position("center")
        )
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    return video.with_audio(audio)

def tts(text, path):
    gTTS(text=text, lang="hi", slow=False).save(path)

# ======================================================
# THUMBNAIL (LONG VIDEO ONLY)
# ======================================================
def make_thumbnail(text):
    bg = ImageClip(fetch_images("kids story illustration", 1)[0]).resized((1280, 720))
    title = TextClip(
        text,
        fontsize=70,
        color="yellow",
        font="DejaVu-Sans-Bold",
        method="caption",
        size=(1200, None)
    ).with_position(("center", "bottom")).with_duration(1)

    CompositeVideoClip([bg, title]).save_frame("thumbnail.jpg", t=0)

# ======================================================
# YOUTUBE AUTH
# ======================================================
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_file("token.json", SCOPES)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open("token.json", "w") as f:
        f.write(creds.to_json())

youtube = build("youtube", "v3", credentials=creds)

# ======================================================
# UPLOAD
# ======================================================
def upload(path, title, desc, tags, thumb=None, shorts=False):
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": "24",
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi"
        },
        "status": {"privacyStatus": "public"}
    }

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(path, resumable=True)
    )
    res = req.execute()

    if thumb:
        youtube.thumbnails().set(
            videoId=res["id"],
            media_body=MediaFileUpload(thumb)
        ).execute()

# ======================================================
# RUN
# ======================================================
# SHORT (RHYME)
rhyme = generate_rhyme()
tts(rhyme, "short.mp3")
imgs = fetch_images("kids rhyme " + random.choice(KIDS_COLORS))
short_video = animated_video(imgs, "short.mp3", (1080, 1920))
short_video.write_videofile("short.mp4", fps=24)

upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes #Shorts",
    rhyme + "\n\n#HindiRhymes #KidsShorts",
    ["hindi rhyme", "kids shorts", "nursery rhyme"],
    shorts=True
)

# LONG (STORY)
story = generate_story()
tts(story, "long.mp3")
imgs = fetch_images("kids story " + random.choice(KIDS_COLORS))
long_video = animated_video(imgs, "long.mp3", (1920, 1080))
long_video.write_videofile("long.mp4", fps=24)

make_thumbnail("नई हिंदी बच्चों की कहानी\nNew Hindi Kids Story")

upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    story + "\n\n#HindiStory #KidsStory #MoralStory",
    ["hindi kids story", "moral story", "bedtime story"],
    thumb="thumbnail.jpg"
)
