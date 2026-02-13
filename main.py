import os
import json
import random
import time
import requests
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import edge_tts
import asyncio

# --- CONFIGURATION ---
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
# Note: We don't need YouTube tokens for this test, but keeping them prevents errors if you switch back

genai.configure(api_key=GEMINI_KEY)

# --- 1. THE BRAIN (Generate Script) ---
def get_script():
    model = genai.GenerativeModel('gemini-pro')
    prompt = """
    Create a 30-second YouTube Short script about a fascinating random fact (Space, History, or Nature).
    Return ONLY valid JSON with this format:
    {
        "topic": "The topic title",
        "script": "The full voiceover text (approx 50-60 words).",
        "keywords": ["query1", "query2", "query3"],
        "title": "Clickbait Title for YouTube",
        "description": "Video description with hashtags"
    }
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '')
        return json.loads(text)
    except Exception as e:
        print(f"Error generating script: {e}")
        return None

# --- 2. THE VOICE (Edge TTS) ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

# --- 3. THE VISUALS (Pexels) ---
def get_videos(keywords, duration_needed):
    clips = []
    headers = {"Authorization": PEXELS_KEY}
    
    # Try multiple keywords to ensure we get enough clips
    for query in keywords:
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=3&orientation=portrait"
        try:
            r = requests.get(url, headers=headers)
            data = r.json()
            
            if not data.get('videos'): 
                print(f"No videos found for {query}")
                continue
            
            # Get the best video file
            video_files = data['videos'][0]['video_files']
            # Sort by quality (width) to get best resolution
            video_files.sort(key=lambda x: x['width'], reverse=True)
            video_url = video_files[0]['link']
            
            filename = f"temp_{query}.mp4"
            with open(filename, 'wb') as f:
                f.write(requests.get(video_url).content)
            
            clip = VideoFileClip(filename)
            
            # Resize/Crop logic
            if clip.rotation == 90:
                clip = clip.resize(clip.rotation)
                
            clip = clip.resize(height=1920)
            if clip.w > 1080:
                clip = clip.crop(x1=clip.w/2 - 540, width=1080, height=1920)
                
            clips.append(clip)
            if len(clips) >= 3: break 
        except Exception as e:
            print(f"Error downloading video for {query}: {e}")
            continue
        
    return clips

# --- 4. THE EDITOR (MoviePy) ---
def make_video(script_data):
    if not script_data: return None
    
    # A. Generate Audio
    asyncio.run(generate_voice(script_data['script']))
    audio = AudioFileClip("voice.mp3")
    
    # B. Get Video Clips
    clips = get_videos(script_data['keywords'], audio.duration)
    if not clips:
        print("Error: No videos could be downloaded.")
        return None

    # Loop clips if they are shorter than audio
    final_clips = []
    current_duration = 0
    
    # Simple logic to cycle through clips
    while current_duration < audio.duration:
        for clip in clips:
            if current_duration >= audio.duration: break
            final_clips.append(clip)
            current_duration += clip.duration

    final_video = concatenate_videoclips(final_clips)
    final_video = final_video.set_audio(audio)
    final_video = final_video.subclip(0, audio.duration)
    
    # C. Add Captions (Simple Center Text)
    # Using 'method=caption' wraps text automatically
    txt_clip = TextClip(script_data['topic'], fontsize=70, color='white', font='Arial-Bold', method='caption', size=(800, None))
    txt_clip = txt_clip.set_position(('center', 'center')).set_duration(final_video.duration)
    
    # Combine
    result = CompositeVideoClip([final_video, txt_clip])
    output_filename = "final_output.mp4"
    result.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    return output_filename

# --- MAIN EXECUTION (TEST MODE) ---
if __name__ == "__main__":
    print("--- STARTING TEST RUN ---")
    
    print("1. Generating Script...")
    data = get_script()
    
    if data:
        print(f"Topic: {data.get('topic')}")
        print(f"Script Length: {len(data.get('script', ''))} chars")
        
        print("2. Creating Video...")
        video_file = make_video(data)
        
        if video_file:
            print(f"SUCCESS! Video saved as: {video_file}")
            print("To watch it: Go to the Summary page of this Action run and download 'test-video-result' from Artifacts.")
        else:
            print("FAILED to create video file.")
    else:
        print("FAILED to generate script.")
        
    print("--- TEST RUN FINISHED ---")
