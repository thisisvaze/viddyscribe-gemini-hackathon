import google.cloud.texttospeech as tts
import re
import logging

from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, TextClip
from google.api_core.exceptions import ResourceExhausted
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
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


if __name__ != "__main__":
    from api.utils.llm_instructions import instructions, instructions_silent_period
    from api.utils.gemini import get_info_from_video 
    from api.utils.speech_to_text import speechToTextUtilities 
    from api.utils.model_configs import Model
# Load environment variables from .env file
load_dotenv()

# Set the environment variable for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "api/gckey.json"


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
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Found matches: {matches}")

    if not matches:
        logging.error("No matches found in the description.")
        return []

    timestamp_ranges = []

    tasks = []  # List to hold all the tasks

    for timestamp, text in matches:
        start_time = timestamp
        filename = f"{start_time.replace(':', '-')}.wav"
        logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        
        # Create a task for each text-to-speech generation
        tasks.append(tts_utility(model_name, text, filename))

    # Run all tasks concurrently
    await asyncio.gather(*tasks)

    # Check if files are created and handle them
    for timestamp, text in matches:
        start_time = timestamp
        filename = f"{start_time.replace(':', '-')}.wav"
        
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
        new_filename = f"{start_time.replace(':', '-')}_to_{end_time}.wav"
        os.rename(filename, new_filename)
        logging.info(f"Generated speech saved to \"{new_filename}\"")

        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    logging.info(f"Generated timestamp ranges: {timestamp_ranges}")
    return timestamp_ranges

# def text_to_wav_elevenlabs( voice_id: str, text: str, filename: str):
#     url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
#     headers = {
#         "Content-Type": "application/json",
#         "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
#     }
#     data = {
#         "text": text,
#         "voice_settings": {
#             "stability": 0.5,
#             "similarity_boost": 0.75
#         }
#     }


#     response = requests.post(url, headers=headers, json=data)
#     if response.status_code == 200:
#         with open(filename, "wb") as out:
#             out.write(response.content)
#             print(f'Generated speech saved to "{filename}"')
#     else:
#         print(f"Error: {response.status_code}, {response.text}")
#         raise Exception(f"Failed to generate speech: {response.text}")


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
        return await text_to_wav_elevenlabs(voice, text, filename)  # Add await here
    

# async def generate_wav_files_from_response(response_body: dict, model_name: str):
#     description = response_body["description"]
#     # Updated regex pattern to handle M:SS, MM:SS, M:SS.sss, and MM:SS.sss formats
#     pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
#     matches = pattern.findall(description)
#     logging.info(f"Found matches: {matches}")

#     if not matches:
#         logging.error("No matches found in the description.")
#         return []

#     timestamp_ranges = []

#     for timestamp, text in matches:
#         start_time = timestamp
#         filename = f"{start_time.replace(':', '-')}.wav"
#         logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        
#         try:
#             await tts_utility(model_name, text, filename)
#         except Exception as e:
#             logging.error(f"Error generating WAV file for text '{text}' at timestamp '{start_time}': {e}")
#             raise

#         max_wait_time = 30
#         wait_interval = 0.5
#         elapsed_time = 0

#         while (not os.path.exists(filename) or os.path.getsize(filename) == 0) and elapsed_time < max_wait_time:
#             logging.info(f"Waiting for file {filename} to be created. Elapsed time: {elapsed_time}s")
#             await asyncio.sleep(wait_interval)
#             elapsed_time += wait_interval

#         if not os.path.exists(filename) or os.path.getsize(filename) == 0:
#             logging.error(f"Failed to generate WAV file: {filename}")
#             raise Exception(f"Failed to generate WAV file: {filename}")

#         audio_clip = AudioFileClip(filename)
#         duration = audio_clip.duration

#         # Handle different timestamp formats
#         try:
#             start_dt = datetime.datetime.strptime(start_time, "%M:%S.%f")
#         except ValueError:
#             start_dt = datetime.datetime.strptime(start_time, "%M:%S")

#         end_time = (start_dt + datetime.timedelta(seconds=duration)).strftime("%M-%S.%f")[:-3]
#         new_filename = f"{start_time.replace(':', '-')}_to_{end_time}.wav"
#         os.rename(filename, new_filename)
#         logging.info(f"Generated speech saved to \"{new_filename}\"")

#         timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

#     logging.info(f"Generated timestamp ranges: {timestamp_ranges}")
#     return timestamp_ranges


