import os, json, random, hashlib, requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

PIXABAY_KEY = os.getenv("PIXABAY_KEY")

# ---------------- MEMORY ----------------
def load_memory(path):
    if not os.path.exists(path):
        return set()
    return set(json.load(open(path)))

def save_memory(path, data):
    json.dump(list(data), open(path, "w"))

# ---------------- TEXT ENGINE ----------------
def unique_text(mode):
    memory_file = f"{mode}_memory.json"
    memory = load_memory(memory_file)

    while True:
        if mode == "short":
            text = random.choice([
                "Twinkle twinkle little star, learn and shine wherever you are",
                "Happy rhyme for kids, clap and smile all the time",
                "Fun rhyme with joy and play, learning grows every day"
            ])
        else:
            text = random.choice([
                "Once upon a time a clever rabbit taught a big lesson",
                "A small bird learned courage and kindness",
                "A magical forest showed the power of honesty"
            ])

        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in memory:
            memory.add(h)
            save_memory(memory_file, memory)
            return text

# ---------------- TITLE + TAGS ----------------
def generate_metadata(text, mode):
    if mode == "short":
        title = f"Kids Rhyme | {text.split()[0]} Fun Song"
        tags = ["kids rhyme", "nursery rhyme", "learning shorts", "kids song"]
    else:
        title = f"Kids Story | {text.split()[0]} Moral Story"
        tags = ["kids story", "bedtime story", "moral story", "learning kids"]

    desc = f"{title}\n\nSafe educational content for children."
    return title, desc, tags

# ---------------- IMAGE FETCH ----------------
def pixabay_images(query, count):
    url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&image_type=photo&per_page={count}"
    r = requests.get(url).json()
    return [h["largeImageURL"] for h in r.get("hits", [])]

# ---------------- THUMBNAIL ----------------
def make_thumbnail(text, out):
    img = Image.new("RGB", (1280, 720), (255, 220, 180))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.text((50, 300), text[:40], fill=(0,0,0), font=font)
    img.save(out)

# ---------------- VIDEO ----------------
def make_video(mode):
    text = unique_text(mode)
    title, desc, tags = generate_metadata(text, mode)

    images = pixabay_images("kids cartoon", 6 if mode=="short" else 10)
    clips = []

    for i, url in enumerate(images):
        img_path = f"img_{mode}_{i}.jpg"
        open(img_path, "wb").write(requests.get(url).content)
        clips.append(ImageClip(img_path).set_duration(2))

    tts = gTTS(text)
    audio_file = f"{mode}.mp3"
    tts.save(audio_file)

    audio = AudioFileClip(audio_file)
    video = concatenate_videoclips(clips).set_audio(audio)
    out = f"{mode}.mp4"
    video.write_videofile(out, fps=24)

    thumb = f"{mode}_thumb.jpg"
    make_thumbnail(title, thumb)

    print("\n==============================")
    print("VIDEO:", out)
    print("THUMB :", thumb)
    print("TITLE:", title)
    print("DESC :", desc)
    print("TAGS :", ", ".join(tags))
    print("==============================\n")

# ---------------- RUN ----------------
if __name__ == "__main__":
    make_video("short")
    make_video("long")
