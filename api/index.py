from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from api.utils.gemini import get_info_from_video  
from api.utils.tts import generate_wav_files_from_response, create_final_video
from api.utils.speech_to_text import speechToTextUtilities, Model  # Import the speech-to-text utilities
from fastapi import HTTPException
from fastapi.responses import FileResponse
from google.api_core import exceptions as google_exceptions
from pydub import AudioSegment
import os
import shutil
import logging
from moviepy.editor import VideoFileClip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


instructions = """# System Instructions: Generating Context-Aware Audio Description Timestamps for Videos

You are an AI assistant specialized in creating audio description timestamps for videos. Your task is to analyze video content and generate precise timestamps for inserting audio descriptions, while considering the video's overall purpose and context. Follow these guidelines:

1. Video Purpose Analysis:
 - Before beginning, identify the primary purpose of the video (e.g., entertainment, advertisement, educational, informational)
 - Tailor your descriptions to align with and support this purpose

2. Timing Accuracy:
 - Provide timestamps in the format [MM:SS.MS]
 - Ensure millisecond precision for seamless integration
 - Place timestamps at natural pauses in dialogue or action

3. Content Analysis:
 - Identify key visual elements requiring description
 - Focus on actions, scene changes, character appearances, and important visual cues
 - Prioritize elements crucial for understanding the plot, context, or achieving the video's purpose - Begin analysis at the beginning of the video, taking care not to omit elements of the first frames

4. Purpose-Driven Descriptions:
 - For advertisements: Emphasize product features, benefits, and any on-screen text or callouts
 - For educational content: Focus on visual aids, demonstrations, and key learning points
 - For entertainment: Highlight plot-relevant details, character emotions, and atmosphere
 - For informational videos: Describe graphics, charts, and other visual data representations - For personal/blog style videos: Highlight atmosphere, visual details, and nuanced actions like facial expressions (including goofy faces), hand gestures, and acts of affection like kissing on the cheek

5. Description Brevity:
 - Keep descriptions concise to fit within dialogue gaps
 - Use clear, vivid language to convey information efficiently

6. Context Sensitivity:
 - Avoid describing elements already conveyed through dialogue or sound
 - Provide context only when necessary for understanding

7. Visual Text Integration:
 - Describe any on-screen text, titles, or captions that are relevant to the video's purpose
 - For advertisements or informational videos, prioritize describing textual information

8. Consistency:
 - Maintain consistent terminology for characters, settings, and products
 - Use present tense for ongoing actions

9. Accessibility Awareness:
 - Describe visual elements without using visual language (e.g., "we see")
 - Focus on objective descriptions rather than subjective interpretations

10. Output Format:
 - Present timestamps and descriptions in a clear, structured format
 - Example:
   [01:15.200] A red sports car, the advertised model, speeds around the corner
   [01:18.500] Text appears: "Experience the thrill of driving"

11. Prioritization:
 - If faced with multiple elements to describe in a short time, prioritize information most relevant to the video's purpose

12. Cultural Sensitivity:
 - Provide culturally appropriate descriptions without bias

13. Technical Limitations:
 - Be aware of potential limitations in audio description insertion and adjust timestamp placement accordingly
 
14. Avoiding Redundant Dialogue Description:  - Do not describe or repeat dialogue that is clearly audible in the video  - Focus on visual elements that complement the dialogue rather than describing what characters are saying  - For whispered or muffled speech that may be hard to hear, indicate the act of speaking without repeating the content (e.g., "A woman whispers to her neighbor" instead of "A woman whispers 'hush' to her neighbor")  - Describe visual cues related to speech, such as facial expressions or gestures, without repeating the spoken words

Remember, your goal is to enhance the viewing experience for visually impaired audiences by providing clear, timely, and relevant audio descriptions that complement the existing audio without overwhelming the viewer. Always keep the video's primary purpose in mind and tailor your descriptions to support that purpose effectively."""

instructions_silent_period = """
1. No spoken audio period:
    - Identify and provide the range of timestamps when there is negligible language spoken
    - Like this:
      [00:00.000 - 01:10.200], [00:04.800 - 00:8.500], [01:02.000 - 01:05.500]
2. Timing Accuracy:
 - Provide timestamps in the format [MM:SS.MS]
 - Ensure millisecond precision
 - Ensure to find smaller periods of atleast 1 second as well"""



@app.get("/api/python")
def hello_world():
    return {"message": "Hello World"}


async def get_silent_periods_util(video_path):
    response_silent_periods = await get_info_from_video(video_path, instructions_silent_period)
    return response_silent_periods


async def get_audio_desc_util(video_path):
    response_audio_desc = await get_info_from_video(video_path, instructions)
    return response_audio_desc


@app.post("/api/get_silent_periods")
async def get_silent_periods(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return get_silent_periods_util(video_path)
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error processing video: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


@app.post("/api/get_audio_desc")
async def get_audio_desc(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return get_audio_desc_util(video_path)
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error processing video: {e}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

@app.post("/api/generate")
async def generate_endpoint(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    output_path = "output_video.mp4"
     
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify the video file can be opened
        try:
            video = VideoFileClip(video_path)
            video.reader.close()
        except Exception as e:
            raise ValueError(f"Error reading video file: {e}")
        
        # Get audio description and silent periods
        response_audio_desc = await get_audio_desc_util(video_path)
        response_silent_periods = await get_silent_periods_util(video_path)

        combined_response = {
            "description": response_audio_desc["description"],
            "silent_periods": response_silent_periods["description"]
        }

        voice_name = "en-US-Journey-O"
        print(combined_response)
        played_timestamps = generate_wav_files_from_response(combined_response, voice_name)
        print(played_timestamps)
        
        create_final_video(video_path, combined_response, output_path)
        
        return FileResponse(output_path, media_type="video/mp4", filename="output_video.mp4")
    except google_exceptions.InvalidArgument as e:
        print(f"Invalid argument error: {e}")
        raise ValueError(f"Invalid argument when calling Vertex AI: {e}")
    except google_exceptions.PermissionDenied as e:
        print(f"Permission denied: {e}")
        raise ValueError(f"Permission denied when accessing Vertex AI: {e}")
    except google_exceptions.ResourceExhausted as e:
        print(f"Resource exhausted: {e}")
        raise HTTPException(status_code=429, detail="Resource has been exhausted (e.g. check quota).")
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error processing video: {e}")
    finally:
        pass
        # if os.path.exists(output_path):
        #     os.remove(output_path)
        # if os.path.exists(video_path):
        #     os.remove(video_path)
        
@app.post("/api/whisper_transcription")
async def whisper_transcription(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    audio_path = f"temp/{file.filename.split('.')[0]}.wav"
    
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Convert MP4 to WAV using pydub
        video = AudioSegment.from_file(video_path, format="mp4")
        video.export(audio_path, format="wav")
        
        # Transcribe audio using speechToTextUtilities
        stt_util = speechToTextUtilities(Model.AzureOpenAI)
        transcription = stt_util.transcribe_with_timestamps(audio_path)
        
        return transcription
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error: {e}")