async def create_final_video(video_path: str, response_body: dict, output_path: str, model_name):
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

    silent_periods = response_body["silent_periods"]
    logging.info(f"Silent periods: {silent_periods}")
    no_speech_pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] - \[(\d{1,2}:\d{2}(?:\.\d{3})?)\]\s*')
    no_speech_matches = no_speech_pattern.findall(silent_periods)

    no_speech_periods = []
    for start, end in no_speech_matches:
        start_parts = start.split(':')
        end_parts = end.split(':')
        start_seconds = int(start_parts[0]) * 60 + float(start_parts[1])
        end_seconds = int(end_parts[0]) * 60 + float(end_parts[1])
        no_speech_periods.append((start_seconds, end_seconds))

    if not no_speech_periods or no_speech_periods[0][0] > 0:
        no_speech_periods.insert(0, (0, 0.1))

    clips = []
    last_end = 0
    added_timestamps = set()

    for i, (start_timestamp, text) in enumerate(matches):
        ts_parts = start_timestamp.split(':')
        ts_start_seconds = int(ts_parts[0]) * 60 + float(ts_parts[1])

        audio_filename = f"{start_timestamp.replace(':', '-')}_to_*.wav"
        audio_files = glob.glob(audio_filename)
        if not audio_files:
            raise FileNotFoundError(f"Audio file matching {audio_filename} not found")
        audio_clip = AudioFileClip(audio_files[0])

        insertion_time = None
        still_frame_time = None
        for silent_period_start, silent_period_end in no_speech_periods:
            if silent_period_start <= ts_start_seconds <= silent_period_end:
                if ts_start_seconds + audio_clip.duration <= silent_period_end:
                    insertion_time = ts_start_seconds
                    logging.info(f"Silent period covers entire audio at {start_timestamp}. No still frame needed, adding the clip here: {insertion_time}")
                else:
                    insertion_time = ts_start_seconds
                    still_frame_time = silent_period_end
                    logging.info(f"Silent period partially covers audio at {start_timestamp}. Adding clip until {silent_period_end} and then still frame.")
                break
            elif (silent_period_start >= ts_start_seconds and silent_period_start-ts_start_seconds < 5) or (silent_period_end <= ts_start_seconds and ts_start_seconds - silent_period_end < 5):
                if silent_period_start >= last_end:
                    insertion_time = silent_period_start
                    logging.info(f"Silent period found for audio at {start_timestamp}. Inserting here: {insertion_time}")
                    if silent_period_end - silent_period_start <= audio_clip.duration:
                        still_frame_time = silent_period_end
                    break

        if insertion_time is None:
            insertion_time = last_end + 0.5
            still_frame_time = last_end + 0.5
            logging.warning(f"No silent period found for audio at {start_timestamp}. Inserting a little after last description: {insertion_time}")

        if insertion_time >= last_end and still_frame_time is not None:
            if still_frame_time == insertion_time:
                segment = video.subclip(last_end, still_frame_time)
            else:
                segment = video.subclip(last_end, insertion_time)
            clips.append(segment)
        if insertion_time >= last_end and still_frame_time is None:
            segment = video.subclip(last_end, insertion_time)
            clips.append(segment)

        if still_frame_time is not None and insertion_time == still_frame_time:
            still_frame = video.get_frame(still_frame_time)
            still_clip = ImageClip(still_frame).set_duration(audio_clip.duration)
            still_clip = still_clip.set_audio(audio_clip)
            clips.append(still_clip)
        elif still_frame_time is not None and still_frame_time != insertion_time:
            video_segment = video.subclip(insertion_time, still_frame_time)
            still_frame = video.get_frame(still_frame_time)
            still_clip = ImageClip(still_frame).set_duration(audio_clip.duration - (still_frame_time - insertion_time))
            combined_audio = CompositeAudioClip([video_segment.audio, audio_clip.set_start(0)])
            combined_video = concatenate_videoclips([video_segment, still_clip.set_start(still_frame_time - insertion_time)])
            combined_video = combined_video.set_audio(combined_audio)
            clips.append(combined_video)
        else:
            audio_clip = audio_clip.set_start(0)
            video_segment = video.subclip(insertion_time, insertion_time + audio_clip.duration)
            combined_audio = CompositeAudioClip([video_segment.audio, audio_clip])
            video_segment = video_segment.set_audio(combined_audio)
            clips.append(video_segment)

        new_no_speech_periods = []
        for start, end in no_speech_periods:
            if start <= insertion_time < end:
                if start < insertion_time:
                    new_no_speech_periods.append((start, insertion_time))
                if insertion_time + audio_clip.duration < end:
                    new_no_speech_periods.append((insertion_time + audio_clip.duration, end))
            else:
                new_no_speech_periods.append((start, end))
        no_speech_periods = new_no_speech_periods
        logging.info(no_speech_periods)
            
        added_timestamps.add(start_timestamp)

        last_end = still_frame_time if still_frame_time is not None else insertion_time + audio_clip.duration

    if last_end < video.duration:
        final_segment = video.subclip(last_end, video.duration)
        clips.append(final_segment)

    final_clip = concatenate_videoclips(clips)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    logging.info(f"Final video created successfully. Duration: {final_clip.duration} seconds")

async def get_silent_periods_util_whisper(video_path):
    audio_path = f"{os.path.splitext(video_path)[0]}.wav"
    
    # Convert video to audio
    video = AudioSegment.from_file(video_path, format="mp4")
    video.export(audio_path, format="wav")
    
    stt_util = speechToTextUtilities(Model.AzureOpenAI)
    silent_periods = await stt_util.transcribe_with_timestamps(audio_path)
    
    return {"description": silent_periods}


