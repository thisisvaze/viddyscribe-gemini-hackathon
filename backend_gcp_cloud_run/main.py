from flask import Flask, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import os
import shutil
from google.cloud import storage
import datetime
from datetime import timedelta
import logging
import asyncio
from util.Constants import BUCKET_NAME
from util.gcs_bucket import download_from_gcs, download_multiple_from_gcs, upload_to_gcs, get_storage_client
from util.text_to_speech import main_function
import json
from google.oauth2 import service_account
processing_status = {}

storage_client = get_storage_client()

class VideoProcessRequest:
    def __init__(self, video_path: str, add_bg_music: str):
        self.video_path = video_path
        self.add_bg_music = add_bg_music

app = Flask(__name__)

# Add this configuration to increase the maximum content length
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB




VIDDYSCRIBE_API_KEY = os.getenv("VIDDYSCRIBE_API_KEY")

signed_urls = {}

# Add CORS middleware
from flask_cors import CORS
CORS(app, resources={r"/*": {"origins": "*"}})

def verify_api_key():
    api_key = request.headers.get("Authorization")
    if not api_key or api_key != f"Bearer {VIDDYSCRIBE_API_KEY}":
        return jsonify({"detail": "Invalid API Key"}), 403


from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

@app.route("/upload_video", methods=["POST"])
def upload_video():
    error_response = verify_api_key()
    if error_response:
        return error_response

    try:
        add_bg_music = True if request.form.get('add_bg_music') == "true" else False
        print("Add bg music:"+str(add_bg_music))
        file = request.files['file']
        filename = secure_filename(file.filename)
        file_location = f"/tmp/{filename}"
        file.save(file_location)
        
        gcs_url = upload_to_gcs(BUCKET_NAME, file_location, filename)

         # Clean up the temporary file
        os.remove(file_location)

        output_video_name = os.path.splitext(filename)[0] + "_output.mp4"
        processing_status[output_video_name] = "Processing video... This may take 4-10 minutes. Keep this tab open."

        # Schedule the task in a separate thread
        executor.submit(asyncio.run, process_video_task(gcs_url, add_bg_music, output_video_name))
        
        return jsonify({"status": "processing", "gcs_url": gcs_url, "output_video_name": output_video_name})
    except Exception as e:
        logging.error(f"Error in /upload_video: {e}")
        return jsonify({"detail": "Internal Server Error"}), 500


async def process_video_task(gcs_url: str, add_bg_music: str, output_video_name: str):
    try:
        logging.info(f"Starting to process video: {gcs_url}")
        request = VideoProcessRequest(video_path=gcs_url, add_bg_music=add_bg_music)
        result = await process_video(request)
        
        if not isinstance(result, dict) or 'status' not in result:
            raise ValueError("Invalid result format from process_video")

        if result['status'] == 'error':
            logging.error(f"Error processing video: {result.get('message', 'Unknown error')}")
            processing_status[output_video_name] = "Error processing video"
            return

        if 'output_url' not in result:
            logging.error("No output_url in result")
            processing_status[output_video_name] = "Error processing video"
            return

        processed_video_filename = os.path.basename(result["output_url"])
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(processed_video_filename)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="GET"
        )
        
        signed_urls[processed_video_filename] = signed_url
        processing_status[output_video_name] = "Processing completed"
        logging.info(f"Video processing completed: {output_video_name}")
        
    except Exception as e:
        logging.error(f"Error in process_video_task: {str(e)}")
        processing_status[output_video_name] = "Error processing video"

