import os
import json
import random
import time
import requests
from pathlib import Path

from gtts import gTTS
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
    CompositeVideoClip,
    TextClip
)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ======================================================
# CONFIG
# ======================================================

PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

SHORT_MEM = "short_mem.json"
LONG_MEM = "long_mem.json"

Path("assets").mkdir(exist_ok=True)

# ======================================================
# MEMORY (NO REPEAT GUARANTEE)
# ======================================================

def load_mem(path):
    if os.path.exists(path):
        return set(json.load(open(path)))
    return set()

def save_mem(path, data):
    json.dump(list(data), open(path, "w"), ensure_ascii=False, indent=2)

short_used = load_mem(SHORT_MEM)
long_used = load_mem(LONG_MEM)

# ======================================================
# STORY GENERATORS (OFFLINE, SAFE)
# ======================================================

SHORT_RHYMES = [
    "चिड़िया बोली चूँ चूँ चूँ, उठो बच्चों सूरज निकला यूँ",
    "लाल गेंद उछली कूदे, हँसते बच्चे मन को छुए",
    "पानी बचाओ जीवन बचाओ, धरती माँ को खुश बनाओ",
    "सच बोलो रोज़ करो, अच्छे काम से नाम करो",
    "मम्मी पापा की सुनो बात, खुश रहता है पूरा घर साथ"
]

LONG_STORIES = [
    "एक गाँव में छोटा सा हाथी रहता था जो सबकी मदद करता था। "
    "एक दिन जंगल में आग लगी और हाथी ने नदी से पानी लाकर सबको बचाया। "
    "सबने सीखा कि मदद करने से दोस्ती बढ़ती है।",

    "रिया नाम की बच्ची रोज़ पेड़ को पानी देती थी। "
    "एक दिन उसी पेड़ ने उसे छाया दी और फल दिए। "
    "कहानी सिखाती है कि प्रकृति की सेवा जरूरी है।",

    "मोहन को झूठ बोलने की आदत थी। "
    "एक दिन सच बोलने से उसकी मुश्किल हल हुई। "
    "उसे समझ आया कि सच सबसे बड़ा सहारा है।"
]

def unique_pick(pool, used):
    choices = [x for x in pool if x not in used]
    if not choices:
        used.clear()
        choices = pool[:]
    item = random.choice(choices)
    used.add(item)
    return item

short_text = unique_pick(SHORT_RHYMES, short_used)
long_text = unique_pick(LONG_STORIES, long_used)

save_mem(SHORT_MEM, short_used)
save_mem(LONG_MEM, long_used)

# ======================================================
# IMAGE FETCH (DIFFERENT IMAGES)
# ======================================================

def fetch_image(query, out):
    r = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "image_type": "illustration",
            "safesearch": "true"
        },
        timeout=20
    ).json()
    url = random.choice(r["hits"])["largeImageURL"]
    img = requests.get(url).content
    open(out, "wb").write(img)

# ======================================================
# VIDEO CREATION
# ======================================================

def make_video(text, img_query, out, vertical=False):
    audio_path = f"{out}.mp3"
    gTTS(text=text, lang="hi", slow=False).save(audio_path)

    audio = AudioFileClip(audio_path)

    img_path = f"{out}.jpg"
    fetch_image(img_query, img_path)

    clip = ImageClip(img_path).set_duration(audio.duration).set_audio(audio)

    if vertical:
        clip = clip.resize(height=1920).crop(x_center=clip.w/2, width=1080)
    else:
        clip = clip.resize(height=720)

    clip.write_videofile(out, fps=24, codec="libx264", audio_codec="aac")

# ======================================================
# THUMBNAIL (LONG VIDEO)
# ======================================================

def make_thumbnail(title):
    fetch_image("kids story illustration", "thumb_bg.jpg")

    bg = ImageClip("thumb_bg.jpg").resize((1280, 720))
    txt = TextClip(
        title,
        fontsize=70,
        color="yellow",
        font="DejaVu-Sans-Bold",
        method="caption",
        size=(1100, None)
    ).set_position("center").set_duration(1)

    CompositeVideoClip([bg, txt]).save_frame("thumbnail.jpg")

# ======================================================
# YOUTUBE AUTH
# ======================================================

def youtube_client():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret.json", SCOPES
        )
        creds = flow.run_console()
        json.dump(json.loads(creds.to_json()), open("token.json", "w"))
    return build("youtube", "v3", credentials=creds)

yt = youtube_client()

# ======================================================
# UPLOAD
# ======================================================

def upload(path, title, desc, tags, thumb=None, short=False):
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    res = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(path, resumable=True)
    ).execute()

    if thumb:
        yt.thumbnails().set(
            videoId=res["id"],
            media_body=MediaFileUpload(thumb)
        ).execute()

# ======================================================
# RUN
# ======================================================

make_video(short_text, "kids rhyme illustration", "short.mp4", vertical=True)
make_video(long_text, "kids story illustration", "long.mp4", vertical=False)

make_thumbnail("नई हिंदी बच्चों की कहानी\nNew Hindi Kids Story")

upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes",
    short_text + "\n#kids #hindi #shorts",
    ["hindi rhymes", "kids shorts"],
    short=True
)

upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    long_text + "\n#kids #story #hindi",
    ["hindi kids story", "moral story"],
    thumb="thumbnail.jpg"
)

print("✅ DONE: 1 unique short + 1 unique long uploaded")
