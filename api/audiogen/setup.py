import torchaudio
from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write
import os
from pydub import AudioSegment
import torch  # Add this import


class MusicGenerator:
    def __init__(self, model_name="facebook/musicgen-melody"):
        # Load the model
        self.model = MusicGen.get_pretrained(model_name)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # Move model to the appropriate device

    def is_using_gpu(self):
        return self.device.type == 'cuda'

    def generate_music(self, melody_path, descriptions, duration):
        self.model.set_generation_params(duration = duration)
        # Load the melody
        melody, sr = torchaudio.load(melody_path)
        
        # Generate music using the melody and descriptions
        wav = self.model.generate_with_chroma(descriptions, melody[None].expand(1, -1, -1).to(self.device), sr)
        
        output_paths = []
        for idx, one_wav in enumerate(wav):
            output_path = os.path.join(os.path.dirname(melody_path), f'{idx}_generated')  # Add .wav extension
            # Save the generated music with loudness normalization at -14 db LUFS
            audio_write(output_path, one_wav.cpu(), self.model.sample_rate, strategy="loudness")
            output_paths.append(output_path+".wav")
        
        return output_paths[0]

if __name__ == "__main__":
    pass
    # Example usage:
    # generator = MusicGenerator()
    # print(f"Using GPU: {generator.is_using_gpu()}")
    # video_path = "./b.mp4"
    # audio_path = convert_mp4_to_wav(video_path)
    # descriptions = ['']
    # output_paths = generator.generate_music(audio_path, descriptions, duration=30)  # Add duration parameter
    # print(f"Generated music saved to: {output_paths}")
