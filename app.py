from flask import Flask, render_template, request, jsonify
import yt_dlp
import requests
from webvtt import WebVTT
from io import StringIO
import google.generativeai as genai
from typing import Dict
import os

app = Flask(__name__)

def get_youtube_transcript(video_url: str, api_key: str = None) -> Dict:

    # Configure yt-dlp options
    ydl_opts = {
        'writesubtitles': True,       # Enable subtitle extraction
        'writeautomaticsub': True,    # Include automatic captions
        'subtitleslangs': ['en'],     # Prefer English subtitles
        'skip_download': True,        # Do not download the video
    }

    # Extract video info
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    
    # Check for available subtitles
    subtitles = info.get('subtitles', {}).get('en', [])
    automatic = info.get('automatic_captions', {}).get('en', [])
    
    if not subtitles and not automatic:
        return {'status': 'error', 'message': "No English subtitles found for this video."}

    # Select manual or automatic subtitles
    sub_list = subtitles if subtitles else automatic
    
    # Find a supported subtitle format
    selected_sub = None
    for sub in sub_list:
        if sub['ext'] in ['vtt', 'json3']:
            selected_sub = sub
            break
    
    if not selected_sub:
        return {'status': 'error', 'message': "No supported subtitle format found."}
    
    # Download subtitle content
    response = requests.get(selected_sub['url'])
    response.raise_for_status()
    content = response.text
    
    # Parse based on format
    if selected_sub['ext'] == 'vtt':
        vtt_buffer = StringIO(content)
        captions = WebVTT().read(vtt_buffer)
        transcript = ' '.join([caption.text.strip() for caption in captions])
    elif selected_sub['ext'] == 'json3':
        import json
        data = json.loads(content)
        transcript = ' '.join(
            seg['utf8']
            for event in data['events']
            for seg in event.get('segs', [])
            if 'utf8' in seg
        )
    
    # Write transcript to file
    output_filename = os.path.join('static', 'downloads', 'transcript.txt')
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(transcript)
    
    # Generate notes if API key is provided
    if api_key:
        notes_result = generate_notes_and_summary(transcript, api_key)
        return {
            'status': 'success',
            'transcript': transcript,
            'notes': notes_result['content'],
            'message': f"Transcript and notes generated successfully"
        }
    
    return {
        'status': 'success',
        'transcript': transcript,
        'message': "Transcript generated successfully"
    }

def generate_notes_and_summary(transcript: str, api_key: str) -> Dict[str, str]:
    """
    Generate structured notes and summary from transcript using Gemini API
    """
    # Configure the Gemini API
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-thinking-exp-01-21')
    
    notes_prompt = """
    Please analyze this transcript and create:
    1. Detailed bullet-point notes of the key points and concepts
    2. A clear, concise summary in simple language that anyone can understand
    3. present the notes in a way that is easy to read and understand use BOLD for the key points and concepts, maintain space between the bullet points and topics
    
    Format the response as follows:
    
    KEY NOTES:
    • [bullet points here]
    
    SUMMARY:
    [layman's terms summary here]

    only return the notes and summary, no other text
    
    Transcript:
    {transcript}
    """
    
    try:
        response = model.generate_content(notes_prompt.format(transcript=transcript))
        
        # Write the response to a separate file
        output_filename = os.path.join('static', 'downloads', 'notes_and_summary.txt')
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
            
        return {
            'status': 'success',
            'message': 'Notes and summary generated successfully',
            'content': response.text.replace('```', '')
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error generating notes and summary: {str(e)}',
            'content': None
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    video_url = request.form.get('video_url')
    api_key = request.form.get('api_key')
    
    if not video_url:
        return jsonify({'status': 'error', 'message': 'Please provide a YouTube URL'})
    
    result = get_youtube_transcript(video_url, api_key)
    return jsonify(result)

if __name__ == '__main__':
    # Create downloads directory if it doesn't exist
    os.makedirs(os.path.join('static', 'downloads'), exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)