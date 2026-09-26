import os
import json
import time
import math
import requests
import textwrap
import urllib.parse
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

DEFAULT_DATA = {
    "recommended_yt_song": "Moral of the Story - Ashe (Shorts Trending)",
    "yt_music_search_query": "Moral of the Story Ashe",
    "video_title": "When you love someone you can't have... 💔 #Shorts #manhwa #lovestory",
    "scenes": [
        {
            "male_age": "25",
            "female_age": "14",
            "bubble_type": "speech",
            "speaker_label": "HIM",
            "dialogue": "Focus on your books, kid. Stop looking at me.",
            "prompt": "Korean manhwa style, handsome 25 year old male tutor looking down gently at cute 14 year old student, clean anime webtoon, no chinese text, no hanzi, no kanji, no subtitles, no watermark, 9:16 vertical"
        },
        {
            "male_age": "26",
            "female_age": "15",
            "bubble_type": "thought",
            "speaker_label": "HER THOUGHTS",
            "dialogue": "I made these chocolates for you... why is my heart racing?",
            "prompt": "Korean manhwa style, cute 15 year old anime girl blushing holding small gift behind back, soft pastel lighting, clean anime webtoon, no chinese text, no hanzi, no subtitles, 9:16 vertical"
        },
        {
            "male_age": "27",
            "female_age": "16",
            "bubble_type": "speech",
            "speaker_label": "HER",
            "dialogue": "I don't care about the age gap! I love you!",
            "prompt": "Dramatic manhwa scene, tearful 16 year old girl confessing under rain, handsome 27 year old man stunned, clean anime webtoon, no chinese text, no kanji, no watermark, 9:16 vertical"
        },
        {
            "male_age": "27",
            "female_age": "16",
            "bubble_type": "speech",
            "speaker_label": "HIM",
            "dialogue": "You are just a child to me. Forget it.",
            "prompt": "Cold anime man turning face away in dark shadows, painful heartbreak, clean anime webtoon, no chinese text, no hanzi, no subtitles, 9:16 vertical"
        },
        {
            "male_age": "29",
            "female_age": "18",
            "bubble_type": "speech",
            "speaker_label": "HIM",
            "dialogue": "Meet Claire. We are getting married in June.",
            "prompt": "Heartbreak scene, handsome man holding hands with elegant woman, 18 year old girl standing frozen in shock, clean anime webtoon, no chinese text, no subtitles, 9:16 vertical"
        },
        {
            "male_age": "",
            "female_age": "18",
            "bubble_type": "thought",
            "speaker_label": "HER THOUGHTS",
            "dialogue": "You told me to wait till I grew up... but you never waited for me.",
            "prompt": "Heartbroken anime girl crying in heavy rain, shattered expression, dramatic cinematic lighting, clean anime webtoon, no chinese text, no hanzi, no subtitles, 9:16 vertical"
        }
    ]
}

