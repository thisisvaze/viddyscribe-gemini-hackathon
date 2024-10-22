import random
import os
from moviepy.editor import AudioFileClip
from util.gcs_bucket import download_from_gcs
import uuid

class BackgroundAudioGenerator():
    def __init__(self, category):
        self.category = category
        self.bucket_name = "viddyscribe_bg_audio_samples"
        self.gcs_files = [f'{category}_{i}.mp3' for i in range(1, 2)]
        self.selected_file = random.choice(self.gcs_files)
        self.local_file = self.download_file(self.selected_file)
        self.current_position = 0 

    def download_file(self, gcs_file):
        local_file = f'/tmp/{os.path.basename(gcs_file)}'
        download_from_gcs(self.bucket_name, gcs_file, local_file)
        return local_file

    def generate_music_from_collection(self, duration):
        audio_clip = AudioFileClip(self.local_file)
        start_time = self.current_position
        end_time = start_time + duration

        if end_time > audio_clip.duration:
            # Reset to start from 0 to duration
            start_time = 0
            end_time = duration
            self.current_position = duration  # Update position to duration
        else:
            self.current_position = end_time

        subclip = audio_clip.subclip(start_time, end_time)
        temp_music_path = f"/tmp/temp_music_{uuid.uuid4()}.mp3"
        subclip.write_audiofile(temp_music_path)
        return temp_music_path