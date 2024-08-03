from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from api.utils.gemini import get_info_from_video  
from api.utils.tts import generate_wav_files_from_response, create_final_video, run_final
from api.utils.speech_to_text import speechToTextUtilities, Model
from pydub import AudioSegment
from moviepy.editor import VideoFileClip
from api.utils.llm_instructions import instructions, instructions_silent_period
import os
import shutil
import asyncio
import logging
import time
from fastapi.staticfiles import StaticFiles

   
# Set the environment variable for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "api/gckey.json"

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
@app.post("/api/generate")
async def generate_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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


# @app.post("/api/generate")
# async def generate_endpoint(file: UploadFile = File(...)):
#        start_time = time.time()
#        video_path = f"temp/{file.filename}"
#        output_path = f"static/videos/{file.filename.split('.')[0]}_output.mp4"  # Save in static directory
#        os.makedirs("temp", exist_ok=True)
#        os.makedirs("static/videos", exist_ok=True)  # Ensure the static directory exists
       
#        try:
#            with open(video_path, "wb") as buffer:
#                shutil.copyfileobj(file.file, buffer)
#            logging.info(f"File saved to {video_path}")

#            video = VideoFileClip(video_path)
#            video.reader.close()
#            logging.info(f"Video file {video_path} opened successfully")
           
#            await asyncio.wait_for(run_final(video_path, output_path), timeout=300)
#            logging.info(f"Main function completed for {video_path}")

#            if not os.path.exists(output_path):
#                logging.error("Generated video not found")
#                raise HTTPException(status_code=404, detail="Generated video not found")

#            def iterfile():
#                with open(output_path, mode="rb") as file_like:
#                    yield from file_like

#            logging.info(f"Returning generated video path {output_path}")
#            logging.info(f"Total time taken: {time.time() - start_time} seconds")
#            return {"output_path": output_path}  # Return the output path

#        except asyncio.TimeoutError:
#            logging.error("Request timed out")
#            raise HTTPException(status_code=504, detail="Request timed out")
#        except Exception as e:
#            logging.error(f"Error processing video: {e}")
#            raise HTTPException(status_code=500, detail=f"Error processing video: {e}")
#        finally:
#            pass

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

@app.post("/api/get_audio_desc")
async def get_audio_desc(file: UploadFile = File(...)):
    video_path = f"temp/{file.filename}"
    try:
        os.makedirs("temp", exist_ok=True)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return await get_audio_desc_util(video_path)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {e}")

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
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e}")