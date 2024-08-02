from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from api.utils.gemini import get_info_from_video  
from api.utils.tts import generate_wav_files_from_response, create_final_video, run_final
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
import os
import time

# Set the environment variable for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "api/gckey.json"

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

    try:
        clip = VideoFileClip(video_path)
        logging.info(f"Video loaded successfully. Duration: {clip.duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")


    output_path = "temp/output_video.mp4"
    # Get audio description and silent periods
    response_audio_desc = await get_audio_desc_util(video_path)
    response_silent_periods = await get_silent_periods_util(video_path)

    if not response_audio_desc or not response_silent_periods:
        logging.error("Failed to retrieve audio description or silent periods")
        raise ValueError("Failed to retrieve audio description or silent periods")
    
    print(response_audio_desc)
    response_body = {
        "description": response_audio_desc["description"],
        "silent_periods": response_silent_periods["description"]
    }
    

    await create_final_video(video_path, response_body, output_path, "Azure")


@app.post("/api/generate")
async def generate_endpoint(file: UploadFile = File(...)):
    start_time = time.time()
    video_path = f"temp/{file.filename}"
    output_path = "temp/output_video.mp4"  # Ensure the output path is within the temp directory
    os.makedirs("temp", exist_ok=True)
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    logging.info(f"File saved to {video_path}")
    # Verify the video file can be opened
    try:
        video = VideoFileClip(video_path)
        video.reader.close()
        logging.info(f"Video file {video_path} opened successfully")
    except Exception as e:
        logging.error(f"Error reading video file: {e}")
        raise ValueError(f"Error reading video file: {e}")
    
    try:
        # Set a timeout for the main function
        await asyncio.wait_for(run_final(video_path), timeout=300)  # Timeout set to 120 seconds (2 minutes)
        logging.info(f"Main function completed for {video_path}")
    except asyncio.TimeoutError:
        logging.error("Request timed out")
        raise HTTPException(status_code=504, detail="Request timed out")

    # Ensure the file exists before returning the response
    if not os.path.exists(output_path):
        logging.error("Generated video not found")
        raise HTTPException(status_code=404, detail="Generated video not found")

    logging.info(f"Returning generated video path {output_path}")
    logging.info(f"Total time taken: {time.time() - start_time} seconds")
    return FileResponse(output_path, media_type='video/mp4', filename='output_video.mp4')

@app.post("/api/get_silent_periods")
async def get_silent_periods(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
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
        
        video = AudioSegment.from_file(video_path, format="mp4")
        video.export(audio_path, format="wav")
        
        stt_util = speechToTextUtilities(Model.AzureOpenAI)
        transcription = stt_util.transcribe_with_timestamps(audio_path)
        
        return transcription
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise ValueError(f"Error: {e}")