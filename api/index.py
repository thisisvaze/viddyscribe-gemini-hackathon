import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
from moviepy.editor import VideoFileClip
from api.utils.gemini import get_info_from_video  
from api.utils.tts import create_final_video, run_final
from api.utils.speech_to_text import speechToTextUtilities, Model
from api.utils.llm_instructions import instructions, instructions_silent_period
import uvicorn
import shutil
import asyncio
import time
import subprocess
from fastapi.staticfiles import StaticFiles
import os

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the full path to the gckey.json file
gckey_path = os.path.join(script_dir, "gckey.json")

# Set the environment variable for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gckey_path



security = HTTPBearer()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

async def get_silent_periods_util(video_path):
    response_silent_periods = await get_info_from_video(video_path, instructions_silent_period)
    return response_silent_periods

async def get_audio_desc_util(video_path):
    response_audio_desc = await get_info_from_video(video_path, instructions)
    return response_audio_desc

@app.get("/api/video_status")
async def video_status(path: str):
    if os.path.exists(path):
        return {"status": "completed"}
    elif os.path.exists(path.replace("_output.mp4", ".mp4")):
        return {"status": "processing"}
    else: 
        return {"status": "error"}
    
async def main(video_path, output_path):
    try:
        clip = VideoFileClip(video_path)
        logging.info(f"Video loaded successfully. Duration: {clip.duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading video: {e}")
    response_audio_desc = await get_audio_desc_util(video_path)
    response_silent_periods = await get_silent_periods_util(video_path)

    if not response_audio_desc or not response_silent_periods:
        logging.error("Failed to retrieve audio description or silent periods")
        raise ValueError("Failed to retrieve audio description or silent periods")
    
    response_body = {
        "description": response_audio_desc["description"],
        "silent_periods": response_silent_periods["description"]
    }

    await create_final_video(video_path, response_body, output_path, "Azure")

@app.post("/api/create_video")
async def generate_endpoint(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if credentials.credentials != os.getenv("VIDDYSCRIBE_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API Key")

    start_time = time.time()
    video_path = f"temp/{file.filename}"
    output_path = f"static/videos/{file.filename.split('.')[0]}_output.mp4"
    os.makedirs("temp", exist_ok=True)
    os.makedirs("static/videos", exist_ok=True)

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logging.info(f"File saved to {video_path}")

        # Add the video processing task to background tasks
        background_tasks.add_task(process_video, video_path, output_path)

        logging.info(f"Video processing started for {video_path}")
        return JSONResponse({"status": "processing", "output_path": output_path})

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {e}")


async def process_video(video_path: str, output_path: str):
    try:
        await asyncio.wait_for(run_final(video_path, output_path), timeout=300)
        logging.info(f"Video processing completed for {video_path}")
    except asyncio.TimeoutError:
        logging.error("Video processing timed out")
    except Exception as e:
        logging.error(f"Error during video processing: {e}")
    finally:
        # Cleanup temp directory
        temp_dir = "temp"
        # Delete all audio files in temp directory
        for filename in os.listdir(temp_dir):
            if filename.endswith(('.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a')):
                file_path = os.path.join(temp_dir, filename)
                try:
                    os.unlink(file_path)
                    logging.info(f"Deleted audio file {file_path}")
                except Exception as e:
                    logging.error(f"Failed to delete audio file {file_path}. Reason: {e}")


@app.get("/api/download")
async def download_file(path: str):
    file_path = os.path.join("static", path)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type='application/octet-stream', filename=os.path.basename(file_path))
    else:
        logging.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")
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
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {e}")

# @app.post("/api/get_audio_desc")
# async def get_audio_desc(file: UploadFile = File(...)):
#     video_path = f"temp/{file.filename}"
#     try:
#         os.makedirs("temp", exist_ok=True)
#         with open(video_path, "wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)
        
#         return await get_audio_desc_util(video_path)
#     except Exception as e:
#         logging.error(f"Unexpected error: {e}")
#         raise HTTPException(status_code=500, detail=f"Error processing video: {e}")

# @app.post("/api/whisper_transcription")
# async def whisper_transcription(file: UploadFile = File(...)):
#     video_path = f"temp/{file.filename}"
#     audio_path = f"temp/{file.filename.split('.')[0]}.wav"
    
#     try:
#         os.makedirs("temp", exist_ok=True)
#         with open(video_path, "wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)
        
#         video = AudioSegment.from_file(video_path, format="mp4")
#         video.export(audio_path, format="wav")
        
#         stt_util = speechToTextUtilities(Model.AzureOpenAI)
#         transcription = stt_util.transcribe_with_timestamps(audio_path)
        
#         return transcription
#     except Exception as e:
#         logging.error(f"Unexpected error: {e}")
#         raise HTTPException(status_code=500, detail=f"Error: {e}")

def main():
    try:
        uvicorn.run(
            "main:app", 
            host="0.0.0.0", 
            port=8000, 
            log_level="info", 
            reload=True,
            ssl_certfile="/etc/letsencrypt/live/viddyscribe.thisisvaze.com/fullchain.pem",
            ssl_keyfile="/etc/letsencrypt/live/viddyscribe.thisisvaze.com/privkey.pem",
            limit_concurrency=100,  # Adjust as needed
            limit_max_requests=1000  # Adjust as needed
        )
    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        raise

def check_ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("ffmpeg is installed.")
    except subprocess.CalledProcessError:
        logging.error("ffmpeg is not installed.")
        raise HTTPException(status_code=500, detail="ffmpeg is not installed.")
    
if __name__ == "__main__":
    main()