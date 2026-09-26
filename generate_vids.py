import os
import json
import time
import requests
import urllib.parse
from groq import Groq
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips

DEFAULT_STORYLINE = [
    {
        "age_male": "25",
        "age_female": "14",
        "dialogue": "Hey kid, time to study.",
        "prompt": "Korean manhwa webtoon style, handsome older male tutor looking down gently at a cute young girl studying with books, pastel lighting, soft manhwa illustration, 9:16 vertical"
    },
    {
        "age_male": "26",
        "age_female": "15",
        "dialogue": "Don't call me kid.",
        "prompt": "Korean manhwa style, handsome college guy smiling, cute teenage girl with pigtails blushing, modern living room, warm aesthetic, 9:16 vertical"
    },
    {
        "age_male": "27",
        "age_female": "16",
        "dialogue": "I love you. / You're out of your mind.",
        "prompt": "Dramatic manhwa webtoon scene, handsome man with surprised serious expression pointing at teenage girl forehead, night bench, emotional angst, 9:16 vertical"
    },
    {
        "age_male": "",
        "age_female": "18",
        "dialogue": "Finally 18. I can tell him now.",
        "prompt": "Beautiful anime manhwa girl at 18, smiling wearing casual stylish outfit, cherry blossoms falling, hopeful romantic expression, 9:16 vertical"
    },
    {
        "age_male": "29",
        "age_female": "18",
        "dialogue": "Who is she? / My girlfriend.",
        "prompt": "Heartbreak scene, handsome man in suit holding hands with glamorous woman, young girl looking shocked with teary eyes, luxury hotel lobby, high drama, 9:16 vertical"
    },
    {
        "age_male": "",
        "age_female": "18",
        "dialogue": "How could you do this to me...?",
        "prompt": "Sad manhwa girl crying in rainy street, crouching down, shattered heart atmosphere, cinematic emotional lighting, 9:16 vertical"
    }
]

def generate_manhwa_script():
    """Dynamically queries Groq for active models and generates a viral script."""
    print("[SCRIPT] Calling Groq for viral manhwa storyline...")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("⚠️ GROQ_API_KEY missing. Using fallback storyline.")
        return DEFAULT_STORYLINE
        
    client = Groq(api_key=groq_key)
    prompt = """Generate a 6-scene viral romantic angst manhwa script in JSON format.
Each scene must have:
- "age_male": male character's age (or empty string if not in scene)
- "age_female": female character's age
- "dialogue": punchy emotional subtitle (under 10 words)
- "prompt": highly descriptive prompt for Korean manhwa / anime webtoon style art, ending with "9:16 vertical"

Return ONLY raw valid JSON array, no markdown backticks."""

    try:
        # Auto-discover active models on your account
        active_models = [m.id for m in client.models.list().data]
        print(f"[GROQ] Active models available: {active_models[:4]}...")

        # Pick the best active model available
        preferred_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-8b-8192",
            "llama3-70b-8192",
            "gemma2-9b-it",
            "mixtral-8x7b-32768"
        ]
        chosen_model = next((m for m in preferred_models if m in active_models), active_models[0])
        print(f"[GROQ] Selected active model: {chosen_model}")

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=chosen_model,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        parsed = json.loads(content.strip())
        print(f"✅ Generated script ({len(parsed)} scenes) via Groq [{chosen_model}].")
        return parsed
        
    except Exception as e:
        print(f"⚠️ Groq generation skipped ({e}). Using default storyline.")
        return DEFAULT_STORYLINE

def generate_vertical_image(prompt, output_path):
    """Generates 9:16 Manhwa art using your authenticated Pollinations endpoint."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    encoded_prompt = urllib.parse.quote(prompt + ", webtoon art, digital illustration, highly detailed, manhwa aesthetic")
    
    if api_key:
        url = f"https://gen.pollinations.ai/image/{encoded_prompt}?key={api_key}&model=flux&width=1080&height=1920&nologo=true"
    else:
        url = f"https://gen.pollinations.ai/image/{encoded_prompt}?model=flux&width=1080&height=1920&nologo=true"
        
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
                print(f"✅ Saved: {output_path}")
                return True
            else:
                print(f"⚠️ Status {res.status_code}. Retrying in 4s...")
                time.sleep(4)
        except Exception as e:
            print(f"⚠️ Network error: {e}. Retrying...")
            time.sleep(4)
    return False

def build_manhwa_short():
    print("=== STARTING VOICELESS ROMANTIC MANHWA SHORT ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)
    
    story = generate_manhwa_script()
    clips = []
    
    for i, scene in enumerate(story):
        img_path = f"workspace/scene_{i}.jpg"
        if not generate_vertical_image(scene["prompt"], img_path):
            print(f"❌ Skipping scene {i} due to download failure.")
            continue
            
        base_clip = ImageClip(img_path).set_duration(4.5).resize((1080, 1920))
        base_clip = base_clip.resize(lambda t: 1.0 + (0.02 * t))
        
        composite_layers = [base_clip]
        
        # Age Tags (Top Center)
        age_str = ""
        if scene.get("age_male"):
            age_str += f"{scene['age_male']}           "
        if scene.get("age_female"):
            age_str += f"{scene['age_female']}"
            
        if age_str.strip():
            try:
                age_clip = TextClip(
                    age_str,
                    fontsize=75,
                    font="Liberation-Sans-Bold",
                    color="white",
                    stroke_color="black",
                    stroke_width=4
                ).set_position(("center", 180)).set_duration(4.5)
                composite_layers.append(age_clip)
            except Exception as e:
                print(f"⚠️ Age text overlay skipped: {e}")

        # Dialogue Subtitle (Lower Center)
        dialogue = scene.get("dialogue", "")
        if dialogue:
            try:
                txt_clip = TextClip(
                    dialogue,
                    fontsize=52,
                    font="Liberation-Sans-Bold",
                    color="white",
                    stroke_color="black",
                    stroke_width=3,
                    method="caption",
                    size=(900, None)
                ).set_position(("center", 1350)).set_duration(4.5)
                composite_layers.append(txt_clip)
            except Exception as e:
                print(f"⚠️ Dialogue overlay skipped: {e}")
                
        scene_composite = CompositeVideoClip(composite_layers, size=(1080, 1920))
        clips.append(scene_composite)

    if not clips:
        print("❌ No scenes were generated!")
        return False
        
    print("[RENDER] Assembling full 9:16 short...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    final_path = "videos/final_manhwa_short.mp4"
    final_video.write_videofile(
        final_path,
        fps=24,
        codec="libx264",
        preset="ultrafast"
    )
    print(f"🎉 SUCCESS: {final_path} is ready for YouTube!")
    return True

if __name__ == "__main__":
    build_manhwa_short()
