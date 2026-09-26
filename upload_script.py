import os
import glob
import json
import base64
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_authenticated_service():
    """Decodes GitHub Secret token and refreshes credentials automatically."""
    token_b64 = os.getenv("YOUTUBE_TOKEN_JSON_B64")
    if not token_b64:
        raise ValueError("❌ Missing YOUTUBE_TOKEN_JSON_B64 secret in environment.")

    token_json = json.loads(base64.b64decode(token_b64).decode("utf-8"))
    
    credentials = Credentials(
        token=token_json.get("token"),
        refresh_token=token_json.get("refresh_token"),
        token_uri=token_json.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_json.get("client_id"),
        client_secret=token_json.get("client_secret"),
        scopes=token_json.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"])
    )

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
    
    # Select the newest file
    latest_video = max(video_files, key=os.path.getctime)
    print(f"[DISCOVERY] Found target video to upload: {latest_video}")
    return latest_video

def upload_short():
    print("=== STARTING YOUTUBE SHORTS UPLOAD PIPELINE ===")
    youtube = get_authenticated_service()
    video_path = find_target_video()

    # Dynamic viral metadata tailored for romance manhwa shorts
    body = {
        "snippet": {
            "title": "When you love someone you can't have... 💔 #Shorts #manhwa #lovestory",
            "description": (
                "When feelings cross the line... 💔\n\n"
                "#Shorts #manhwa #webtoon #romance #animestory #viralshort"
            ),
            "tags": ["Shorts", "manhwa", "webtoon", "romance", "anime", "love story", "angst"],
            "categoryId": "1"  # 1 = Film & Animation, 24 = Entertainment
        },
        "status": {
            "privacyStatus": "public",  # Use "unlisted" or "private" if you want to inspect first
            "selfDeclaredMadeForKids": False,  # CRITICAL: Must be False for non-nursery content
            "embeddable": True
        }
    }

    media = MediaFileUpload(
        video_path,
        chunksize=1024*1024*4,  # 4MB chunks
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
