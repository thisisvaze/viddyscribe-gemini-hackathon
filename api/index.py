import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header, Depends, WebSocket, WebSocketDisconnect
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
import subprocess
from fastapi.staticfiles import StaticFiles

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

# Store active WebSocket connections
active_connections = {}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        del active_connections[client_id]

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
    
@app.post("/api/create_video")
async def generate_endpoint(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    credentials: HTTPAuthorizationCredentials = Depends(security),
    client_id: str = Header(None)
):
    if credentials.credentials != os.getenv("VIDDYSCRIBE_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API Key")

    start_time = time.time()
    timestamp = int(start_time)  # Get the current timestamp
    video_path = f"temp/{timestamp}_{file.filename}"
    output_path = f"static/videos/{timestamp}_{file.filename.split('.')[0]}_output.mp4"
    os.makedirs("temp", exist_ok=True)
    os.makedirs("static/videos", exist_ok=True)

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logging.info(f"File saved to {video_path}")

        # Add the video processing task to background tasks
        background_tasks.add_task(process_video, video_path, output_path, client_id)

        logging.info(f"Video processing started for {video_path}")
        return JSONResponse({"status": "processing", "output_path": output_path})

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {e}")
    

async def process_video(video_path: str, output_path: str, client_id: str):
    try:
        await asyncio.wait_for(main_function(video_path, output_path), timeout=600)
        logging.info(f"Video processing completed for {video_path}")
        if client_id in active_connections:
            await active_connections[client_id].send_text("completed")
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