@app.route("/start_processing", methods=["POST"])
def start_processing():
    error_response = verify_api_key()
    if error_response:
        return error_response

    try:
        data = request.json
        filename = data.get('filename')
        add_bg_music = data.get('add_bg_music', False)

        if not filename:
            return jsonify({"error": "Filename is required"}), 400

        # Remove the gs:// prefix if it exists
        gcs_url = filename if not filename.startswith('gs://') else filename[5:]
        output_video_name = os.path.splitext(filename)[0] + "_output.mp4"
        processing_status[output_video_name] = "Processing video... This may take 4-10 minutes. Keep this tab open."

        # Schedule the task in a separate thread
        executor.submit(asyncio.run, process_video_task(gcs_url, add_bg_music, output_video_name))
        
        return jsonify({"status": "processing", "output_video_name": output_video_name})
    except Exception as e:
        logging.error(f"Error in /start_processing: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
    
    
@app.route("/get_upload_url", methods=["POST"])
def get_upload_url():
    error_response = verify_api_key()
    if error_response:
        return error_response

    try:
        data = request.json
        if not data:
            logging.error("No JSON data in request")
            return jsonify({"error": "No data provided"}), 400

        filename = data.get('filename')
        content_type = data.get('contentType')
        
        logging.info(f"Received request for upload URL. Filename: {filename}, Content-Type: {content_type}")
        
        if not filename or not content_type:
            logging.error(f"Missing filename or content_type. Filename: {filename}, Content-Type: {content_type}")
            return jsonify({"error": "Filename and content type are required"}), 400

        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)

        # Generate a signed URL for uploading
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT",
            content_type=content_type,
        )

        logging.info(f"Generated signed URL for {filename}")
        return jsonify({"upload_url": url})
    except Exception as e:
        logging.error(f"Error generating upload URL: {str(e)}")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@app.route("/update_status/<output_video_name>", methods=["GET"])
def update_status(output_video_name: str):
    status = processing_status.get(output_video_name, "Processing video. This may take 4-10 minutes. Keep this tab open.")
    return jsonify({"status": status})

@app.route("/process_video", methods=["POST"])
async def process_video(request):
    video_path = request.video_path

    if not video_path:
        return jsonify({"status": "error", "message": "video_path is required"}), 400

    try:
        result = await main_function(video_path, request.add_bg_music)
        if not isinstance(result, dict):
            raise ValueError("main_function did not return a dictionary")
        return result
    except Exception as e:
        logging.error(f"Error in process_video: {str(e)}")
        return {"status": "error", "message": str(e)}
    

@app.route("/download_sample_videos", methods=["GET"])
def download_sample_videos():
    bucket_name = BUCKET_NAME
    source_blob_names = ["sample_video1.mp4", "sample_video2.mp4"]
    ui_names = ["Battery", "Smoothie"]
    
    signed_urls = []
    bucket = storage_client.bucket(bucket_name)
    
    for blob_name, ui_name in zip(source_blob_names, ui_names):
        blob = bucket.blob(blob_name)
        try:
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=15),  # URL valid for 15 minutes
                method="GET"
            )
            signed_urls.append({"name": ui_name, "url": signed_url})
        except Exception as e:
            logging.error(f"Error generating signed URL for {blob_name}: {e}")
            return jsonify({"detail": f"Error generating signed URL for {blob_name}"}), 500
    
    return jsonify(signed_urls)

@app.route("/serve_video/<video_name>", methods=["GET"])
def serve_video(video_name: str):
    bucket_name = BUCKET_NAME
    bucket = storage_client.bucket(bucket_name)
    
    # Mapping of UI names to blob names
    video_mapping = {
        "Battery": "sample_video1.mp4",
        "Smoothie": "sample_video2.mp4"
    }
    
    blob_name = video_mapping.get(video_name)
    if not blob_name:
        return jsonify({"detail": "Video not found"}), 404
    
    blob = bucket.blob(blob_name)
    
    try:
        video_data = blob.download_as_bytes()
        return Response(video_data, mimetype="video/mp4")
    except Exception as e:
        logging.error(f"Error serving video {video_name}: {e}")
        return jsonify({"detail": f"Error serving video {video_name}"}), 500


@app.route("/download_video/<file_name>", methods=["GET"])
def download_video(file_name: str):
    try:
        # Retrieve the signed URL from the in-memory dictionary
        signed_url = signed_urls.get(file_name)
        if not signed_url:
            return jsonify({"detail": "File not found"}), 404
        
        return jsonify({"signed_url": signed_url})
    except Exception as e:
        logging.error(f"Error retrieving signed URL for {file_name}: {e}")
        return jsonify({"detail": "Error retrieving signed URL"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))