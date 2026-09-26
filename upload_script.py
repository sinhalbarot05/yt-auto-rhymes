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
    """Decodes Base64-encoded Pickle OR JSON YouTube credentials."""
    token_str = os.getenv("YOUTUBE_TOKEN_JSON_B64")
    if not token_str:
        raise ValueError("❌ Missing YOUTUBE_TOKEN_JSON_B64 secret in environment.")

    try:
        raw_bytes = base64.b64decode(token_str)
    except Exception:
        raw_bytes = token_str.encode("utf-8")

    if raw_bytes.startswith(b"\x80"):
        print("[AUTH] Loaded Base64 Python pickle token.")
        credentials = pickle.loads(raw_bytes)
    else:
        print("[AUTH] Loaded Base64 JSON token.")
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
        print("[AUTH] Refreshing expired token via Google OAuth...")
        credentials.refresh(Request())
        print("✅ OAuth token refreshed.")

    return build("youtube", "v3", credentials=credentials)

def find_target_video():
    """Finds the generated MP4 file inside the videos/ directory."""
    files = glob.glob("videos/*.mp4")
    if not files:
        raise FileNotFoundError("❌ No .mp4 files found in videos/ directory.")
    latest = max(files, key=os.path.getctime)
    print(f"[VIDEO] Found target upload file: {latest}")
    return latest

def load_metadata():
    """Loads Groq AI generated titles and song recommendations."""
    meta_path = "workspace/video_metadata.json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "video_title": "When you love someone you can't have... 💔 #Shorts #manhwa #lovestory",
        "recommended_yt_song": "Moral of the Story - Ashe (Shorts Trending)",
        "yt_music_search_query": "Moral of the Story Ashe"
    }

def upload_short():
    print("=== STARTING YOUTUBE SHORTS UPLOAD PIPELINE ===")
    youtube = get_authenticated_service()
    video_path = find_target_video()
    meta = load_metadata()

    song_name = meta.get("recommended_yt_song", "Trending Romance Audio")
    song_search = meta.get("yt_music_search_query", song_name)
    title = meta.get("video_title", "When you love someone you can't have... 💔 #Shorts #manhwa #lovestory")

    description = (
        f"When feelings cross the line... 💔\n\n"
        f"🎵 Recommended Sound: '{song_name}' (Add via YouTube Shorts editor)\n"
        f"🔍 Audio Search Term: {song_search}\n\n"
        f"#Shorts #manhwa #webtoon #romance #animestory #viralshort #lovestory"
    )

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["Shorts", "manhwa", "webtoon", "romance", "anime", "love story", "age gap"],
            "categoryId": "1"  # Film & Animation
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True
        }
    }

    media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 4, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"[UPLOAD] Uploading soundless short with metadata tags...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   ↳ Progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"🎉 UPLOAD COMPLETE!")
    print(f"🔗 Watch URL: https://youtube.com/shorts/{video_id}")
    print(f"💡 TO ATTACH SOUND: Open the YouTube App -> Tap on your uploaded Short -> Tap 'Add Sound' -> Search '{song_search}' -> Done!")

if __name__ == "__main__":
    upload_short()
