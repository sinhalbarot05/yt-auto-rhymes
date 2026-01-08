import os, json, random, hashlib, base64, datetime
import requests
from gtts import gTTS

# ✅ CORRECT MoviePy imports (NO editor)
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

# =====================================================
# CONFIG
# =====================================================
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
MEMORY_DIR = "memory"

os.makedirs(MEMORY_DIR, exist_ok=True)

FILES = {
    "stories": f"{MEMORY_DIR}/stories.json",
    "rhymes": f"{MEMORY_DIR}/rhymes.json",
    "images": f"{MEMORY_DIR}/images.json"
}

def load(path):
    if not os.path.exists(path):
        with open(path,"w") as f: json.dump([],f)
    return json.load(open(path))

def save(path,data):
    json.dump(data,open(path,"w"),ensure_ascii=False,indent=2)

stories = load(FILES["stories"])
rhymes = load(FILES["rhymes"])
images_used = load(FILES["images"])

# =====================================================
# FESTIVAL LOGIC
# =====================================================
def festival():
    today = datetime.date.today()
    if today.month == 3:
        return "Holi"
    if today.month == 8:
        return "Raksha Bandhan"
    if today.month == 10 or today.month == 11:
        return "Diwali"
    return "None"

# =====================================================
# GEMINI via Vertex REST (NO billing issues)
# =====================================================
def gemini(prompt):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_file(
        "gcp-sa.json",
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())

    url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/us-central1/publishers/google/models/gemini-pro:generateContent"

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json"
    }

    data = {
        "contents":[{"parts":[{"text":prompt}]}],
        "generationConfig":{
            "temperature":0.8,
            "maxOutputTokens":600
        }
    }

    r = requests.post(url, headers=headers, json=data, timeout=60).json()
    return r["candidates"][0]["content"]["parts"][0]["text"]

# =====================================================
# UNIQUE TEXT
# =====================================================
def unique_text(kind):
    mem = stories if kind=="story" else rhymes
    while True:
        text = gemini(
            f"Write a NEW Hindi kids {kind}. Festival:{festival()}. "
            f"Never repeat anything similar."
        )
        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in mem:
            mem.append(h)
            save(FILES["stories" if kind=="story" else "rhymes"], mem)
            return text

# =====================================================
# PIXABAY UNIQUE IMAGES
# =====================================================
def images(query, n=5):
    res = requests.get("https://pixabay.com/api/", params={
        "key":PIXABAY_KEY,"q":query,"image_type":"illustration","per_page":20
    }).json()

    out=[]
    for h in res["hits"]:
        if str(h["id"]) in images_used: continue
        img = f"img_{h['id']}.jpg"
        open(img,"wb").write(requests.get(h["largeImageURL"]).content)
        images_used.append(str(h["id"]))
        out.append(img)
        if len(out)==n: break

    save(FILES["images"], images_used)
    return out

# =====================================================
# AUDIO
# =====================================================
def tts(text,file):
    gTTS(text=text,lang="hi").save(file)

# =====================================================
# VIDEO
# =====================================================
def video(imgs,audio,out,h):
    aud=AudioFileClip(audio)
    d=aud.duration/len(imgs)
    clips=[ImageClip(i).with_duration(d).resized(height=h) for i in imgs]
    concatenate_videoclips(clips).with_audio(aud).write_videofile(out,fps=24)

# =====================================================
# RUN
# =====================================================
short = unique_text("rhyme")
tts(short,"s.mp3")
video(images("kids rhyme"),"s.mp3","short.mp4",1920)

story = unique_text("story")
tts(story,"l.mp3")
video(images("kids story"),"l.mp3","long.mp4",1080)

print("✅ DONE — unique story, unique images, future-proof")
