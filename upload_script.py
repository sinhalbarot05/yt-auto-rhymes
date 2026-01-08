import os
import json
import random
import requests
from pathlib import Path

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ================= CONFIG =================

PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

SHORT_MEM = "short_mem.json"
LONG_MEM = "long_mem.json"

Path("assets").mkdir(exist_ok=True)

# ================= MEMORY =================

def load_mem(path):
    if os.path.exists(path):
        return set(json.load(open(path, encoding="utf-8")))
    return set()

def save_mem(path, data):
    json.dump(list(data), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

short_used = load_mem(SHORT_MEM)
long_used = load_mem(LONG_MEM)

# ================= CONTENT =================

SHORT_RHYMES = [
    "चिड़िया बोली चूँ चूँ चूँ, सुबह आई सूरज यूँ",
    "लाल गेंद उछली कूदे, बच्चे खुशियाँ रोज़ लूटे",
    "पानी बचाओ आज करो, धरती माँ से प्यार करो",
    "सच बोलो रोज़ करो, अच्छे बनो आगे बढ़ो",
    "मम्मी पापा की सुनो बात, खुश रहता है पूरा साथ"
]

LONG_STORIES = [
    "एक गाँव में छोटा हाथी था जो सबकी मदद करता था। "
    "एक दिन जंगल में आग लगी, हाथी ने नदी से पानी लाकर सबको बचाया। "
    "कहानी सिखाती है कि मदद सबसे बड़ा गुण है।",

    "रिया रोज़ पौधों को पानी देती थी। "
    "एक दिन उसी पेड़ ने उसे फल और छाया दी। "
    "यह कहानी प्रकृति से प्यार सिखाती है।",

    "मोहन झूठ बोलता था, लेकिन सच ने उसे मुश्किल से निकाला। "
    "उसे समझ आया कि सच सबसे अच्छा दोस्त है।"
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

# ================= IMAGE =================

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

    img_url = random.choice(r["hits"])["largeImageURL"]
    open(out, "wb").write(requests.get(img_url).content)

# ================= VIDEO =================

def make_video(text, img_query, out, vertical=False):
    audio_file = out.replace(".mp4", ".mp3")
    gTTS(text=text, lang="hi").save(audio_file)

    audio = AudioFileClip(audio_file)
    img_file = out.replace(".mp4", ".jpg")

    fetch_image(img_query, img_file)

    clip = ImageClip(img_file).set_duration(audio.duration).set_audio(audio)

    if vertical:
        clip = clip.resize(height=1920).crop(x_center=clip.w / 2, width=1080)
    else:
        clip = clip.resize(height=720)

    clip.write_videofile(out, fps=24, codec="libx264", audio_codec="aac")

# ================= THUMBNAIL =================

def make_thumbnail(title):
    fetch_image("kids story illustration", "thumb.jpg")

    bg = ImageClip("thumb.jpg").resize((1280, 720))
    txt = TextClip(
        title,
        fontsize=70,
        color="yellow",
        font="DejaVu-Sans-Bold",
        method="caption",
        size=(1100, None)
    ).set_position("center").set_duration(1)

    CompositeVideoClip([bg, txt]).save_frame("thumbnail.jpg")

# ================= YOUTUBE =================

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

def upload(path, title, desc, tags, thumb=None):
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

# ================= RUN =================

make_video(short_text, "kids rhyme illustration", "short.mp4", vertical=True)
make_video(long_text, "kids story illustration", "long.mp4", vertical=False)

make_thumbnail("नई हिंदी बच्चों की कहानी\nNew Hindi Kids Story")

upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes",
    short_text + "\n#kids #hindi #shorts",
    ["hindi rhymes", "kids shorts"]
)

upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    long_text + "\n#kids #story #hindi",
    ["hindi kids story", "moral story"],
    thumb="thumbnail.jpg"
)

print("✅ SUCCESS: 1 unique short + 1 unique long uploaded")
