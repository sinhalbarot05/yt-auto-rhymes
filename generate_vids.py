import os
import json
import time
import requests
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

def generate_premium_voice(text, output_path):
    """Generates deep, human-like dramatic narration using your OpenAI key."""
    print("[VOICE-STUDIO] Calling neural speech engine...")
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY is empty in GitHub Secrets.")
        return False
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "tts-1-hd",
        "voice": "onyx",
        "input": text
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"✅ Voice Track Saved: {output_path}")
            return True
        else:
            print(f"❌ OpenAI Voice Engine Failed (Status {response.status_code}). Please verify your OPENAI_API_KEY secret.")
            print(f"   Response details: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Voice Engine Network Error: {e}")
        return False

def generate_free_tier_image(prompt, output_path):
    """Pulls high-res images from the free tier of Pollinations, completely bypassing key verification and 402 errors."""
    print(f"[IMAGE-FACTORY] Generating high-end scene asset via public free array...")
    
    # Premium corporate noir style lock to guarantee professional visual output
    style_lock = ", flat 2D vector art, minimalist corporate noir style, high contrast, cinematic shadow lighting, dark charcoal background"
    full_prompt = prompt + style_lock
    
    # Using the clean public endpoint without authorization headers or paid parameters
    url = f"https://image.pollinations.ai/p/{requests.utils.quote(full_prompt)}?width=1920&height=1080&nologo=true"
    
    try:
        response = requests.get(url, timeout=45)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"✅ Image Asset Secured: {output_path}")
            return True
        else:
            print(f"❌ Image Factory Failed: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Image Factory Connection Error: {e}")
        return False

def build_premium_short():
    print("=== STARTING FRESH PREMIUM DARK LEDGER RENDER ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)
    
    video_chapters = {
        "intro": {
            "text": "When you walk into a bank with zero dollars... you aren't a customer. You are a liability.",
            "prompt": "An empty, cold, dark bank lobby with dramatic sharp lighting, minimalist charcoal corporate noir style"
        },
        "scenes": [
            {
                "text": "At the ten-thousand dollar barrier, the system charges you money... just to hold your money.",
                "prompt": "A stoic man in a sharp plain suit looking down at a glowing screen, high contrast shadow"
            },
            {
                "text": "But cross the seven-figure mark? The rules completely bend. The branch manager invites you to a private room... and the fees vanish.",
                "prompt": "The same stoic man sitting in an upscale minimalist boardroom chair, warm luxury accent lighting"
            }
        ]
    }
    
    clips = []
    
    # 1. Generate Intro Media Assets
    intro_img = "workspace/premium_intro.jpg"
    intro_audio = "workspace/premium_intro.mp3"
    
    img_success = generate_free_tier_image(video_chapters["intro"]["prompt"], intro_img)
    voice_success = generate_premium_voice(video_chapters["intro"]["text"], intro_audio)
    
    # Guard clause to stop execution gracefully if assets failed to generate
    if not img_success or not voice_success:
        print("\n❌ STOPPING PRODUCTION: Core assets could not be downloaded due to the API errors above. Fix the keys before running again.")
        return False
    
    intro_clip = ImageClip(intro_img).set_duration(10)
    intro_clip = intro_clip.resize(lambda t: 1.0 + (0.03 * t))
    clips.append(intro_clip)
    
    # 2. Generate Chapter Scene Cuts
    for index, scene in enumerate(video_chapters["scenes"]):
        img_path = f"workspace/premium_scene_{index}.jpg"
        
        if not generate_free_tier_image(scene["prompt"], img_path):
            print(f"❌ STOPPING PRODUCTION: Failed to generate scene slide {index}.")
            return False
        
        slide_clip = ImageClip(img_path).set_duration(5)
        if index % 2 == 0:
            slide_clip = slide_clip.resize(lambda t: 1.06 - (0.02 * t))
        else:
            slide_clip = slide_clip.resize(lambda t: 1.0 + (0.04 * t))
            
        clips.append(slide_clip)
        
    # 3. Compile Master Timeline
    print("[STUDIO] Compiling video timeline matrix...")
    final_movie = concatenate_videoclips(clips, method="compose")
    
    print("[RENDER] Exporting high-bitrate master MP4...")
    final_movie.write_videofile(
        "videos/final_premium_short.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast"
    )
    print("🎉 MASTER PRODUCTION COMPLETE: videos/final_premium_short.mp4 is ready!")
    return True

if __name__ == "__main__":
    build_premium_short()
