import os
import time
import requests
from gtts import gTTS
from moviepy.editor import ImageClip, concatenate_videoclips

def generate_free_voice(text, output_path):
    """Generates speech completely free using Google's TTS engine without any API keys."""
    print("[VOICE-STUDIO] Generating free narration track...")
    try:
        tts = gTTS(text=text, lang='en', tld='com')
        tts.save(output_path)
        print(f"✅ Voice Track Saved: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Voice Engine Failed: {e}")
        return False

def generate_premium_image(prompt, output_path):
    """Generates scenes using your Pollinations key with built-in cloud retry safety layers."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    
    style_lock = ", flat 2D vector art, minimalist corporate noir style, high contrast, cinematic shadow lighting, dark charcoal background"
    full_prompt = prompt + style_lock
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    # 🌟 FIX: Removed '&enhance=true' to skip the heavily locked cloud upscaler queue
    url = f"https://image.pollinations.ai/p/{requests.utils.quote(full_prompt)}?width=1920&height=1080&nologo=true"
    
    max_retries = 5
    backoff_delay = 5  # Seconds to wait between crowded queue attempts
    
    for attempt in range(max_retries):
        print(f"[IMAGE-FACTORY] Generating asset (Attempt {attempt + 1}/{max_retries})...")
        try:
            response = requests.get(url, headers=headers, timeout=45)
            
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print(f"✅ Image Asset Secured: {output_path}")
                return True
                
            elif response.status_code == 402 or "Queue full" in response.text:
                print(f"⚠️ [QUEUE BUSY] Shared cloud IP collision detected. Retrying in {backoff_delay}s...")
                time.sleep(backoff_delay)
                
            else:
                print(f"❌ Image Factory Failed with Status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"⚠️ Network glitch encountered: {e}. Retrying...")
            time.sleep(backoff_delay)
            
    print("❌ Image Factory completely timed out after maximum cloud retries.")
    return False

def build_production_short():
    print("=== STARTING RESILIENT DUAL-ENGINE PRODUCTION ===")
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
    
    img_success = generate_premium_image(video_chapters["intro"]["prompt"], intro_img)
    voice_success = generate_free_voice(video_chapters["intro"]["text"], intro_audio)
    
    if not img_success or not voice_success:
        print("\n❌ STOPPING PRODUCTION: Core assets could not be compiled.")
        return False
    
    intro_clip = ImageClip(intro_img).set_duration(10)
    intro_clip = intro_clip.resize(lambda t: 1.0 + (0.03 * t))
    clips.append(intro_clip)
    
    # 2. Generate Chapter Scene Cuts
    for index, scene in enumerate(video_chapters["scenes"]):
        img_path = f"workspace/premium_scene_{index}.jpg"
        
        if not generate_premium_image(scene["prompt"], img_path):
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
    
    print("[RENDER] Exporting premium master MP4...")
    final_movie.write_videofile(
        "videos/final_premium_short.mp4",
        fps=24,
        codec="libx264",
        preset="ultrafast"
    )
    print("🎉 PRODUCTION COMPLETE: videos/final_premium_short.mp4 is ready!")
    return True

if __name__ == "__main__":
    build_production_short()
