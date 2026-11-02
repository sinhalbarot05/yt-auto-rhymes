import os
import glob
import json
import base64
import pickle
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def get_authenticated_service():
    """Decodes Base64 Pickle or JSON OAuth credentials and refreshes automatically."""
    token_str = os.getenv("YOUTUBE_TOKEN_JSON_B64")
    if not token_str:
        raise ValueError("❌ Missing YOUTUBE_TOKEN_JSON_B64 secret in GitHub Actions.")

    try:
        raw_bytes = base64.b64decode(token_str)
    except Exception:
        raw_bytes = token_str.encode("utf-8")

    if raw_bytes.startswith(b"\x80"):
        credentials = pickle.loads(raw_bytes)
    else:
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            data = json.loads(token_str)

        credentials = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"])
        )

    if credentials.expired and credentials.refresh_token:
        print("[AUTH] Refreshing expired OAuth token...")
        credentials.refresh(Request())

    return build("youtube", "v3", credentials=credentials)


def load_story_metadata():
    meta_file = "workspace/video_metadata.json"
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_unique_description(meta):
    """Builds a unique, story-specific description from the generated scenes so no two uploads look identical."""
    trope_name = meta.get("trope", "Original Korean Manhwa Romance")
    scenes = meta.get("scenes", [])

    teaser_lines = []
    if scenes:
        first_sc = scenes[0]
        if first_sc.get("male_line"):
            teaser_lines.append(f"💬 Him: \"{first_sc['male_line']}\"")
        if first_sc.get("female_line"):
            teaser_lines.append(f"💭 Her: \"{first_sc['female_line']}\"")

    teaser_block = "\n".join(teaser_lines) if teaser_lines else "A complete original romantic webtoon short story."

    return (
        f"📖 Story: {trope_name} 💗🥀\n\n"
        f"{teaser_block}\n\n"
        f"🎵 Music: Love Story (Ethereal Instrumental Slowed & Reverb) - Indila\n"
        f"✨ Subscribe for daily original Manhwa & Webtoon love stories!\n\n"
        f"#Shorts #manhwa #webtoon #lovestory #indila #romance #anime #manga #viralshort #fyp"
    )


def upload_short():
    print("=== STARTING AUTOMATED YOUTUBE SHORTS UPLOAD ===")
    youtube = get_authenticated_service()

    mp4_files = glob.glob("videos/*.mp4")
    if not mp4_files:
        raise FileNotFoundError("❌ No rendered MP4 found in videos/ directory.")
    target_video = max(mp4_files, key=os.path.getctime)

    meta = load_story_metadata()
    raw_title = meta.get("video_title", "When Her Fiancé Stood Her Up, His Brother Saved Her 🌂❤️ #Shorts #manhwa")
    if "#Shorts" not in raw_title and "#shorts" not in raw_title:
        raw_title = f"{raw_title} #Shorts"
    title = raw_title[:100]

    description = build_unique_description(meta)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [
                "Shorts", "manhwa", "webtoon", "love story", "indila love story instrumental",
                "childhood friends to lovers", "enemies to lovers", "anime romance", "viral short"
            ],
            "categoryId": "1"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True
        }
    }

    media = MediaFileUpload(target_video, chunksize=1024 * 1024 * 4, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"[UPLOAD] Uploading '{title}' ({target_video}) to YouTube Shorts...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   ↳ Upload Progress: {int(status.progress() * 100)}%")

    vid_id = response.get("id")
    print(f"🎉 UPLOAD COMPLETE: https://youtube.com/shorts/{vid_id}")


if __name__ == "__main__":
    upload_short()
