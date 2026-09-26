import os
import json
import time
import requests
import urllib.parse
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips

# Permanent fallback storyline with 1st-person POV and changing ages
DEFAULT_STORYLINE = [
    {
        "male_age": "25",
        "female_age": "14",
        "speaker_name": "Him",
        "speaker_type": "chat",
        "dialogue": "Stop daydreaming and finish your math equations, kid.",
        "prompt": "Korean manhwa webtoon style, handsome older male college tutor smiling gently at a cute young teenage girl studying at desk, soft pastel anime lighting, 9:16 vertical"
    },
    {
        "male_age": "26",
        "female_age": "15",
        "speaker_name": "Her",
        "speaker_type": "thought",
        "dialogue": "I made homemade chocolates for you... but my hands won't stop shaking.",
        "prompt": "Cute anime girl with pigtails blushing nervously holding a small gift box behind her back, modern hallway, warm manhwa aesthetic, 9:16 vertical"
    },
    {
        "male_age": "27",
        "female_age": "16",
        "speaker_name": "Her",
        "speaker_type": "chat",
        "dialogue": "I don't care about the age gap. I love you.",
        "prompt": "Emotional dramatic anime scene, teenage girl with intense teary eyes confessing under streetlamp, handsome older man looking startled, night, 9:16 vertical"
    },
    {
        "male_age": "27",
        "female_age": "16",
        "speaker_name": "Him",
        "speaker_type": "chat",
        "dialogue": "Never say that again. You're just my student.",
        "prompt": "Handsome anime man with cold serious expression, turning his face away in shadows, emotional distance, dark blue night aesthetic, 9:16 vertical"
    },
    {
        "male_age": "29",
        "female_age": "18",
        "speaker_name": "Him",
        "speaker_type": "chat",
        "dialogue": "Meet Claire. She's my fiancée.",
        "prompt": "Heartbreak scene, handsome man in tailored suit holding hands with glamorous woman, 18 year old girl standing frozen in shock, tears welling up, luxury lobby, 9:16 vertical"
    },
    {
        "male_age": "",
        "female_age": "18",
        "speaker_name": "Her",
        "speaker_type": "thought",
        "dialogue": "You told me to wait until I grew up... but you never intended to wait for me.",
        "prompt": "Heartbroken anime girl crying heavily in the rain, mascara running, shattered expression, cinematic dramatic lighting, rainy city background, 9:16 vertical"
    }
]

def fetch_romantic_music(output_path="workspace/romantic_bg.mp3"):
    """Downloads a royalty-free emotional romantic piano loop for the video soundtrack."""
    if os.path.exists(output_path):
        return output_path
    print("[AUDIO] Fetching romantic piano background track...")
    # Clean CC0 romantic piano theme
    music_url = "https://raw.githubusercontent.com/sinhalbarot05/yt-auto-rhymes/main/assets/romantic_piano.mp3"
    fallback_url = "https://cdn.freesound.org/previews/612/612642_11861866-lq.mp3"
    
    for url in [music_url, fallback_url]:
        try:
            res = requests.get(url, timeout=20)
            if res.status_code == 200 and len(res.content) > 10000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                print(f"✅ Secured romantic soundtrack: {output_path}")
                return output_path
        except Exception:
            continue
    print("⚠️ Music download skipped. Video will render voiceless.")
    return None

def create_top_age_badge(male_age, female_age, output_path="workspace/age_badge.png"):
    """Creates a modern frosted glass header card displaying both character ages."""
    width, height = 1080, 240
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 46)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 26)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Glass container pill
    draw.rounded_rectangle([140, 50, 940, 170], radius=40, fill=(15, 18, 30, 210), outline=(255, 255, 255, 80), width=2)

    # Male Age (Left)
    if male_age:
        draw.text((220, 70), "HIM 👨", fill=(130, 180, 255), font=font_small)
        draw.text((235, 102), str(male_age), fill=(255, 255, 255), font=font_large)
    else:
        draw.text((220, 90), "SOLO 👤", fill=(160, 160, 160), font=font_small)

    # Center Heart Icon
    draw.text((515, 85), "💔", fill=(255, 100, 130), font=font_large)

    # Female Age (Right)
    if female_age:
        draw.text((760, 70), "HER 👩", fill=(255, 160, 200), font=font_small)
        draw.text((775, 102), str(female_age), fill=(255, 255, 255), font=font_large)

    img.save(output_path, "PNG")
    return output_path

def create_webtoon_chat_bubble(speaker_name, speaker_type, dialogue, output_path):
    """Generates an authentic Korean Webtoon chat or thought bubble."""
    width, height = 1080, 480
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font_tag = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 28)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 40)
    except Exception:
        font_tag = ImageFont.load_default()
        font_text = ImageFont.load_default()

    # Stylize based on speech vs inner monologue
    if speaker_type == "thought":
        badge_text = f"💭 {speaker_name.upper()}'S INNER THOUGHTS"
        card_fill = (22, 18, 32, 230)      # Deep soft purple frosted glass
        border_col = (255, 150, 200, 150)  # Rose gold glow
        tag_bg = (210, 60, 120, 230)
    else:
        badge_text = f"💬 {speaker_name.upper()} SPEAKS"
        card_fill = (15, 22, 35, 230)      # Midnight navy frosted glass
        border_col = (120, 180, 255, 150)  # Electric blue accent
        tag_bg = (30, 110, 220, 230)

    # Rounded dialog box
    draw.rounded_rectangle([70, 70, 1010, 420], radius=32, fill=card_fill, outline=border_col, width=3)

    # Header tag pill
    draw.rounded_rectangle([110, 42, 560, 96], radius=16, fill=tag_bg)
    draw.text((130, 52), badge_text, fill=(255, 255, 255), font=font_tag)

    # Word wrapping for dialog text
    words = dialogue.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        test_line = " ".join(current_line)
        bbox = draw.textbbox((0, 0), test_line, font=font_text)
        if (bbox[2] - bbox[0]) > 840:
            current_line.pop()
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))

    # Render wrapped text
    y_text = 135
    for line in lines[:4]:
        draw.text((115, y_text), line, fill=(255, 255, 255), font=font_text)
        y_text += 58

    img.save(output_path, "PNG")
    return output_path

