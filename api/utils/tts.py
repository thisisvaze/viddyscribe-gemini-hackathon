import google.cloud.texttospeech as tts
import re
import logging
 
from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, TextClip
from google.api_core.exceptions import ResourceExhausted
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
import datetime
import time
import os
import requests
import glob
import asyncio
if __name__ != "__main__":
    from api.utils.llm_instructions import instructions, instructions_silent_period
    from api.utils.gemini import get_info_from_video 
# Load environment variables from .env file
load_dotenv()


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


import os

def get_voice_name(voice_model: str):
    if voice_model == "Azure":
        return "en-US-NovaMultilingualNeural"
    elif voice_model == "Google":
        return "en-US-Journey-O"
    elif voice_model == "ElevenLabs":
        return "kPzsL2i3teMYv0FxEYQ6"
    else:
        raise ValueError(f"Unsupported voice model: {voice_model}")


def text_to_wav_elevenlabs( voice_id: str, text: str, filename: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Content-Type": "application/json",
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }
    data = {
        "text": text,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        with open(filename, "wb") as out:
            out.write(response.content)
            print(f'Generated speech saved to "{filename}"')
    else:
        print(f"Error: {response.status_code}, {response.text}")
        raise Exception(f"Failed to generate speech: {response.text}")


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

async def get_silent_periods_util(video_path):
    response_silent_periods = await get_info_from_video(video_path, instructions_silent_period)
    return response_silent_periods


async def get_audio_desc_util(video_path):
    response_audio_desc = await get_info_from_video(video_path, instructions)
    return response_audio_desc

async def tts_utility(model_name, text, filename):
    voice = get_voice_name(model_name)
    if model_name == "Azure":
        return text_to_wav_azure( voice, text, filename)
    elif model_name == "Google":
        return text_to_wav( voice, text, filename)
    elif model_name == "ElevenLabs":
        return text_to_wav_elevenlabs( voice, text, filename)
    

async def generate_wav_files_from_response(response_body: dict, model_name: str):
    description = response_body["description"]
    # Updated regex pattern to handle both M:SS.sss and MM:SS.sss formats
    pattern = re.compile(r'\[(\d{1,2}:\d{2}\.\d{3})\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Found matches: {matches}")

    # Trim to the first 20 descriptions if there are more than 20
    # if len(matches) > 10:
    #     matches = matches[:10]
    #     logging.info("Trimmed matches to the first 20 descriptions.")

    if not matches:
        logging.error("No matches found in the description.")
        return []

    timestamp_ranges = []

    for timestamp, text in matches:
        start_time = timestamp
        filename = f"{start_time.replace(':', '-')}.wav"
        logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        
        try:
            await tts_utility(model_name, text, filename)
        except Exception as e:
            logging.error(f"Error generating WAV file: {e}")
            raise

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
        end_time = (datetime.datetime.strptime(start_time, "%M:%S.%f") + datetime.timedelta(seconds=duration)).strftime("%M-%S.%f")[:-3]
        new_filename = f"{start_time.replace(':', '-')}_to_{end_time}.wav"
        os.rename(filename, new_filename)
        logging.info(f"Generated speech saved to \"{new_filename}\"")

        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    logging.info(f"Generated timestamp ranges: {timestamp_ranges}")
    return timestamp_ranges


async def create_final_video(video_path: str, response_body: dict, output_path: str, voice_model):
    response_audio_timestamps = await generate_wav_files_from_response(response_body, voice_model)
    # Ensure response_audio_timestamps is generated
    if not response_audio_timestamps:
        logging.error("Failed to generate response audio timestamps")
        raise ValueError("Failed to generate response audio timestamps")

    try:
        video = VideoFileClip(video_path)
    except OSError as e:
        print(f"Error loading video file {video_path}: {e}")
        raise ValueError(f"Error loading video file {video_path}: {e}")

    
    description = response_body["description"]
    logging.info(f"Description: {description}")
    # Updated regex pattern to handle both M:SS.sss and MM:SS.sss formats
    pattern = re.compile(r'\[(\d{1,2}:\d{2}\.\d{3})\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Matches: {matches}")

    silent_periods = response_body["silent_periods"]
    logging.info(f"Silent periods: {silent_periods}")
    no_speech_pattern = re.compile(r'\[(\d{1,2}:\d{2}\.\d{3})\] - \[(\d{1,2}:\d{2}\.\d{3})\]\s*')
    no_speech_matches = no_speech_pattern.findall(silent_periods)

    no_speech_periods = []
    for start, end in no_speech_matches:
        start_parts = start.split(':')
        end_parts = end.split(':')
        start_seconds = int(start_parts[0]) * 60 + float(start_parts[1])
        end_seconds = int(end_parts[0]) * 60 + float(end_parts[1])
        no_speech_periods.append((start_seconds, end_seconds))

    

    clips = []
    last_end = 0
    time_offset = 0
    added_timestamps = set() 


    for i, (start_timestamp, text) in enumerate(matches):
        ts_parts = start_timestamp.split(':')
        ts_seconds = int(ts_parts[0]) * 60 + float(ts_parts[1])

        audio_filename = f"{start_timestamp.replace(':', '-')}_to_*.wav"
        audio_files = glob.glob(audio_filename)
        if not audio_files:
            raise FileNotFoundError(f"Audio file matching {audio_filename} not found")
        audio_clip = AudioFileClip(audio_files[0])

        insertion_time = None
        still_frame_time = None
        for start, end in no_speech_periods:
            if end >= ts_seconds:
                insertion_time = start
                if end - start <= audio_clip.duration:  # Check if no_speech_period is not greater than audio_clip time
                    still_frame_time = end
                break

        if insertion_time is None:
            offset = 0.1  # Small offset to ensure still_frame_time is within video duration
            insertion_time = video.duration - offset
            still_frame_time = video.duration - offset
            print(f"Warning: No silent period found for audio at {start_timestamp}. Inserting at the end: {insertion_time}")

        if insertion_time > last_end:
            segment = video.subclip(last_end, insertion_time)
            clips.append(segment)

        if still_frame_time is not None:
            still_frame = video.get_frame(still_frame_time)
            still_clip = ImageClip(still_frame).set_duration(audio_clip.duration)
            still_clip = still_clip.set_audio(audio_clip)
            clips.append(still_clip)
        else:
            audio_clip = audio_clip.set_start(insertion_time)
            video_segment = video.subclip(insertion_time, insertion_time + audio_clip.duration)
            combined_audio = CompositeAudioClip([video_segment.audio, audio_clip])
            video_segment = video_segment.set_audio(combined_audio)
            clips.append(video_segment)
            
        added_timestamps.add(start_timestamp) 

        last_end = still_frame_time if still_frame_time is not None else insertion_time + audio_clip.duration

        time_offset += audio_clip.duration

    if last_end < video.duration:
        final_segment = video.subclip(last_end)
        clips.append(final_segment)

    final_clip = concatenate_videoclips(clips)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    print(f"Final video created successfully. Duration: {final_clip.duration} seconds")





async def run_final(video_path):
    # Output path for the final video
    output_path = "temp/output_video.mp4"

    # Get audio description and silent periods
    response_audio_desc = await get_audio_desc_util(video_path)
    response_silent_periods = await get_silent_periods_util(video_path)

    response_body = {
        "description": response_audio_desc["description"],
        "silent_periods": response_silent_periods["description"]
    }
    # test_response_body = {'description': '[00:00.000] Four men stand on a stage behind a table with a green front.\n[00:02.880] A computer screen shows data about a compressed file.\n[00:07.760] A man in a suit in the audience raises his hand.\n[00:10.000] The man in the audience speaks into a microphone. \n[00:15.360] The man on stage types on a laptop. A large screen displays the laptop screen. \n', 
    #                  'silent_periods': '[00:15.283] - [00:15.966] \n'}

    try:
        clip = VideoFileClip(video_path)
        logging.info(f"Video loaded successfully. Duration: {clip.duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")

    # # Call the function
    await create_final_video(video_path, response_body, output_path, "ElevenLabs")

    
if __name__ == "__main__":
    # Path to a sample video file
    video_path = "temp/inp_new_test.mp4"
    asyncio.run(run_final())
        
    