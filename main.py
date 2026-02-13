import os
import json
import requests
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import edge_tts
import asyncio

# --- CONFIGURATION ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY")

genai.configure(api_key=GEMINI_KEY)

# --- 1. THE BRAIN (Generate Script) ---
def get_script():
    # UPDATED MODEL: Using the highly stable Gemini 2.0 Flash
    model = genai.GenerativeModel('gemini-2.0-flash')
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
        text = response.text.strip()
        # Clean potential markdown formatting
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        return json.loads(text)
    except Exception as e:
        print(f"Error generating script: {e}")
        return None

# --- 2. THE VOICE (Edge TTS) ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

# --- 3. THE VISUALS (Pexels) ---
def get_videos(keywords):
    clips = []
    headers = {"Authorization": PEXELS_KEY}
    temp_files = []
    
    for query in keywords:
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=1&orientation=portrait"
        try:
            r = requests.get(url, headers=headers)
            data = r.json()
            if not data.get('videos'): continue
            
            video_url = data['videos'][0]['video_files'][0]['link']
            filename = f"temp_{query}.mp4"
            
            with open(filename, 'wb') as f:
                f.write(requests.get(video_url).content)
            
            temp_files.append(filename)
            clip = VideoFileClip(filename).resize(height=1920)
            if clip.w > 1080:
                clip = clip.crop(x1=clip.w/2 - 540, width=1080, height=1920)
            clips.append(clip)
            if len(clips) >= 3: break 
        except Exception as e:
            print(f"Error downloading {query}: {e}")
    return clips, temp_files

# --- 4. THE EDITOR (MoviePy) ---
def make_video(script_data):
    if not script_data: return None
    
    asyncio.run(generate_voice(script_data['script']))
    audio = AudioFileClip("voice.mp3")
    
    clips, temp_files = get_videos(script_data['keywords'])
    if not clips: return None

    final_clips = []
    dur = 0
    while dur < audio.duration:
        for c in clips:
            if dur >= audio.duration: break
            final_clips.append(c)
            dur += c.duration

    final_video = concatenate_videoclips(final_clips).set_audio(audio).set_duration(audio.duration)
    
    txt = TextClip(script_data['topic'], fontsize=70, color='white', font='Arial-Bold', 
                   method='caption', size=(800, None)).set_position('center').set_duration(audio.duration)
    
    final = CompositeVideoClip([final_video, txt])
    output_name = "final_output.mp4"
    final.write_videofile(output_name, fps=24, codec="libx264", audio_codec="aac")
    
    # Clean up
    for f in temp_files:
        try: os.remove(f)
        except: pass
    try: os.remove("voice.mp3")
    except: pass
    
    return output_name

if __name__ == "__main__":
    print("Step 1: Generating Script...")
    data = get_script()
    if data:
        print(f"Step 2: Creating Video for: {data['topic']}")
        res = make_video(data)
        if res:
            print(f"SUCCESS: Video ready at {res}")
    else:
        print("FAILED: Script generation failed.")