def generate_manhwa_script():
    """Dynamically queries Groq for 1st-person POV dramatic storylines."""
    print("[SCRIPT] Calling Groq for 1st-person manhwa dialogue...")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return DEFAULT_STORYLINE

    client = Groq(api_key=groq_key)
    prompt = """Write a 6-scene emotional romance drama between a male mentor/college guy and a younger female student in JSON format.
Rules:
- NEVER use third-person narrator descriptions (no 'She walks', 'His heart flutters').
- Use ONLY direct first-person dialogue ('chat') or inner thoughts ('thought').
- Ages must change progressively (e.g. 25 & 14 -> 26 & 15 -> 27 & 16 -> 29 & 18).
- Each scene must have:
  "male_age": string (e.g. "25", or "" if absent)
  "female_age": string (e.g. "14")
  "speaker_name": "Him" or "Her"
  "speaker_type": "chat" or "thought"
  "dialogue": maximum 15 emotional, punchy words
  "prompt": high-detail Korean manhwa/webtoon illustration prompt ending with "9:16 vertical"

Return ONLY a raw JSON array."""

    try:
        active_models = [m.id for m in client.models.list().data]
        preferred = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192", "gemma2-9b-it"]
        model = next((m for m in preferred if m in active_models), active_models[0])

        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.75
        )
        content = res.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())
    except Exception as e:
        print(f"⚠️ Groq parse error: {e}. Using permanent dramatic storyline.")
        return DEFAULT_STORYLINE

def generate_vertical_image(prompt, output_path):
    """Generates crisp 9:16 vertical art via Pollinations."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    encoded_prompt = urllib.parse.quote(prompt + ", webtoon art, digital illustration, manhwa aesthetic")
    
    url = f"https://gen.pollinations.ai/image/{encoded_prompt}?width=1080&height=1920&nologo=true&model=flux"
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[IMAGE] Fetching 9:16 vertical frame...")
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=60)
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""):
                with open(output_path, "wb") as f:
                    f.write(res.content)
                print(f"✅ Image saved: {output_path}")
                return True
        except Exception:
            time.sleep(3)
    return False

def build_manhwa_short():
    print("=== STARTING ADVANCED MANHWA WEBTOON PRODUCTION ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    story = generate_manhwa_script()
    bg_music_file = fetch_romantic_music()
    clips = []

    for i, scene in enumerate(story):
        img_path = f"workspace/scene_{i}.jpg"
        if not generate_vertical_image(scene["prompt"], img_path):
            continue

        # 1. Base Image with slow zoom
        base_clip = ImageClip(img_path).set_duration(4.5).resize((1080, 1920))
        base_clip = base_clip.resize(lambda t: 1.0 + (0.02 * t))

        # 2. Dynamic Age Header Badge
        age_badge_path = f"workspace/age_{i}.png"
        create_top_age_badge(scene.get("male_age", ""), scene.get("female_age", ""), age_badge_path)
        age_clip = ImageClip(age_badge_path).set_position(("center", 40)).set_duration(4.5)

        # 3. Webtoon Chat/Thought Card (Lower third)
        bubble_path = f"workspace/bubble_{i}.png"
        create_webtoon_chat_bubble(
            scene.get("speaker_name", "Her"),
            scene.get("speaker_type", "thought"),
            scene.get("dialogue", "..."),
            bubble_path
        )
        bubble_clip = ImageClip(bubble_path).set_position(("center", 1320)).set_duration(4.5)

        composite = CompositeVideoClip([base_clip, age_clip, bubble_clip], size=(1080, 1920))
        clips.append(composite)

    if not clips:
        print("❌ No scenes generated!")
        return False

    print("[RENDER] Assembling full 9:16 video...")
    final_video = concatenate_videoclips(clips, method="compose")

    # Attach romantic music if available
    if bg_music_file and os.path.exists(bg_music_file):
        try:
            audio = AudioFileClip(bg_music_file).subclip(0, final_video.duration)
            final_video = final_video.set_audio(audio)
            print("🎵 Mixed romantic audio soundtrack into master video.")
        except Exception as e:
            print(f"⚠️ Audio mixing skipped: {e}")

    final_path = "videos/final_manhwa_short.mp4"
    final_video.write_videofile(
        final_path,
        fps=24,
        codec="libx264",
        audio_codec="aac" if final_video.audio else None,
        preset="ultrafast"
    )
    print(f"🎉 MASTER COMPLETE: {final_path} ready with chat bubbles & music!")
    return True

if __name__ == "__main__":
    build_manhwa_short()
