import os
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks,Request, Header, Depends, WebSocket, WebSocketDisconnect, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
from moviepy.editor import VideoFileClip
from api.utils.gemini import VertexAIUtility  
from api.utils.text_to_speech import main_function
from api.utils.llm_instructions import instructions_chain_1, instructions_chain_2, instructions_silent_period
import uvicorn
import shutil
import asyncio
import time
import json
import subprocess
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

class VideoRequest(BaseModel):
    add_bg_music: Optional[bool] = False

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


# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.mount("/static", StaticFiles(directory="static"), name="static")


active_connections = {}
# Store background tasks
background_tasks_dict = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        del active_connections[client_id]


@app.post("/api/cancel_video")
async def cancel_video(client_id: str = Header(..., alias="client_id")):
    if client_id in background_tasks_dict:
        task = background_tasks_dict[client_id]
        if task:
            task.cancel()  # Request cancellation
            try:
                await asyncio.wait_for(task, timeout=1)  # Wait for the task to be cancelled
            except asyncio.CancelledError:
                logging.info(f"Task for client {client_id} was cancelled successfully.")
            except asyncio.TimeoutError:
                logging.warning(f"Task for client {client_id} did not cancel in time.")
            except Exception as e:
                logging.error(f"Error while cancelling task for client {client_id}: {e}")
            finally:
                del background_tasks_dict[client_id]
        else:
            logging.error(f"Task for client {client_id} is None")
            raise HTTPException(status_code=500, detail="Task is None")
        return JSONResponse({"status": "cancelled"})
    else:
        logging.error(f"No active task found for client {client_id}")
        raise HTTPException(status_code=404, detail="No active task found for this client")

@app.get("/api/video_status")
async def video_status(path: str):
    try:
        if os.path.exists(path):
            return {"status": "completed"}
        elif os.path.exists(path.replace("_output.mp4", ".mp4")):
            return {"status": "processing"}
        else: 
            return {"status": "processing"}  # Change "error" to "processing" to avoid false negatives
    except Exception as e:
        logging.error(f"Error checking video status: {e}")
        return {"status": "error", "message": str(e)}
    
    from fastapi import Request  # Add this import
@app.post("/api/create_video")
async def generate_endpoint(
    request: Request,  # Add this parameter
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    add_bg_music: Optional[bool] = Form(False),
    client_id: str = Form(...),  # Change from Header to Form
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    logging.info(f"Received file: {file.filename}")
    logging.info(f"Received add_bg_music: {add_bg_music}")
    logging.info(f"Received client_id: {client_id}")

    # Log the headers and form data for debugging
    logging.info(f"Headers: {dict(request.headers)}")
    logging.info(f"Form data: {await request.form()}")

    if credentials.credentials != os.getenv("VIDDYSCRIBE_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API Key")

    # Check file extension
    if not file.filename.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only MP4 files are supported")

    # Check file size
    file_size = await file.read()
    if len(file_size) > 7 * 1024 * 1024:  # 7MB
        raise HTTPException(status_code=400, detail="File size exceeds 7MB limit")
    await file.seek(0)  # Reset file pointer after reading

    start_time = time.time()
    timestamp = int(start_time)  # Get the current timestamp
    video_path = f"temp/{timestamp}_{file.filename}"
    output_path = f"/home/azureuser/viddyscribe-gemini-hackathon/static/videos/{timestamp}_{file.filename.split('.')[0]}_output.mp4"
    os.makedirs("temp", exist_ok=True)
    os.makedirs("/home/azureuser/viddyscribe-gemini-hackathon/static/videos", exist_ok=True)

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logging.info(f"File saved to {video_path}")

        # Check video duration
        video = VideoFileClip(video_path)
        if video.duration > 120:  # 2 minutes
            raise HTTPException(status_code=400, detail="Video duration exceeds 2 minutes limit")

        # Add the video processing task to background tasks
        task = background_tasks.add_task(process_video, video_path, output_path, client_id, add_bg_music)
        background_tasks_dict[client_id] = task

        logging.info(f"Video processing started for {video_path}")
        return JSONResponse({"status": "processing", "output_path": output_path})

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {e}")
    
async def process_video(video_path: str, output_path: str, client_id: str, add_bg_music: bool):
    try:
        await asyncio.wait_for(main_function(video_path, output_path, add_bg_music), timeout=600)
        logging.info(f"Video processing completed for {video_path}")
        if client_id in active_connections:
            message = json.dumps({"status": "completed", "output_path": output_path})
            await active_connections[client_id].send_text(message)
            logging.info(f"Sent 'completed' message to client {client_id}")
        else:
            logging.error(f"Client {client_id} not found in active connections")
    except asyncio.TimeoutError:
        logging.error("Video processing timed out")
    except asyncio.CancelledError:
        logging.info(f"Video processing cancelled for {video_path}")
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
        # Remove task from dictionary
        if client_id in background_tasks_dict:
            del background_tasks_dict[client_id]


@app.get("/api/download")
async def download_file(path: str):
    # Find the index of "static/videos/" in the provided path
    start_index = path.find("static/videos/")
    if start_index == -1:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Trim the path to start from "static/videos/"
    trimmed_path = path[start_index:]

    if not os.path.exists(trimmed_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(trimmed_path)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
	logging.error(f"{request}: {exc_str}")
	content = {'status_code': 10422, 'message': exc_str, 'data': None}
	return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)