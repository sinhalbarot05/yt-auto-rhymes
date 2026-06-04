import os
import json
import time
import requests
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

def generate_premium_voice(text, output_path):
    """Generates deep, human-like dramatic narration using your fresh OpenAI premium key."""
    print("[VOICE-STUDIO] Calling neural speech engine with fresh key...")
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY is empty. Make sure your fresh key is in GitHub Secrets.")
        return False
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    # Using 'tts-1-hd' for maximum fidelity uncompressed audio
    # Using 'onyx' for that deep, cynical insider voice tone you requested
    payload = {
        "model": "tts-1-hd",
        "voice": "onyx",
        "input": text
    }
    
    response = requests.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
    
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✅ Premium Voice Track Saved: {output_path}")
        return True
    else:
        print(f"❌ Voice Engine Failed (Status {response.status_code}): {response.text}")
        return False

def generate_premium_image(prompt, output_path):
    """Generates crisp 1080p cinematic scenes using your fresh Pollinations premium key."""
    print(f"[IMAGE-FACTORY] Generating high-end scene asset...")
    api_key = os.getenv("POLLINATIONS_API_KEY")
    
    # Premium corporate noir style lock to guarantee high quality
    style_lock = ", flat 2D vector art, minimalist corporate noir style, high contrast, cinematic shadow lighting, dark charcoal background"
    full_prompt = prompt + style_lock
    
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"https://image.pollinations.ai/p/{requests.utils.quote(full_prompt)}?width=1920&height=1080&nologo=true&enhance=true"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✅ Premium Image Secured: {output_path}")
        return True
    else:
        print(f"❌ Image Factory Failed: Status {response.status_code}")
        return False

def build_premium_short():
    print("=== STARTING FRESH PREMIUM DARK LEDGER RENDER ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)
    
    # The 10-5-5-5 pacing matrix layout
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
    
    # 1. Render the Heavy 10-Second Intro Anchor
    intro_img = "workspace/premium_intro.jpg"
    intro_audio = "workspace/premium_intro.mp3"
    
    generate_premium_image(video_chapters["intro"]["prompt"], intro_img)
    generate_premium_voice(video_chapters["intro"]["text"], intro_audio)
    
    # Set high-quality duration and smooth Ken Burns zoom camera motion
    intro_clip = ImageClip(intro_img).set_duration(10)
    intro_clip = intro_clip.resize(lambda t: 1.0 + (0.03 * t))
    clips.append(intro_clip)
    
    # 2. Render sequential 5-Second Chapter Cuts
    for index, scene in enumerate(video_chapters["scenes"]):
        img_path = f"workspace/premium_scene_{index}.jpg"
        generate_premium_image(scene["prompt"], img_path)
        
        slide_clip = ImageClip(img_path).set_duration(5)
        # Alternate camera zoom paths to hook human viewer attention spans
        if index % 2 == 0:
            slide_clip = slide_clip.resize(lambda t: 1.06 - (0.02 * t))
        else:
            slide_clip = slide_clip.resize(lambda t: 1.0 + (0.04 * t))
            
        clips.append(slide_clip)
        
    # 3. Stitch & Export Studio-Grade Finished Movie File
    print("[STUDIO] Compiling video timeline matrix...")
    final_movie = concatenate_videoclips(clips, method="compose")
    
    # Cranking render settings to absolute maximum high quality
    print("[RENDER] Exporting high-bitrate master MP4...")
    final_movie.write_videofile(
        "videos/final_premium_short.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium", # Slows processing slightly to maximize video crispness
        ffmpeg_params=["-crf", "18"] # Ultra-low compression factor = flawless image quality
    )
    print("🎉 MASTER PRODUCTION COMPLETE: videos/final_premium_short.mp4 is ready!")

if __name__ == "__main__":
    build_premium_short()