def get_font(size):
    """Loads clean sans-serif font from Ubuntu system path with safe fallback."""
    paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def draw_top_age_bar(male_age, female_age, output_path):
    """Draws a clean top UI bar tracking character ages."""
    img = Image.new("RGBA", (1080, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_val = get_font(44)
    font_lbl = get_font(24)

    # Frosted header pill
    draw.rounded_rectangle([150, 40, 930, 160], radius=35, fill=(15, 20, 32, 220), outline=(255, 255, 255, 90), width=3)

    if male_age:
        draw.text((220, 60), "HIM 👨", font=font_lbl, fill=(140, 190, 255))
        draw.text((235, 92), str(male_age), font=font_val, fill=(255, 255, 255))
    else:
        draw.text((220, 80), "SOLO 👤", font=font_lbl, fill=(180, 180, 180))

    draw.text((515, 75), "💔", font=font_val, fill=(255, 100, 140))

    if female_age:
        draw.text((750, 60), "HER 👩", font=font_lbl, fill=(255, 160, 210))
        draw.text((765, 92), str(female_age), font=font_val, fill=(255, 255, 255))

    img.save(output_path, "PNG")
    return output_path

def draw_manga_bubble(text, speaker_label, bubble_type, output_path):
    """Draws genuine Manga speech and thought bubbles with zero boxy edges."""
    canvas_w, canvas_h = 960, 460
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_text = get_font(34)
    font_badge = get_font(22)

    wrapped_lines = textwrap.wrap(text, width=28)[:4]
    formatted_text = "\n".join(wrapped_lines)

    bbox = draw.multiline_textbbox((0, 0), formatted_text, font=font_text, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    bw = min(canvas_w - 60, max(460, tw + 90))
    bh = max(180, th + 80)
    bx0 = (canvas_w - bw) // 2
    by0 = 40
    bx1 = bx0 + bw
    by1 = by0 + bh

    if bubble_type == "thought":
        # 1. Thought Bubble (Puffy cloud lobes + descending thought circles)
        cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
        rx, ry = bw // 2, bh // 2
        num_lobes = 14
        lobe_r = 38

        # Draw cloud puff perimeter
        for i in range(num_lobes):
            theta = 2 * math.pi * i / num_lobes
            lx = int(cx + (rx - 15) * math.cos(theta))
            ly = int(cy + (ry - 10) * math.sin(theta))
            draw.ellipse([lx - lobe_r, ly - lobe_r, lx + lobe_r, ly + lobe_r], fill="white", outline="black", width=4)

        # Fill center core to hide internal outlines
        draw.ellipse([bx0 + 20, by0 + 15, bx1 - 20, by1 - 15], fill="white")

        # Trailing thought dots pointing to character's head
        tail_x = cx - 40
        draw.ellipse([tail_x - 16, by1 + 18, tail_x + 16, by1 + 50], fill="white", outline="black", width=3)
        draw.ellipse([tail_x - 30, by1 + 58, tail_x - 6, by1 + 82], fill="white", outline="black", width=3)
        draw.ellipse([tail_x - 42, by1 + 90, tail_x - 24, by1 + 108], fill="white", outline="black", width=2)

        # Monologue pill
        draw.rounded_rectangle([cx - 120, by0 - 18, cx + 120, by0 + 18], radius=12, fill=(240, 80, 140))
        draw.text((cx, by0), f"💭 {speaker_label}", font=font_badge, fill="white", anchor="mm")

    else:
        # 2. Dialogue Speech Bubble (Oval body with directional speech tail)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=45, fill="white", outline="black", width=5)

        # Downward speech pointer tail
        tail_x = (bx0 + bx1) // 2 - 20
        tail = [
            (tail_x - 25, by1 - 2),
            (tail_x - 45, by1 + 55),
            (tail_x + 10, by1 - 2)
        ]
        draw.polygon(tail, fill="white", outline="black")
        draw.line([(tail_x - 23, by1 - 1), (tail_x + 8, by1 - 1)], fill="white", width=7)

        # Dialogue pill
        cx = (bx0 + bx1) // 2
        draw.rounded_rectangle([cx - 90, by0 - 18, cx + 90, by0 + 18], radius=12, fill=(35, 120, 240))
        draw.text((cx, by0), f"💬 {speaker_label}", font=font_badge, fill="white", anchor="mm")

    # Centered black manga dialogue
    text_x = (bx0 + bx1) // 2
    text_y = (by0 + by1) // 2
    draw.multiline_text((text_x, text_y), formatted_text, font=font_text, fill="black", align="center", anchor="mm")

    img.save(output_path, "PNG")
    return output_path

def generate_story_and_metadata():
    """Asks Groq to create dramatic 1st-person romance script + pick trending YouTube Library song."""
    print("[GROQ] Calling AI to write script and select matching YouTube Audio...")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("⚠️ GROQ_API_KEY missing. Using default manhwa storyline.")
        return DEFAULT_DATA

    client = Groq(api_key=groq_key)
    prompt = """Create a 6-scene viral first-person romantic angst manhwa script in JSON format.
Also choose one emotional, trending song from the YouTube Shorts Audio Library that matches this mood.

Return ONLY raw JSON with this exact structure:
{
  "recommended_yt_song": "Song Title - Artist Name (Shorts Trending)",
  "yt_music_search_query": "Search query for YouTube audio picker",
  "video_title": "Catchy Shorts Title with #Shorts #manhwa #lovestory",
  "scenes": [
    {
      "male_age": "25",
      "female_age": "14",
      "bubble_type": "speech",
      "speaker_label": "HIM",
      "dialogue": "Short first-person text under 12 words",
      "prompt": "Clean Korean manhwa style, [character action], clean anime webtoon, no chinese text, no hanzi, no kanji, no subtitles, no watermark, 9:16 vertical"
    }
  ]
}

Rules:
- bubble_type must be either 'speech' or 'thought'
- NEVER write in third person (no 'she looks away'). Use only direct dialogue or inner thoughts.
- Age gap must progress over the 6 scenes.
- Every prompt MUST contain 'no chinese text, no hanzi, no kanji, no subtitles, 9:16 vertical'.
"""
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
        data = json.loads(content.strip())
        print(f"✅ Groq generated script. Recommended YT Library Song: {data.get('recommended_yt_song')}")
        return data
    except Exception as e:
        print(f"⚠️ Groq API skipped ({e}). Using default storyline.")
        return DEFAULT_DATA

def fetch_vertical_image(prompt, output_path):
    """Fetches vertical 9:16 art from Pollinations with sanitized anti-text parameters."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    sanitized_prompt = prompt + ", masterpiece manhwa, beautiful clean digital anime art, 9:16 vertical"
    encoded = urllib.parse.quote(sanitized_prompt)

    url = f"https://gen.pollinations.ai/image/{encoded}?width=1080&height=1920&model=flux&nologo=true"
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=60)
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""):
                with open(output_path, "wb") as f:
                    f.write(res.content)
                print(f"✅ Secured clean scene: {output_path}")
                return True
        except Exception:
            time.sleep(3)
    return False

def build_soundless_short():
    print("=== STARTING VOICELESS MANHWA SHORTS PRODUCTION ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    data = generate_story_and_metadata()

    # Save metadata for upload_script.py
    with open("workspace/video_metadata.json", "w") as f:
        json.dump(data, f, indent=2)

    scenes = data.get("scenes", DEFAULT_DATA["scenes"])
    clips = []

    for i, sc in enumerate(scenes):
        img_path = f"workspace/scene_{i}.jpg"
        if not fetch_vertical_image(sc["prompt"], img_path):
            continue

        # 1. Base Image with slow dramatic zoom
        base = ImageClip(img_path).set_duration(4.5).resize((1080, 1920))
        base = base.resize(lambda t: 1.0 + (0.025 * t))

        # 2. Dynamic Age Header Bar
        age_bar_path = f"workspace/age_{i}.png"
        draw_top_age_bar(sc.get("male_age", ""), sc.get("female_age", ""), age_bar_path)
        age_clip = ImageClip(age_bar_path).set_position(("center", 40)).set_duration(4.5)

        # 3. Manga Speech/Thought Bubble (Positioned over character head)
        bubble_path = f"workspace/bubble_{i}.png"
        draw_manga_bubble(
            sc.get("dialogue", "..."),
            sc.get("speaker_label", "TALK"),
            sc.get("bubble_type", "speech"),
            bubble_path
        )
        bubble_clip = ImageClip(bubble_path).set_position(("center", 260)).set_duration(4.5)

        composite = CompositeVideoClip([base, age_clip, bubble_clip], size=(1080, 1920))
        clips.append(composite)

    if not clips:
        print("❌ No scenes rendered successfully.")
        return False

    print("[RENDER] Assembling 100% SOUNDLESS master video...")
    final_video = concatenate_videoclips(clips, method="compose")

    # Strictly soundless output: audio=False removes any empty audio container
    final_path = "videos/final_manhwa_short.mp4"
    final_video.write_videofile(
        final_path,
        fps=24,
        codec="libx264",
        audio=False,
        preset="ultrafast"
    )
    print(f"🎉 MASTER COMPLETE (SOUNDLESS): {final_path}")
    print(f"🎵 Recommended YouTube Shorts Sound: {data.get('recommended_yt_song')}")
    return True

if __name__ == "__main__":
    build_soundless_short()
