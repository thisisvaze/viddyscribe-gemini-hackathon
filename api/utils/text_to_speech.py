import google.cloud.texttospeech as tts
import re
import logging
from asyncio import Semaphore
from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, TextClip
from google.api_core.exceptions import ResourceExhausted
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
import azure.cognitiveservices.speech as speechsdk
import base64
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from fastapi import UploadFile, File  # Import FastAPI components
import time 
from api.audiogen.setup import MusicGenerator
import warnings
import datetime
import os
import requests
import asyncio
from elevenlabs.client import AsyncElevenLabs
from elevenlabs import save
import time
import os
import requests
import glob
import asyncio
from pydub import AudioSegment
from dotenv import load_dotenv
from api.utils.gemini import VertexAIUtility



# Load environment variables from .env file
load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the full path to the gckey.json file
gckey_path = os.path.join(script_dir, "gckey.json")

# Set the environment variable for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gckey_path


if __name__ != "__main__":
    from api.utils.llm_instructions import instructions_chain_1, instructions_chain_2, instructions_silent_period, instructions_timestamp_format
    from api.utils.gemini import VertexAIUtility 

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


import os

music_generator = MusicGenerator()

def get_voice_name(voice_model: str):
    if voice_model == "Azure":
        return "en-US-NovaMultilingualNeural"
    elif voice_model == "Google":
        return "en-US-Journey-O"
    elif voice_model == "ElevenLabs":
        return "kPzsL2i3teMYv0FxEYQ6"
        #return "pjcYQlDFKMbcOUp6F5GD"
    else:
        raise ValueError(f"Unsupported voice model: {voice_model}")
    

async def tts_utility(model_name, text, filename):
    voice = get_voice_name(model_name)
    if model_name == "Azure":
        return text_to_wav_azure( voice, text, filename)
    elif model_name == "Google":
        return text_to_wav( voice, text, filename)
    elif model_name == "ElevenLabs":
        return await text_to_wav_elevenlabs(voice, text, filename)  # Add await here


async def text_to_wav_elevenlabs(voice_id: str, text: str, filename: str):
    client = AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    
    audio_generator = await client.generate(
        text=text,
        voice=voice_id,
        model="eleven_turbo_v2_5"
    )
    # Open the file in binary write mode
    with open(filename, "wb") as f:
        async for chunk in audio_generator:
            f.write(chunk)
    print(f'Generated speech saved to "{filename}"')

async def generate_wav_files_from_response(response_body: dict, model_name: str):
    description = response_body["description"]
    logging.info(f"Description: {description}")  # Log the description to verify its format
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')  # Updated regex pattern
    matches = pattern.findall(description)

    if not matches:
        logging.error("No timestamps found in the description returned by gemini.")
        raise ValueError("Failed to generate response audio timestamps")


    timestamp_ranges = []

    tasks = []  # List to hold all the tasks
    semaphore = Semaphore(10)  # Limit to 10 concurrent tasks

    async def limited_tts_utility(model_name, text, filename):
        async with semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await tts_utility(model_name, text, filename)
                    break  # Exit the loop if successful
                except Exception as e:
                    logging.error(f"Error generating WAV file on attempt {attempt + 1} for text: '{text}' - {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)  # Wait before retrying
                    else:
                        raise

    for match in matches:
        timestamp, text = match  # Split the match to get timestamp and text
        start_time = timestamp.strip('[')
        filename = f"temp/{start_time.replace(':', '-')}.wav"  # Updated path to include temp folder
        logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        
        # Create a task for each text-to-speech generation
        tasks.append(limited_tts_utility(model_name, text, filename))

    # Run all tasks concurrently
    await asyncio.gather(*tasks)

    # Check if files are created and handle them
    for match in matches:
        timestamp, text = match  # Directly unpack the tuple
        start_time = timestamp.strip('[')
        filename = f"temp/{start_time.replace(':', '-')}.wav"  # Updated path to include temp folder
        logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        
        max_wait_time = 30
        wait_interval = 0.5
        elapsed_time = 0

        while (not os.path.exists(filename) or os.path.getsize(filename) == 0) and elapsed_time < max_wait_time:
            logging.info(f"Waiting for file {filename} to be created. Elapsed time: {elapsed_time}s")
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            logging.error(f"Failed to generate WAV file: {filename}")
            raise Exception(f"Failed to generate WAV file: {filename}")

        audio_clip = AudioFileClip(filename)
        duration = audio_clip.duration

        try:
            start_dt = datetime.datetime.strptime(start_time, "%M:%S.%f")
        except ValueError:
            start_dt = datetime.datetime.strptime(start_time, "%M:%S")

        end_time = (start_dt + datetime.timedelta(seconds=duration)).strftime("%M-%S.%f")[:-3]
        new_filename = f"temp/{start_time.replace(':', '-')}_to_{end_time}.wav"  # Updated path to include temp folder
        os.rename(filename, new_filename)
        logging.info(f"Generated speech saved to \"{new_filename}\"")

        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    logging.info(f"Generated timestamp ranges: {timestamp_ranges}")
    return timestamp_ranges

def text_to_wav(voice_name: str, text: str, filename: str):
    language_code = "-".join(voice_name.split("-")[:2])
    text_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code=language_code, name=voice_name
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)

    client = tts.TextToSpeechClient()
    try:
        response = client.synthesize_speech(
            input=text_input,
            voice=voice_params,
            audio_config=audio_config,
        )
    except ResourceExhausted as e:
        print(f"Resource exhausted: {e}")
        raise

    with open(filename, "wb") as out:
        out.write(response.audio_content)
        print(f'Generated speech saved to "{filename}"')
    
