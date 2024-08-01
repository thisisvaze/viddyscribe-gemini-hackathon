import google.cloud.texttospeech as tts
import re
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip, CompositeAudioClip
from google.api_core.exceptions import ResourceExhausted  # Import the exception
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
import datetime
import time
# Load environment variables from .env file
load_dotenv()
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
    pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\] (.+)')
    matches = pattern.findall(description)

    timestamp_ranges = []

    for timestamp, text in matches:
        start_time = timestamp
        filename = f"{start_time.replace(':', '-')}.wav"  # Use start timestamp as filename
        #text_to_wav_azure(voice_name, text, filename)
        text_to_wav(voice_name, text, filename)

        # Wait until the file is fully generated
        max_wait_time = 30  # Maximum wait time in seconds
        wait_interval = 0.5  # Interval between checks in seconds
        elapsed_time = 0

        while (not os.path.exists(filename) or os.path.getsize(filename) == 0) and elapsed_time < max_wait_time:
            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            raise Exception(f"Failed to generate WAV file: {filename}")

        # Calculate end timestamp based on the duration of the generated WAV file
        audio_clip = AudioFileClip(filename)
        duration = audio_clip.duration
        end_time = (datetime.datetime.strptime(start_time, "%H:%M:%S.%f") + datetime.timedelta(seconds=duration)).strftime("%H-%M-%S.%f")[:-3]
        new_filename = f"{start_time.replace(':', '-')}_to_{end_time}.wav"
        os.rename(filename, new_filename)
        print(f"Generated speech saved to \"{new_filename}\"")

        # Append the timestamp range and description to the list
        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    return timestamp_ranges
    

# def create_final_video(video_path: str, response_body: dict, output_path: str):
#     try:
#         video = VideoFileClip(video_path)
#     except OSError as e:
#         print(f"Error loading video file {video_path}: {e}")
#         raise ValueError(f"Error loading video file {video_path}: {e}")

#     description = response_body["description"]
#     pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\] (.+)')
#     matches = pattern.findall(description)

#     no_speech_pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}\.\d{3}) - (\d{2}:\d{2}:\d{2}\.\d{3})\] No speech period')
#     no_speech_matches = no_speech_pattern.findall(description)

#     no_speech_periods = []
#     for start, end in no_speech_matches:
#         start_parts = start.split(':')
#         end_parts = end.split(':')
#         start_seconds = int(start_parts[0]) * 3600 + int(start_parts[1]) * 60 + float(start_parts[2])
#         end_seconds = int(end_parts[0]) * 3600 + int(end_parts[1]) * 60 + float(end_parts[2])
#         no_speech_periods.append((start_seconds, end_seconds))

#     clips = []
#     last_end = 0
#     audio_clips = [video.audio]  # Start with the original audio track
#     used_ranges = []  # To keep track of used timestamp ranges

#     for timestamp, text in matches:
#         ts_parts = timestamp.split(':')
#         ts_seconds = int(ts_parts[0]) * 3600 + int(ts_parts[1]) * 60 + float(ts_parts[2])
        
#         audio_clip = AudioFileClip(f"{timestamp.replace(':', '-')}.wav")

#         # Find the closest no speech period before the audio description timestamp
#         closest_no_speech_start = None
#         closest_no_speech_end = None
#         for start, end in no_speech_periods:
#             if start <= ts_seconds:
#                 closest_no_speech_start = start
#                 closest_no_speech_end = end
#             else:
#                 break

#         if closest_no_speech_start is not None:
#             ts_seconds = closest_no_speech_start

#         # Check for overlapping and adjust if necessary
#         for start, end in used_ranges:
#             if start <= ts_seconds < end:
#                 ts_seconds = end  # Move to the end of the last used range

#         # Add the video part before the pause
#         if ts_seconds > last_end:
#             clips.append(video.subclip(last_end, min(ts_seconds, video.duration)))

#         # Add the still frame with the audio
#         try:
#             frame = video.get_frame(min(ts_seconds, video.duration - 0.1))
#         except Exception as e:
#             print(f"Error getting frame at {ts_seconds} seconds: {e}")
#             continue

#         still = (VideoFileClip(video_path)
#                  .subclip(min(ts_seconds, video.duration - 0.1), min(ts_seconds + 0.1, video.duration))  # Ensure subclip end is within duration
#                  .set_duration(audio_clip.duration)
#                  .set_audio(audio_clip))
#         clips.append(still)

#         # Add the audio description to the list of audio clips
#         audio_clips.append(audio_clip.set_start(ts_seconds))

#         last_end = ts_seconds + audio_clip.duration  # Update last_end to the end of the audio clip

#         # If the audio description exceeds the no speech period, pause and continue
#         if closest_no_speech_end is not None and last_end > closest_no_speech_end:
#             last_end = closest_no_speech_end

#         # Track the used range
#         used_ranges.append((ts_seconds, last_end))

#     # Add the remaining part of the video
#     if last_end < video.duration:
#         clips.append(video.subclip(last_end, video.duration))
#     else:
#         # Extend the video with a still frame if necessary
#         frame = video.get_frame(video.duration - 0.1)
#         extended_still = (VideoFileClip(video_path)
#                           .subclip(video.duration - 0.1, video.duration)
#                           .set_duration(last_end - video.duration)
#                           .set_audio(None))
#         clips.append(extended_still)

#     final_clip = concatenate_videoclips(clips)
#     # Combine the original audio with the audio descriptions
#     final_audio = CompositeAudioClip(audio_clips)
#     final_clip = final_clip.set_audio(final_audio)

#     final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")