async def run_final(video_path, output_path):
    # Get audio description and silent periods
    response_audio_desc = await get_audio_desc_util(video_path)
    ## Get silent period using Gemini
    response_silent_periods = await get_silent_periods_util(video_path)

    ## Get silent period using whisper
    #response_silent_periods = await get_silent_periods_util_whisper(video_path)
    response_body = {
        "description": response_audio_desc["description"],
        "silent_periods": response_silent_periods["description"]
    }
    try:
        clip = VideoFileClip(video_path)
        video_duration = clip.duration
        logging.info(f"Video loaded successfully. Duration: {video_duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")
        return

    verified_response = await verify_timestamp_range(response_body, video_duration)

    print(str(verified_response) + "MODIFIED")
    # test_response_body = {'description': '[0:02.100] Orange energy streaks through an ornate hallway lined with large lanterns. \n[0:08.250] A panda with a green wooden staff stands among broken lanterns. \n[0:10.100] Three figures are trapped inside one of the lanterns. A crocodile with red scales, a grey rhinoceros, and a white goat. \n[0:12.500] A line of animal warriors emerge from behind the lanterns. A bear, a water buffalo, and a snow leopard, radiating orange energy. \n', 
    #                   'silent_periods': '[00:00.000] - [00:25.140]\n[00:29.040] - [00:34.210]\n[00:36.430] - [00:45.300]\n[00:49.740] - [00:58.080]'}

    # test_response_body = {'description': '[0:02.100] Orange energy streaks through an ornate hallway lined with large lanterns. \n[0:08.250] A panda with a green wooden staff stands among broken lanterns. \n[0:10.100] Three figures are trapped inside one of the lanterns. A crocodile with red scales, a grey rhinoceros, and a white goat. \n[0:12.500] A line of animal warriors emerge from behind the lanterns. A bear, a water buffalo, and a snow leopard, radiating orange energy. \n[0:16.600] The snow leopard, lit by orange energy, walks towards the panda.\n[0:24.850] The snow leopard glares at the panda. \n[0:33.650] The panda’s eyes widen. \n[0:36.550] The snow leopard folds his paws together. \n[0:41.150] The panda smiles. \n[0:45.400] The panda throws his paws up in the air and laughs.  \n[0:48.200] The snow leopard glares. \n[0:55.650] The panda looks down. The snow leopard rests his paw on the panda’s head. \n', 
    #                   'silent_periods': '[00:00.000] - [00:25.140]\n[00:29.040] - [00:34.210]\n[00:36.430] - [00:45.300]\n[00:49.740] - [00:56.000]'}

    # # Call the function
    await create_final_video(video_path, verified_response, output_path, "ElevenLabs")

async def verify_timestamp_range(response_body, video_duration):
    # Verify and adjust the last timestamp in response_audio_desc
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
    matches = pattern.findall(response_body["description"])
    if matches:
        last_timestamp = matches[-1][0]
        last_time_seconds = sum(float(x) * 60 ** i for i, x in enumerate(reversed(last_timestamp.split(":"))))
        if last_time_seconds > video_duration:
            adjusted_time = video_duration - 0.1
            adjusted_timestamp = f"{int(adjusted_time // 60)}:{adjusted_time % 60:.3f}"
            response_body["description"] = re.sub(r'\[\d{1,2}:\d{2}(?:\.\d{3})?\] (.+)$', f'[{adjusted_timestamp}] \\1', response_body["description"])

    # Verify and adjust the last timestamp in response_silent_periods
    silent_pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] - \[(\d{1,2}:\d{2}(?:\.\d{3})?)\]')
    silent_matches = silent_pattern.findall(response_body["silent_periods"])
    if silent_matches:
        last_silent_start, last_silent_end = silent_matches[-1]
        last_silent_end_seconds = sum(float(x) * 60 ** i for i, x in enumerate(reversed(last_silent_end.split(":"))))
        if last_silent_end_seconds > video_duration:
            adjusted_silent_end = video_duration - 0.1
            adjusted_silent_timestamp = f"{int(adjusted_silent_end // 60)}:{adjusted_silent_end % 60:.3f}"
            response_body["silent_periods"] = re.sub(
                r'\[\d{1,2}:\d{2}(?:\.\d{3})?\] - \[\d{1,2}:\d{2}(?:\.\d{3})?\]$',
                f'[{last_silent_start}] - [{adjusted_silent_timestamp}]',
                response_body["silent_periods"]
            )
    
    # Log the adjusted response body for debugging
    logging.info(f"Adjusted response body: {response_body}")
    
    return response_body

if __name__ == "__main__":
    from llm_instructions import instructions, instructions_silent_period
    from gemini import get_info_from_video 
    from speech_to_text import speechToTextUtilities
    # Path to a sample video file
    video_path = "temp/input_test_panda.mp4"
    asyncio.run(run_final(video_path, output_path="temp/output_video.mp4"))
        
    