import os
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import time
import asyncio
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    from utils.model_configs import Model
else:
    from api.utils.model_configs import Model 

class speechToTextUtilities:
    def __init__(self, model):
        self.model = model
        self.speech_config = speechsdk.SpeechConfig(
            subscription=os.getenv("SPEECH_KEY"),
            region=os.getenv("SPEECH_REGION")
        )
        self.speech_config.speech_recognition_language = "en-US"  # Set your language here
        self.speech_config.request_word_level_timestamps()
        self.speech_config.output_format = speechsdk.OutputFormat(1)
        self.speech_config.speech_recognition_model_id = "whisper"

    async def transcribe_with_timestamps_openai(self, audio_file_path):
        import os
        from openai import AsyncAzureOpenAI
        
        client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
            api_version="2024-02-01",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        deployment_id = "whisper"  # This will correspond to the custom name you chose for your deployment when you deployed a model.
        audio_test_file = audio_file_path
        
        result = await client.audio.transcriptions.create(
            file=open(audio_test_file, "rb"),            
            model=deployment_id,
            response_format="srt"
        )
        print(result)
        # Parse the result and reformat silent periods
        transcription_periods = []
        silent_periods = []
        lines = result.split('\n')
        gap_threshold = 300  # Gap threshold in milliseconds

        for i in range(1, len(lines), 4):
            if i + 1 < len(lines):
                start_time, end_time = lines[i].split(' --> ')
                start_time_ms = self._convert_srt_time_to_ms(start_time)
                end_time_ms = self._convert_srt_time_to_ms(end_time)
                transcription_periods.append((start_time_ms, end_time_ms))

        # Handle initial silent period
        if transcription_periods:
            first_start_time = transcription_periods[0][0]
            if first_start_time > gap_threshold:
                silent_periods.append(f"[{self._format_ms_to_srt_time(0)}] - [{self._format_ms_to_srt_time(first_start_time)}]")
        for i in range(1, len(transcription_periods)):
            previous_end_time = transcription_periods[i - 1][1]
            current_start_time = transcription_periods[i][0]
            gap = current_start_time - previous_end_time
            if gap > gap_threshold:
                silent_periods.append(f"[{self._format_ms_to_srt_time(previous_end_time)}] - [{self._format_ms_to_srt_time(current_start_time)}]")

        # Handle final silent period
        audio = AudioSegment.from_file(audio_file_path)
        audio_duration = len(audio)
        last_end_time = transcription_periods[-1][1]
        if audio_duration - last_end_time > gap_threshold:
            silent_periods.append(f"[{self._format_ms_to_srt_time(last_end_time)}] - [{self._format_ms_to_srt_time(audio_duration)}]")

        formatted_periods = '\n'.join(silent_periods)
        print("OPENAI" + str(formatted_periods))
        return formatted_periods

    def _convert_srt_time_to_ms(self, srt_time):
        h, m, s = srt_time.split(':')
        s, ms = s.split(',')
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)

    def _format_ms_to_srt_time(self, ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        return f"{m:02}:{s:02}.{ms:03}"


    async def transcribe_with_timestamps(self, audio_file_path):
        audio_input = speechsdk.AudioConfig(filename=audio_file_path)
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config, audio_config=audio_input)

        all_words = []
        transcription_result = []
        silent_periods = []

        def handle_final_result(evt):
            import json
            json_result = evt.result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
            response = json.loads(json_result)
            words = response['NBest'][0]['Words']
            all_words.extend(words)

        speech_recognizer.recognized.connect(handle_final_result)
        speech_recognizer.start_continuous_recognition_async()
        speech_recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
        speech_recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
        speech_recognizer.canceled.connect(lambda evt: print('CANCELED {}'.format(evt)))

        done = asyncio.Event()

        def stop_cb(evt):
            done.set()
            speech_recognizer.stop_continuous_recognition_async()

        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)

        await done.wait()

        sentence = []
        sentence_start_time = None
        gap_threshold = 300  # Gap threshold in milliseconds

        # Handle initial silent period
        if all_words:
            first_word_start_time = all_words[0]['Offset'] / 10000  # Convert to milliseconds
            if first_word_start_time > gap_threshold:
                silent_periods.append(str(f"[00:00:00.000] - [{time.strftime('%H:%M:%S', time.gmtime(first_word_start_time / 1000))}.{int(first_word_start_time % 1000):03d}]"))
        for i, word in enumerate(all_words):
            start_time = word['Offset'] / 10000  # Convert to milliseconds
            end_time = start_time + (word['Duration'] / 10000)  # Convert to milliseconds

            if sentence_start_time is None:
                sentence_start_time = start_time

            if i > 0:
                previous_end_time = all_words[i - 1]['Offset'] / 10000 + (all_words[i - 1]['Duration'] / 10000)
                gap = start_time - previous_end_time
                if gap > gap_threshold:
                    sentence_start_time_str = time.strftime('%H:%M:%S', time.gmtime(sentence_start_time / 1000)) + f".{int(sentence_start_time % 1000):03d}"
                    sentence_end_time_str = time.strftime('%H:%M:%S', time.gmtime(previous_end_time / 1000)) + f".{int(previous_end_time % 1000):03d}"
                    transcription_result.append(f"[{sentence_start_time_str} - {sentence_end_time_str}] {' '.join(sentence)}")
                    silent_periods.append(str(f"[{sentence_end_time_str}] - [{time.strftime('%H:%M:%S', time.gmtime(start_time / 1000))}.{int(start_time % 1000):03d}]"))
                    sentence = []
                    sentence_start_time = start_time

            sentence.append(word['Word'])

        if sentence:
            sentence_start_time_str = time.strftime('%H:%M:%S', time.gmtime(sentence_start_time / 1000)) + f".{int(sentence_start_time % 1000):03d}"
            sentence_end_time_str = time.strftime('%H:%M:%S', time.gmtime(end_time / 1000)) + f".{int(end_time % 1000):03d}"
            transcription_result.append(f"[{sentence_start_time_str} - {sentence_end_time_str}] {' '.join(sentence)}")

        # Handle final silent period
        audio = AudioSegment.from_file(audio_file_path)
        audio_duration = len(audio) 

        if all_words:
            last_word_end_time = all_words[-1]['Offset'] / 10000 + (all_words[-1]['Duration'] / 10000)  # Convert to milliseconds
            if audio_duration - last_word_end_time > gap_threshold:
                silent_periods.append(str(f"[{time.strftime('%H:%M:%S', time.gmtime(last_word_end_time / 1000))}.{int(last_word_end_time % 1000):03d}] - [{time.strftime('%H:%M:%S', time.gmtime(audio_duration / 1000))}.{int(audio_duration % 1000):03d}]"))
        
        return '\n'.join(silent_periods)

if __name__ == "__main__":
    # Usage example
    stt_util = speechToTextUtilities(Model.AzureOpenAI)
    transcription = asyncio.run(stt_util.transcribe_with_timestamps("./../temp/input_test_panda.mp4"))
    print(transcription)