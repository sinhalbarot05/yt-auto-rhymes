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
    """Universally decodes Base64-encoded Pickle OR JSON credentials."""
    token_str = os.getenv("YOUTUBE_TOKEN_JSON_B64")
    if not token_str:
        raise ValueError("❌ Missing YOUTUBE_TOKEN_JSON_B64 secret in environment.")

    # 1. Decode base64 bytes
    try:
        raw_bytes = base64.b64decode(token_str)
    except Exception:
        raw_bytes = token_str.encode("utf-8")

    credentials = None

    # 2. Check if the payload is a pickled object (starts with opcode \x80)
    if raw_bytes.startswith(b"\x80"):
        print("[AUTH] Detected base64-encoded Python pickle credentials.")
        credentials = pickle.loads(raw_bytes)
    else:
        # Fallback to JSON parsing
        print("[AUTH] Detected JSON credentials payload.")
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

    # 3. Refresh expired tokens automatically
    if credentials.expired and credentials.refresh_token:
        print("[AUTH] Access token expired. Refreshing token via Google OAuth...")
        credentials.refresh(Request())
        print("✅ OAuth token refreshed successfully.")

    return build("youtube", "v3", credentials=credentials)

def find_target_video():
    """Finds the most recently created video inside the videos/ directory."""
    video_files = glob.glob("videos/*.mp4")
    if not video_files:
        raise FileNotFoundError("❌ No .mp4 files found in videos/ directory to upload.")
    
    latest_video = max(video_files, key=os.path.getctime)
    print(f"[DISCOVERY] Found target video to upload: {latest_video}")
    return latest_video

def upload_short():
    print("=== STARTING YOUTUBE SHORTS UPLOAD PIPELINE ===")
    youtube = get_authenticated_service()
    video_path = find_target_video()

    body = {
        "snippet": {
            "title": "When you love someone you can't have... 💔 #Shorts #manhwa #lovestory",
            "description": (
                "When feelings cross the line... 💔\n\n"
                "#Shorts #manhwa #webtoon #romance #animestory #viralshort"
            ),
            "tags": ["Shorts", "manhwa", "webtoon", "romance", "anime", "love story", "angst"],
            "categoryId": "1"  # 1 = Film & Animation
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True
        }
    }

    media = MediaFileUpload(
        video_path,
        chunksize=1024*1024*4,
        resumable=True,
        mimetype="video/mp4"
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    print(f"[UPLOAD] Uploading {video_path} to YouTube Shorts...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   ↳ Upload progress: {int(status.progress() * 100)}%")

    print(f"🎉 UPLOAD COMPLETE! Video ID: {response.get('id')}")
    print(f"🔗 Watch URL: https://youtube.com/shorts/{response.get('id')}")

if __name__ == "__main__":
    upload_short()
