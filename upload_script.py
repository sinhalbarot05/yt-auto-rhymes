import os, json, random, hashlib, requests, pickle
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

PIXABAY_KEY = os.getenv("PIXABAY_KEY")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# ---------------- MEMORY ----------------
def unique_text(mode):
    mem = f"{mode}_mem.json"
    data = set(json.load(open(mem))) if os.path.exists(mem) else set()

    while True:
        text = random.choice(
            ["Happy rhyme for kids learning joy",
             "Twinkle rhyme fun play learn"] if mode=="short"
            else ["A brave rabbit learned honesty",
                  "A small bird learned kindness"]
        )
        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in data:
            data.add(h)
            json.dump(list(data), open(mem,"w"))
            return text

# ---------------- METADATA ----------------
def meta(text, mode):
    if mode=="short":
        return (
            f"Kids Rhyme 🎵 {text.split()[0]}",
            "Educational rhyme for kids.",
            ["kids rhyme","nursery rhyme","shorts"]
        )
    return (
        f"Kids Story 📖 {text.split()[0]}",
        "Safe moral bedtime story.",
        ["kids story","bedtime story","learning"]
    )

# ---------------- THUMBNAIL ----------------
def thumbnail(title, out):
    img = Image.new("RGB",(1280,720),(255,210,160))
    d = ImageDraw.Draw(img)
    f = ImageFont.load_default()
    d.text((100,300),title[:40],font=f,fill=(0,0,0))
    img.save(out)

# ---------------- VIDEO ----------------
def make_video(mode):
    text = unique_text(mode)
    title, desc, tags = meta(text,mode)

    images=[]
    r=requests.get(f"https://pixabay.com/api/?key={PIXABAY_KEY}&q=cartoon kids&per_page=6").json()
    for i,h in enumerate(r.get("hits",[])):
        p=f"{mode}_{i}.jpg"
        open(p,"wb").write(requests.get(h["largeImageURL"]).content)
        images.append(ImageClip(p).set_duration(2))

    tts=gTTS(text)
    mp3=f"{mode}.mp3"
    tts.save(mp3)

    video=concatenate_videoclips(images).set_audio(AudioFileClip(mp3))
    out=f"{mode}.mp4"
    video.write_videofile(out,fps=24)

    thumb=f"{mode}_thumb.jpg"
    thumbnail(title,thumb)

    return out, title, desc, tags, thumb

# ---------------- YOUTUBE AUTH ----------------
def youtube_auth():
    if os.path.exists("token.pickle"):
        return pickle.load(open("token.pickle","rb"))
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json", SCOPES
    )
    creds = flow.run_console()
    pickle.dump(creds,open("token.pickle","wb"))
    return creds

# ---------------- UPLOAD ----------------
def upload(video, title, desc, tags, thumb):
    yt = build("youtube","v3",credentials=youtube_auth())
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet":{
                "title":title,
                "description":desc,
                "tags":tags,
                "categoryId":"1"
            },
            "status":{
                "privacyStatus":"public",
                "selfDeclaredMadeForKids":True
            }
        },
        media_body=MediaFileUpload(video)
    )
    res=req.execute()

    yt.thumbnails().set(
        videoId=res["id"],
        media_body=MediaFileUpload(thumb)
    ).execute()

    print("UPLOADED:",res["id"])

# ---------------- RUN ----------------
if __name__=="__main__":
    for mode in ["short","long"]:
        v,t,d,tg,th = make_video(mode)
        upload(v,t,d,tg,th)
