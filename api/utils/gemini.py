import base64
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from fastapi import UploadFile, File  # Import FastAPI components
import time 
import warnings
from moviepy.editor import VideoFileClip
import os
import aiofiles  # Import aiofiles for async file operations

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")



class VertexAIUtility():
    def __init__(self):
        vertexai.init(project="planar-abbey-418313", location="us-central1")
        self.proModel = GenerativeModel(
                "gemini-1.5-pro-001",
            )
        self.flashModel = GenerativeModel(
                "gemini-1.5-flash-001",
            )
        pass

    def load_video(self, file_path):
        # Load the video file synchronously
        with open(file_path, "rb") as f:
            video_data = f.read()
        video1 = Part.from_data(
            mime_type="video/mp4",
            data=video_data
        )
        return video1
    
    def validate_video(self, file_path):
        try:
            clip = VideoFileClip(file_path)
            duration = clip.duration
            clip.close()
            return duration > 0
        except Exception as e:
            print(f"Error loading video: {e}")
            return False
                  
    
    def get_info_from_video(self, video1, inst):
        generation_config = {
            "max_output_tokens": 8192,
            "temperature": 0.7,
            "top_p": 0.95,
        }
        safety_settings = {
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

        start_time = time.time()  # Start time measurement

        # Generate content and handle the generator
        responses = self.proModel.generate_content(
            [video1, inst + ". Here is the video."],
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
        print({"Gemini response": result})

        return {"description": result}


    def gemini_llm(self, prompt, inst):
        generation_config = {
            "max_output_tokens": 8192,
            "temperature": 0.7,
            "top_p": 0.95,
        }
        safety_settings = {
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

        start_time = time.time()  # Start time measurement

        # Generate content and handle the generator
        responses = self.flashModel.generate_content(
            [inst + prompt],
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
        print({"Gemini response": result})

        return {"description": result}

# Add a main function to test the get_info_from_video function
if __name__ == "__main__":
    from llm_instructions import instructions

    file_path = "./temp/inp_new_test.mp4"  # Replace with your video file path
    inst = instructions  # Replace with your instruction

    # Run the function synchronously
    VertexAIUtility().get_info_from_video(file_path, inst)