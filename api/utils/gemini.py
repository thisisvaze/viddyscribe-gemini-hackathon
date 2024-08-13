import os
import json
import subprocess
import time
import base64
from moviepy.editor import VideoFileClip
import warnings
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import vertexai.preview.generative_models as generative_models
from google.oauth2 import service_account
import google.auth.transport.requests


# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

class VertexAIUtility():
    def __init__(self):
        vertexai.init(project="viddyscribe", location="us-east4")
        #vertexai.init(project="planar-abbey-418313", location="us-central1")  # Initialize here
        self.proModel = GenerativeModel(
            "gemini-1.5-pro-001",
        )
        self.flashModel = GenerativeModel(
            "gemini-1.5-flash-001",
        )
        pass

    def get_access_token(self):
        credentials = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token

    def load_video(self, file_path):
        #vertexai.init(project="planar-abbey-418313", location="us-central1")  # Initialize here
        # Load the video file synchronously
        with open(file_path, "rb") as f:
            video_data = f.read()
        video1 = Part.from_data(
            mime_type="video/mp4",
            data=video_data
        )
        return video1
    
    def load_video_b64(self, file_path):
        # Load the video file synchronously
        with open(file_path, "rb") as f:
            video_data = f.read()
        encoded_video_data = base64.b64encode(video_data).decode('utf-8')
        return encoded_video_data  # Return the base64 encoded video data

    def validate_video(self, file_path):
        #vertexai.init(project="planar-abbey-418313", location="us-central1")  # Initialize here
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
    
    def get_info_from_video_curl(self, file_path, inst):
        # Get the base64 encoded video data
        encoded_video_data = self.load_video_b64(file_path)  # Use load_video_b64 to get base64 encoded data
        # Prepare the JSON payload
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "video/mp4",
                                "data": encoded_video_data  # Use the base64 encoded video data
                            }
                        },
                        {
                            "text": f"{inst}. Here is the video."
                        }
                    ]
                }
            ]
        }

        # Write the payload to a JSON file
        with open('request.json', 'w') as json_file:
            json.dump(payload, json_file)

        # Obtain the access token using the service account key file
        access_token = self.get_access_token()

        # Prepare the curl command
        curl_command = [
            "curl",
            "-X", "POST",
            "-H", f"Authorization: Bearer {access_token}",  # Use the access token
            "-H", "Content-Type: application/json",
            "https://us-central1-aiplatform.googleapis.com/v1/projects/viddyscribe/locations/us-central1/publishers/google/models/gemini-1.5-pro-001:streamGenerateContent",
            "-d", "@request.json"  # Use the JSON file as the data source
        ]

        start_time = time.time()  # Start time measurement

        # Execute the curl command
        result = subprocess.run(curl_command, capture_output=True, text=True)
        response = result.stdout

        end_time = time.time()  # End time measurement
        time_taken = end_time - start_time  # Calculate time taken
        print(f"Time taken for response: {time_taken} seconds")  # Print time taken
        print({"Gemini response": response})

        return {"description": response}

    def gemini_llm_curl(self, prompt, inst):
        # Obtain the access token using the service account key file
        access_token = self.get_access_token()

        # Prepare the curl command
        curl_command = [
            "curl",
            "-X", "POST",
            "-H", f"Authorization: Bearer {access_token}",  # Use the access token
            "-H", "Content-Type: application/json",
            "https://us-central1-aiplatform.googleapis.com/v1/projects/viddyscribe/locations/us-central1/publishers/google/models/gemini-1.5-flash-001:streamGenerateContent",
            "-d", json.dumps({
                "contents": {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"{inst} {prompt}"
                        }
                    ]
                }
            })
        ]

        start_time = time.time()  # Start time measurement

        # Execute the curl command
        result = subprocess.run(curl_command, capture_output=True, text=True)
        response = result.stdout

        end_time = time.time()  # End time measurement
        time_taken = end_time - start_time  # Calculate time taken
        print(f"Time taken for response: {time_taken} seconds")  # Print time taken
        print({"Gemini response": response})

        return {"description": response}

# Add a main function to test the get_info_from_video function
if __name__ == "__main__":
    from llm_instructions import instructions

    file_path = "./temp/inp_new_test.mp4"  # Replace with your video file path
    inst = instructions  # Replace with your instruction

    # Run the function synchronously
    VertexAIUtility().get_info_from_video(file_path, inst)