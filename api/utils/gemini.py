import base64
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from fastapi import UploadFile, File  # Import FastAPI components
import time 
import warnings

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")


async def get_info_from_video(file_path, inst):
    # Load the video file
    with open(file_path, "rb") as f:
        video_data = f.read()
    video1 = Part.from_data(
        mime_type="video/mp4",
        data=video_data
    )

    vertexai.init(project="planar-abbey-418313", location="us-central1")
    model = GenerativeModel(
        "gemini-1.5-pro-001",
    )
    generation_config = {
        "max_output_tokens": 8192,
        "temperature": 0.7,
        "top_p": 0.95,
    }
    safety_settings = {
        generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }

    start_time = time.time()  # Start time measurement

    responses = model.generate_content(
        [video1, inst],
        generation_config=generation_config,
        safety_settings=safety_settings,
        stream=True,
    )

    result = ""
    for response in responses:
        result += response.text

    end_time = time.time()  # End time measurement
    time_taken = end_time - start_time  # Calculate time taken
    print(f"Time taken for response: {time_taken} seconds")  # Print time taken
    print({"description": result})

    return {"description": result}