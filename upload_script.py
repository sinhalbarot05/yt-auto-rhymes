import os
import glob
import json
import base64
import pickle
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def get_youtube_client():
    token_b64 = os.getenv("YOUTUBE_TOKEN_JSON_B64")
    if not token_b64:
        raise ValueError("❌ Missing YOUTUBE_TOKEN_JSON_B64 secret.")

    try:
        raw = base64.b64decode(token_b64)
    except Exception:
        raw = token_b64.encode("utf-8")

    if raw.startswith(b"\x80"):
        creds = pickle.loads(raw)
    else:
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else token_b64)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"])
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("youtube", "v3", credentials=creds)


def upload_short():
    print("=== UPLOADING MANHWA SHORT TO YOUTUBE ===")
    youtube = get_youtube_client()

    mp4s = glob.glob("videos/*.mp4")
    if not mp4s:
        raise FileNotFoundError("❌ No MP4 file found in videos/.")
    video_path = max(mp4s, key=os.path.getctime)

    meta = {}
    if os.path.exists("workspace/video_metadata.json"):
        with open("workspace/video_metadata.json", "r", encoding="utf-8") as f:
            meta = json.load(f)

    title = meta.get("video_title", "Left In The Rain… Until His Brother Stepped In ☔💔 #Shorts #manhwa")
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"
    title = title[:100]

    trope = meta.get("trope", "Original Korean Manhwa Romance")
    scenes = meta.get("scenes", [])
    quote_block = ""
    if scenes:
        m_q = scenes[0].get("male_line", "")
        f_q = scenes[0].get("female_line", "")
        if m_q and f_q:
            quote_block = f"💬 \"{m_q}\"\n💭 \"{f_q}\"\n\n"

    description = (
        f"📖 {trope} 💗🥀\n\n"
        f"{quote_block}"
        f"🎵 Music: Love Story (Ethereal Instrumental Slowed & Reverb) - Indila\n"
        f"✨ Subscribe for daily original Manhwa love stories!\n\n"
        f"#Shorts #manhwa #webtoon #lovestory #anime #romance #manga #viralshort #fyp"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Shorts", "manhwa", "webtoon", "love story", "anime romance", "indila love story"],
            "categoryId": "1"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True
        }
    }

    media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 4, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"   ↳ Uploaded {int(status.progress() * 100)}%")

    print(f"🎉 UPLOADED: https://youtube.com/shorts/{response.get('id')}")


if __name__ == "__main__":
    upload_short()
