import json
import re
import logging
from asyncio import Semaphore
import shutil
from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, TextClip
from google.api_core.exceptions import ResourceExhausted
import uuid
from util.Constants import BUCKET_NAME
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
import azure.cognitiveservices.speech as speechsdk
from util.bgaudio import BackgroundAudioGenerator
from util.gcs_bucket import upload_to_gcs, download_from_gcs
from util.llm_instructions import insturctions_combined_format, instructions_timestamp_format, instructions_choose_category
import datetime
import os
import asyncio
from elevenlabs.client import AsyncElevenLabs
from elevenlabs import save
import os
import glob
import asyncio
from pydub import AudioSegment
from dotenv import load_dotenv
from util.gemini import VertexAIUtility
import os

load_dotenv()
# Ensure the temp directory exists
os.makedirs('temp', exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_voice_name(voice_model: str):
    if voice_model == "Azure":
        return "en-US-NovaMultilingualNeural"
    elif voice_model == "Google":
        return "en-US-Journey-O"
    elif voice_model == "ElevenLabs":
        return "kPzsL2i3teMYv0FxEYQ6"
    else:
        raise ValueError(f"Unsupported voice model: {voice_model}")

async def tts_utility(model_name, text, filename):
    voice = get_voice_name(model_name)
    # if model_name == "Azure":
    #     return text_to_wav_azure(voice, text, filename)
    # elif model_name == "Google":
    #     return text_to_wav(voice, text, filename)
    if model_name == "ElevenLabs":
        return await text_to_wav_elevenlabs(voice, text, filename)

async def text_to_wav_elevenlabs(voice_id: str, text: str, filename: str):
    client = AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            audio_generator = await client.generate(
                text=text,
                voice=voice_id,
                model="eleven_turbo_v2_5"
            )
            with open(filename, "wb") as f:
                async for chunk in audio_generator:
                    f.write(chunk)
            logging.info(f'Generated speech saved to "{filename}"')
            return  # Exit the function if successful
        except Exception as e:
            logging.error(f"Error generating WAV file on attempt {attempt + 1} for text: '{text}' - {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise

async def generate_wav_files_from_response(response_body: dict, model_name: str, unique_id: str):
    description = response_body["description"]
    logging.info(f"Description: {description}")
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
    matches = pattern.findall(description)

    if not matches:
        logging.error("No timestamps found in the description returned by gemini.")
        raise ValueError("Failed to generate response audio timestamps")

    timestamp_ranges = []
    tasks = []
    semaphore = Semaphore(3)

    async def limited_tts_utility(model_name, text, filename):
        async with semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await tts_utility(model_name, text, filename)
                    break
                except Exception as e:
                    logging.error(f"Error generating WAV file on attempt {attempt + 1} for text: '{text}' - {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                    else:
                        raise

    for match in matches:
        timestamp, text = match
        start_time = timestamp.strip('[')
        filename = f"temp/{unique_id}_{start_time.replace(':', '-')}.wav"
        logging.info(f"Generating WAV for text: '{text}' at timestamp: {start_time} with filename: {filename}")
        tasks.append(limited_tts_utility(model_name, text, filename))

    await asyncio.gather(*tasks)

    for match in matches:
        timestamp, text = match
        start_time = timestamp.strip('[')
        filename = f"temp/{unique_id}_{start_time.replace(':', '-')}.wav"
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
        new_filename = f"temp/{unique_id}_{start_time.replace(':', '-')}_to_{end_time}.wav"
        os.rename(filename, new_filename)
        logging.info(f"Generated speech saved to \"{new_filename}\"")

        timestamp_ranges.append(f"[{start_time}] - [{end_time}] {text}")

    logging.info(f"Generated timestamp ranges: {timestamp_ranges}")
    return timestamp_ranges

def get_audio_desc_util(video_path, add_bg_music):
    v = VertexAIUtility()
    
    if not v.validate_video(video_path):
        print(f"Error: Video file '{video_path}' is invalid or corrupted.")
        return {"error": "Invalid video file"}

    response_audio_desc = v.get_info_from_video(video_path, insturctions_combined_format)
    if add_bg_music:
        bg_audio_response = v.get_info_from_video(video_path, instructions_choose_category)["description"]
        try:
            # Strip the code block markers and parse the JSON
            bg_audio_response = bg_audio_response.strip('```json').strip('```').strip()
            bg_audio_category = json.loads(bg_audio_response)["category"]
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode JSON from bg_audio_response: {e}")
            raise
    else:
        bg_audio_category = None

    reformmated_desc = v.gemini_llm(prompt=response_audio_desc["description"], inst=instructions_timestamp_format)
    return reformmated_desc, bg_audio_category

def convert_mp4_to_wav(video_path):
    logging.info(f"Converting video to audio: {video_path}")
    audio_path = f"{os.path.splitext(video_path)[0]}.wav"
    try:
        # Check if the video file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Get file info
        file_size = os.path.getsize(video_path)
        logging.info(f"Video file size: {file_size} bytes")

        # Try to open the file with moviepy first
        try:
            video = VideoFileClip(video_path)
            if video.audio is not None:
                audio = video.audio
                audio.write_audiofile(audio_path)
                logging.info(f"Audio exported to: {audio_path} using moviepy")
            else:
                logging.warning(f"No audio stream found in video: {video_path}")
                return None
        except Exception as moviepy_error:
            logging.warning(f"Moviepy conversion failed: {moviepy_error}. Trying pydub...")

            # If moviepy fails, try pydub
            video = AudioSegment.from_file(video_path, format="mp4")
            video.export(audio_path, format="wav")
            logging.info(f"Audio exported to: {audio_path} using pydub")

    except FileNotFoundError as e:
        logging.error(f"File not found error: {e}")
        raise
    except Exception as e:
        logging.error(f"Error during conversion: {e}")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error(f"Error args: {e.args}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise

    return audio_path

async def main_function(gcs_url, add_bg_music):
    output_path = os.path.splitext(gcs_url)[0] + "_output.mp4"
    try:
        unique_id = uuid.uuid4()
        video_path = f"temp/temp_video_{unique_id}.mp4"
        download_from_gcs(BUCKET_NAME, gcs_url, video_path)
        
        clip = VideoFileClip(video_path)
        video_duration = clip.duration
        logging.info(f"Video loaded successfully. Duration: {video_duration} seconds")
        clip.close()
    except Exception as e:
        logging.error(f"Error loading video: {e}")
        return {"status": "error", "message": str(e)}
    
    response_audio_desc, bg_audio_category = get_audio_desc_util(video_path, add_bg_music)
    if "error" in response_audio_desc:
        logging.error(f"Error in Gemini response: {response_audio_desc['error']}")
        return {"status": "error", "message": response_audio_desc["error"]}

    response_body = {
        "description": response_audio_desc["description"],
    }
    try:
        await create_final_video_v2(video_path, bg_audio_category, response_body, output_path, "ElevenLabs", unique_id, add_bg_music)
    except ValueError as e:
        logging.error(f"Error during video processing: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logging.error(f"Unexpected error during video processing: {e}")
        return {"status": "error", "message": str(e)}
    
    gcs_url = upload_to_gcs(BUCKET_NAME, output_path, os.path.basename(output_path))

    os.remove(video_path)
    os.remove(output_path)
    # Remove only the .wav files with the unique_id
    wav_files = glob.glob(f'temp/{unique_id}_*.wav')
    for wav_file in wav_files:
        os.remove(wav_file)
    
    # Remove the temporary video file
    temp_video_file = f"temp/temp_video_{unique_id}.mp4"
    if os.path.exists(temp_video_file):
        os.remove(temp_video_file)

    # Remove the temporary video file
    temp_generated_wav_file = f"temp/temp_video_{unique_id}.wav"
    if os.path.exists(temp_generated_wav_file):
        os.remove(temp_generated_wav_file)
    
    return {"status": "success", "output_url": gcs_url}

async def create_final_video_v2(video_path: str, bg_audio_category: str, response_body: dict, output_path: str, model_name, unique_id: str, add_bg_music : str):
    logging.info(f"Starting create_final_video_v2 with video_path: {video_path}, output_path: {output_path}, model_name: {model_name}")

    if add_bg_music and bg_audio_category:
        bg_audio_generator = BackgroundAudioGenerator(bg_audio_category)
    
    original_videos_audio = convert_mp4_to_wav(video_path)
    if original_videos_audio is None:
        logging.warning(f"No audio found in video: {video_path}. Proceeding without original audio.")
        original_audio_clip = None
    else:
        logging.info(f"Converted video to audio: {original_videos_audio}")
        original_audio_clip = AudioFileClip(original_videos_audio)
        logging.info(f"Loaded original audio clip with duration: {original_audio_clip.duration}")

    if original_audio_clip is None:
        video = VideoFileClip(video_path)
        blank_audio = AudioSegment.silent(duration=video.duration * 1000)  # duration in milliseconds
        blank_audio_path = f"temp/{unique_id}_blank_audio.wav"
        blank_audio.export(blank_audio_path, format="wav")
        original_audio_clip = AudioFileClip(blank_audio_path).set_start(0)
        logging.info(f"Created blank audio clip with duration: {original_audio_clip.duration}")


    response_audio_timestamps = await generate_wav_files_from_response(response_body, model_name, unique_id)
    if not response_audio_timestamps:
        logging.error("Failed to generate response audio timestamps")
        raise ValueError("Failed to generate response audio timestamps")

    try:
        video = VideoFileClip(video_path)
        logging.info(f"Loaded video file with duration: {video.duration}")
    except OSError as e:
        logging.error(f"Error loading video file {video_path}: {e}")
        raise ValueError(f"Error loading video file {video_path}: {e}")

    description = response_body["description"]
    pattern = re.compile(r'\[(\d{1,2}:\d{2}(?:\.\d{3})?)\] (.+)')
    matches = pattern.findall(description)
    logging.info(f"Found {len(matches)} matches in the description")

    clips = []
    last_end = 0
    added_timestamps = set()

    for i, (start_timestamp, text) in enumerate(matches):
        logging.info(f"Processing match {i}: start_timestamp={start_timestamp}, text={text}")
        
        ts_parts = start_timestamp.split(':')
        ts_start_seconds = int(ts_parts[0]) * 60 + float(ts_parts[1])
        logging.info(f"Calculated start time in seconds: {ts_start_seconds}")

        audio_filename = f"temp/{unique_id}_{start_timestamp.replace(':', '-')}_to_*.wav"
        audio_files = glob.glob(audio_filename)
        if not audio_files:
            raise FileNotFoundError(f"Audio file matching {audio_filename} not found")
        audio_clip = AudioFileClip(audio_files[0])
        logging.info(f"Loaded audio clip from {audio_files[0]} with duration: {audio_clip.duration}")
        
        insertion_time = ts_start_seconds
        still_frame_time = ts_start_seconds
        logging.warning(f"Inserting audio description at: {start_timestamp}")

        if still_frame_time is not None:
            if still_frame_time == insertion_time:
                segment = video.subclip(last_end, still_frame_time)
                clips.append(segment)
                logging.info(f"Added video segment from {last_end} to {still_frame_time}")

        if still_frame_time is not None and insertion_time == still_frame_time:
            still_frame = video.get_frame(still_frame_time)
            still_clip = ImageClip(still_frame).set_duration(audio_clip.duration)
            still_clip = still_clip.set_audio(audio_clip)
            logging.info(f"Created still clip with duration: {audio_clip.duration}")

            if ts_start_seconds == 0: 
                e_time = ts_start_seconds + 5 
            else:
                e_time = ts_start_seconds

            fade_duration = 0.5
            bg_fade_duration = 0.2
            if original_audio_clip:
                vid_max_volume = original_audio_clip.max_volume()
                still_frame_volume = original_audio_clip.subclip(max(ts_start_seconds - 5, 0), e_time).max_volume()
                if vid_max_volume == 0:
                    vid_max_volume = audio_clip.max_volume()
                    still_frame_volume = vid_max_volume
                max_audio_desc_volume = audio_clip.max_volume()
                
                logging.info(f"Calculated volumes: vid_max_volume={vid_max_volume}, max_audio_desc_volume={max_audio_desc_volume}, still_frame_volume={still_frame_volume}")
                
                if add_bg_music and bg_audio_category:
                    music_path = bg_audio_generator.generate_music_from_collection(
                        duration=int(audio_clip.duration)
                    )
                    logging.info(f"Generated background music: {music_path}")

                    generated_music_clip = AudioFileClip(music_path)
                    generated_music_clip_max_volume = generated_music_clip.max_volume()
                    generated_music_clip = generated_music_clip.volumex((vid_max_volume/generated_music_clip_max_volume)*0.5).audio_fadein(fade_duration).volumex(0.12).audio_fadeout(fade_duration).volumex((vid_max_volume/generated_music_clip_max_volume)*3)
                    
                    combined_audio_clips = [still_clip.audio.volumex(vid_max_volume/max_audio_desc_volume), generated_music_clip.set_start(0)]
                    if ts_start_seconds + bg_fade_duration < int(original_audio_clip.duration):
                        logging.info(f"Fading out start audio original track from {ts_start_seconds} to {ts_start_seconds + bg_fade_duration}")
                        faded_out_start_audio_original_track = original_audio_clip.subclip(ts_start_seconds, ts_start_seconds + bg_fade_duration).audio_fadeout(bg_fade_duration)
                        combined_audio_clips.append(faded_out_start_audio_original_track.set_start(0))
                    if ts_start_seconds > bg_fade_duration:
                        logging.info(f"Fading in end audio original track from {ts_start_seconds - bg_fade_duration} to {ts_start_seconds}")
                        faded_in_end_audio_original_track = original_audio_clip.subclip(ts_start_seconds - bg_fade_duration, ts_start_seconds).audio_fadein(bg_fade_duration)
                        combined_audio_clips.append(faded_in_end_audio_original_track.set_start(audio_clip.duration - bg_fade_duration))

                    combined_audio = CompositeAudioClip(combined_audio_clips)

                else:
                    combined_audio_clips = [still_clip.audio.volumex(vid_max_volume/max_audio_desc_volume)]
                    if ts_start_seconds + bg_fade_duration < int(original_audio_clip.duration):
                        logging.info(f"Fading out start audio original track from {ts_start_seconds} to {ts_start_seconds + bg_fade_duration}")
                        faded_out_start_audio_original_track = original_audio_clip.subclip(ts_start_seconds, ts_start_seconds + bg_fade_duration).audio_fadeout(bg_fade_duration)
                        combined_audio_clips.append(faded_out_start_audio_original_track.set_start(0))
                    if ts_start_seconds > bg_fade_duration:
                        logging.info(f"Fading in end audio original track from {ts_start_seconds - bg_fade_duration} to {ts_start_seconds}")
                        faded_in_end_audio_original_track = original_audio_clip.subclip(ts_start_seconds - bg_fade_duration, ts_start_seconds).audio_fadein(bg_fade_duration)
                        combined_audio_clips.append(faded_in_end_audio_original_track.set_start(audio_clip.duration - bg_fade_duration))

                    
                    combined_audio = CompositeAudioClip(combined_audio_clips)
                

                still_clip = still_clip.set_audio(combined_audio)
                logging.info(f"Set combined audio for still clip")
            
            clips.append(still_clip)
            logging.info(f"Added still clip to clips")

        added_timestamps.add(start_timestamp)
        last_end = still_frame_time
        logging.info(f"Updated last_end to {last_end}")

    if last_end < int(video.duration):
        final_segment_end = int(video.duration)
        final_segment = video.subclip(last_end, final_segment_end)
        clips.append(final_segment)
        logging.info(f"Added final video segment from {last_end} to {final_segment_end}")

    final_clip = concatenate_videoclips(clips)
    try:
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        logging.info(f"Final video written to {output_path}")
    except Exception as e:
        logging.error(f"Error during final video writing: {e}")
        raise

    logging.info(f"Final video created successfully. Duration: {final_clip.duration} seconds")