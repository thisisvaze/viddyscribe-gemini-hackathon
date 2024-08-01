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
import glob
# Load environment variables from .env file
load_dotenv()


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


import os

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

def text_to_wav_azure(voice_name: str, text: str, filename: str):
    speech_config = speechsdk.SpeechConfig(subscription=os.environ.get('SPEECH_KEY'), region=os.environ.get('SPEECH_REGION'))
    audio_config = speechsdk.audio.AudioOutputConfig(filename=filename)
    speech_config.speech_synthesis_voice_name = voice_name

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()

    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"Speech synthesized for text [{text}] and saved to {filename}")
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print(f"Speech synthesis canceled: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print(f"Error details: {cancellation_details.error_details}")
                print("Did you set the speech resource key and region values?")

def generate_wav_files_from_response(response_body: dict, voice_name: str):
    description = response_body["description"]
    pattern = re.compile(r'\[(\d{2}:\d{2}\.\d{3})\] (.+)')
    matches = pattern.findall(description)

    timestamp_ranges = []

    for timestamp, text in matches:
        start_time = timestamp
        filename = f"{start_time.replace(':', '-')}.wav"
        text_to_wav(voice_name, text, filename)

        max_wait_time = 30
        wait_interval = 0.5
        elapsed_time = 0

        while (not os.path.exists(filename) or os.path.getsize(filename) == 0) and elapsed_time < max_wait_time:
            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            raise Exception(f"Failed to generate WAV file: {filename}")

        audio_clip = AudioFileClip(filename)
        duration = audio_clip.duration
        end_time = (datetime.datetime.strptime(start_time, "%M:%S.%f") + datetime.timedelta(seconds=duration)).strftime("%M-%S.%f")[:-3]
        new_filename = f"{start_time.replace(':', '-')}_to_{end_time}.wav"
        os.rename(filename, new_filename)
        print(f"Generated speech saved to \"{new_filename}\"")

        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    return timestamp_ranges

def create_final_video(video_path: str, response_body: dict, output_path: str):
    try:
        video = VideoFileClip(video_path)
    except OSError as e:
        print(f"Error loading video file {video_path}: {e}")
        raise ValueError(f"Error loading video file {video_path}: {e}")

    
    description = response_body["description"]
    logging.info(f"Description: {description}")
    pattern = re.compile(r'\[(\d{2}:\d{2}\.\d{3})\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Matches: {matches}")

    silent_periods = response_body["silent_periods"]
    logging.info(f"Silent periods: {silent_periods}")
    no_speech_pattern = re.compile(r'\[(\d{2}:\d{2}\.\d{3}) - (\d{2}:\d{2}\.\d{3})\]')
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
            insertion_time = video.duration
            still_frame_time = video.duration
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

         # Check for other timestamps before the current end
        # for j in range(i + 1, len(matches)):
        #     if start_timestamp in added_timestamps:
        #         continue  
        #     next_timestamp = matches[j]
        #     next_ts_parts = next_timestamp.split(':')
        #     next_ts_seconds = int(next_ts_parts[0]) * 60 + float(next_ts_parts[1])

        #     if next_ts_seconds < end:
        #         next_audio_filename = f"{next_timestamp.replace(':', '-')}_to_*.wav"
        #         next_audio_files = glob.glob(next_audio_filename)
        #         if not next_audio_files:
        #             raise FileNotFoundError(f"Audio file matching {next_audio_filename} not found")
        #         next_audio_clip = AudioFileClip(next_audio_files[0])

        #         next_still_clip = ImageClip(still_frame).set_duration(next_audio_clip.duration)
        #         next_still_clip = next_still_clip.set_audio(next_audio_clip)
        #         clips.append(next_still_clip)
        #         time_offset += next_audio_clip.duration
        #         added_timestamps.add(next_timestamp) 
        #     else:
        #         break

        last_end = still_frame_time if still_frame_time is not None else insertion_time + audio_clip.duration

        time_offset += audio_clip.duration

    if last_end < video.duration:
        final_segment = video.subclip(last_end)
        clips.append(final_segment)

    final_clip = concatenate_videoclips(clips)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    print(f"Final video created successfully. Duration: {final_clip.duration} seconds")
# ... existing code ...
# Sample response body

if __name__ == "__main__":
        
    response_body = {
        "description": "[00:05.100] Hey! Whats up, can you hear me? \n",
        "silent_periods": "[00:00.000 - 00:05.000]\n"
    }

    generate_wav_files_from_response(response_body, "en-US-Journey-O");

    # Path to a sample video file
    video_path = "temp/inp_new.mp4"

    # Output path for the final video
    output_path = "temp/output_video.mp4"

    try:
        clip = VideoFileClip(video_path)
        logging.info(f"Video loaded successfully. Duration: {clip.duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")

    # Call the function
    create_final_video(video_path, response_body, output_path)