async def text_to_wav_azure(voice_name: str, text: str, filename: str):
    speech_config = speechsdk.SpeechConfig(subscription=os.environ.get('SPEECH_KEY'), region=os.environ.get('SPEECH_REGION'))
    audio_config = speechsdk.audio.AudioOutputConfig(filename=filename)
    speech_config.speech_synthesis_voice_name = voice_name

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    # Use the get method to retrieve the result
    result_future = speech_synthesizer.speak_text_async(text)
    speech_synthesis_result = result_future.get()  # Changed from await asyncio.wrap_future(result_future)

    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"Speech synthesized for text [{text}] and saved to {filename}")
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print(f"Speech synthesis canceled: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print(f"Error details: {cancellation_details.error_details}")
                print("Did you set the speech resource key and region values?")

def get_audio_desc_util(video_path):
    v = VertexAIUtility()
    
    # Validate the video before proceeding
    if not v.validate_video(video_path):
        print(f"Error: Video file '{video_path}' is invalid or corrupted.")
        return {"error": "Invalid video file"}

    # video = v.load_video(video_path)  # Use the load_video method from VertexAIUtility
    # response = v.get_info_from_video_curl(video, instructions_chain_1)
    # dynamic_instructions_chain_2 = instructions_chain_2.replace("[Insert the output from Prompt 1 here]", response["description"])
    # time.sleep(4)
    # video = v.load_video(video_path)
    # response_audio_desc = v.get_info_from_video_curl(video, dynamic_instructions_chain_2)
    response = v.get_info_from_video_curl(video_path, instructions_chain_1)
    dynamic_instructions_chain_2 = instructions_chain_2.replace("[Insert the output from Prompt 1 here]", response["description"])
    response_audio_desc = v.get_info_from_video_curl(video_path, dynamic_instructions_chain_2)
    reformmated_desc = v.gemini_llm(prompt =response_audio_desc["description"] , inst = instructions_timestamp_format)
    return reformmated_desc
 
def convert_mp4_to_wav(video_path):
    audio_path = f"{os.path.splitext(video_path)[0]}.wav"
    # Convert video to audio
    video = AudioSegment.from_file(video_path, format="mp4")
    video.export(audio_path, format="wav")
    
    return audio_path

async def main_function(video_path, output_path, add_bg_music):
    try:
        clip = VideoFileClip(video_path)
        video_duration = clip.duration
        logging.info(f"Video loaded successfully. Duration: {video_duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")
        return {"status": "error", "message": str(e)}
    
    # Get audio description
    response_audio_desc = get_audio_desc_util(video_path)
    if "error" in response_audio_desc:
        logging.error(f"Error in Gemini response: {response_audio_desc['error']}")
        return {"status": "error", "message": response_audio_desc["error"]}

    response_body = {
        "description": response_audio_desc["description"],
    }
    try:
        await create_final_video_v2(video_path, response_body, output_path, "ElevenLabs", add_bg_music)
    except ValueError as e:
        logging.error(f"Error during video processing: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logging.error(f"Unexpected error during video processing: {e}")
        return {"status": "error", "message": str(e)}
    
    return {"status": "success", "output_path": output_path}

async def create_final_video_v2(video_path: str, response_body: dict, output_path: str, model_name, add_bg_music : bool):

    original_videos_audio = convert_mp4_to_wav(video_path)
    # Load the audio file into an AudioFileClip object
    original_audio_clip = AudioFileClip(original_videos_audio)
    

    response_audio_timestamps = await generate_wav_files_from_response(response_body, model_name)
    if not response_audio_timestamps:
        logging.error("Failed to generate response audio timestamps")
        raise ValueError("Failed to generate response audio timestamps")

    try:
        video = VideoFileClip(video_path)
    except OSError as e:
        logging.error(f"Error loading video file {video_path}: {e}")
        raise ValueError(f"Error loading video file {video_path}: {e}")

    description = response_body["description"]
    logging.info(f"Description: {description}")
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Matches: {matches}")

    clips = []
    last_end = 0
    added_timestamps = set()

    for i, (start_timestamp, text) in enumerate(matches):
        ts_parts = start_timestamp.split(':')
        ts_start_seconds = int(ts_parts[0]) * 60 + float(ts_parts[1])

        audio_filename = f"temp/{start_timestamp.replace(':', '-')}_to_*.wav"
        audio_files = glob.glob(audio_filename)
        if not audio_files:
            raise FileNotFoundError(f"Audio file matching {audio_filename} not found")
        audio_clip = AudioFileClip(audio_files[0])
        
        # Log the duration of the audio clip
        logging.info(f"Audio clip duration for {start_timestamp}: {audio_clip.duration}")

        insertion_time = ts_start_seconds
        still_frame_time = ts_start_seconds
        logging.warning(f"Inserting audio description at: {start_timestamp}")

        if still_frame_time is not None:
            if still_frame_time == insertion_time:
                segment = video.subclip(last_end, still_frame_time)
                clips.append(segment)
        
        if still_frame_time is not None and insertion_time == still_frame_time:
            still_frame = video.get_frame(still_frame_time)
            still_clip = ImageClip(still_frame).set_duration(audio_clip.duration)
            still_clip = still_clip.set_audio(audio_clip)
            
            if ts_start_seconds == 0: 
                e_time = ts_start_seconds + 5  
            else:
                e_time = ts_start_seconds

            fade_duration = 0.5
            bg_fade_duration = 0.2
            vid_max_volume = original_audio_clip.max_volume()
            still_frame_volume = original_audio_clip.subclip(max(ts_start_seconds - 5, 0), e_time).max_volume()
            if add_bg_music:
                # Extract audio using ffmpeg
                temp_audio_path = "temp_audio.wav"
                subclip = original_audio_clip.subclip(max(ts_start_seconds - 5, 0), e_time)
                subclip.write_audiofile(temp_audio_path)
                subclip = AudioFileClip(temp_audio_path)
                
                music_path = music_generator.generate_music(
                    melody_path=subclip.filename,
                    descriptions=" ",
                    duration=int(audio_clip.duration)
                )

                # Volume alignment and transition
                generated_music_clip = AudioFileClip(music_path)
                generated_music_clip = generated_music_clip.volumex(vid_max_volume*0.5).audio_fadein(fade_duration).volumex(0.1).audio_fadeout(fade_duration).volumex(vid_max_volume*0.5)
    
                combined_audio_clips = [still_clip.audio.volumex(vid_max_volume), generated_music_clip.set_start(0)]
                #combine all audio together
                if ts_start_seconds + bg_fade_duration < original_audio_clip.duration:
                    faded_out_start_audio_original_track = original_audio_clip.subclip(ts_start_seconds, ts_start_seconds + bg_fade_duration).audio_fadeout(bg_fade_duration)
                    combined_audio_clips.append(faded_out_start_audio_original_track)

                    faded_in_end_audio_original_track = original_audio_clip.subclip(ts_start_seconds - bg_fade_duration, ts_start_seconds).audio_fadein(bg_fade_duration)
                    combined_audio_clips.append(faded_in_end_audio_original_track.set_start(ts_start_seconds + audio_clip.duration - bg_fade_duration))

                #combine all audio together with generated bg music
                combined_audio = CompositeAudioClip(combined_audio_clips)
                
            else:
                still_frame_volume = original_audio_clip.subclip(max(ts_start_seconds - 5, 0), e_time).max_volume()
                combined_audio_clips = [still_clip.audio.volumex(vid_max_volume)]
                #combine all audio together
                if ts_start_seconds + bg_fade_duration < original_audio_clip.duration:
                    faded_out_start_audio_original_track = original_audio_clip.subclip(ts_start_seconds, ts_start_seconds + bg_fade_duration).audio_fadeout(bg_fade_duration)
                    combined_audio_clips.append(faded_out_start_audio_original_track)

                    faded_in_end_audio_original_track = original_audio_clip.subclip(ts_start_seconds - bg_fade_duration, ts_start_seconds).audio_fadein(bg_fade_duration)
                    combined_audio_clips.append(faded_in_end_audio_original_track.set_start(audio_clip.duration - bg_fade_duration))

                combined_audio = CompositeAudioClip(combined_audio_clips)
                    
            still_clip = still_clip.set_audio(combined_audio)
            
            clips.append(still_clip)

        added_timestamps.add(start_timestamp)
        last_end = still_frame_time if still_frame_time is not None else insertion_time + audio_clip.duration

    if last_end < int(video.duration):
        final_segment_end = int(video.duration)
        final_segment = video.subclip(last_end, final_segment_end)
        clips.append(final_segment)

    final_clip = concatenate_videoclips(clips)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    logging.info(f"Final video created successfully. Duration: {final_clip.duration} seconds")
