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
import asyncio
import glob
import re
import logging
from moviepy.editor import VideoFileClip
from api.utils.llm_instructions import instructions, instructions_silent_period
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



@app.get("/api/python")
def hello_world():
    return {"message": "Hello World"}


async def get_silent_periods_util(video_path):
    response_silent_periods = await get_info_from_video(video_path, instructions_silent_period)
    return response_silent_periods


async def get_audio_desc_util(video_path):
    response_audio_desc = await get_info_from_video(video_path, instructions)
    return response_audio_desc

async def main(video_path):
    output_path = "temp/output_video.mp4"
    # Get audio description and silent periods
    response_audio_desc = await get_audio_desc_util(video_path)
    response_silent_periods = await get_silent_periods_util(video_path)

    response_body = {
        "description": response_audio_desc["description"],
        "silent_periods": response_silent_periods["description"]
    }
    # test_response_body = {'description': '[00:00.000] Four men stand on a stage behind a table with a green front.\n[00:02.880] A computer screen shows data about a compressed file.\n[00:07.760] A man in a suit in the audience raises his hand.\n[00:10.000] The man in the audience speaks into a microphone. \n[00:15.360] The man on stage types on a laptop. A large screen displays the laptop screen. \n', 
    #                  'silent_periods': '[00:15.283] - [00:15.966] \n'}
    print("WOOHOO: "+str(response_body))

    try:
        clip = VideoFileClip(video_path)
        logging.info(f"Video loaded successfully. Duration: {clip.duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")

    # # Call the function
    await create_final_video(video_path, response_body, output_path, "Azure")

@app.post("/api/generate")
async def generate_endpoint(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    output_path = "temp/output_video.mp4"  # Ensure the output path is within the temp directory
    os.makedirs("temp", exist_ok=True)
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Verify the video file can be opened
    try:
        video = VideoFileClip(video_path)
        video.reader.close()
    except Exception as e:
        raise ValueError(f"Error reading video file: {e}")
    
    await main(video_path)

    # Ensure the file exists before returning the response
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Generated video not found")

    return FileResponse(output_path, filename="output_video.mp4")  # Serve the file

@app.post("/api/get_silent_periods")
async def get_silent_periods(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Await the coroutine to get the actual result
        response_silent_periods = await get_silent_periods_util(video_path)
        return response_silent_periods
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error processing video: {e}")


@app.post("/api/get_audio_desc")
async def get_audio_desc(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return await get_audio_desc_util(video_path)
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error processing video: {e}")


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
