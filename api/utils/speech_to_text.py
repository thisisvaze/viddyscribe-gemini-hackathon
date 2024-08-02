import os
import azure.cognitiveservices.speech as speechsdk
from enum import Enum
import time
class Model(Enum):
    AzureOpenAI = 1
    OpenAI = 2

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

    def transcribe_with_timestamps(self, audio_file_path):
        audio_input = speechsdk.AudioConfig(filename=audio_file_path)
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config, audio_config=audio_input)

        all_words = []
        transcription_result = []

        def handle_final_result(evt):
            import json
            json_result = evt.result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
            response = json.loads(json_result)
            words = response['NBest'][0]['Words']
            all_words.extend(words)

        speech_recognizer.recognized.connect(handle_final_result)
        speech_recognizer.start_continuous_recognition()
        speech_recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
        speech_recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
        speech_recognizer.canceled.connect(lambda evt: print('CANCELED {}'.format(evt)))

        done = False

        def stop_cb(evt):
            nonlocal done
            done = True
            speech_recognizer.stop_continuous_recognition()

        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)

        while not done:
            time.sleep(0.5)

        sentence = []
        sentence_start_time = None
        gap_threshold = 300  # Gap threshold in milliseconds

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
                    sentence = []
                    sentence_start_time = start_time

            sentence.append(word['Word'])

        if sentence:
            sentence_start_time_str = time.strftime('%H:%M:%S', time.gmtime(sentence_start_time / 1000)) + f".{int(sentence_start_time % 1000):03d}"
            sentence_end_time_str = time.strftime('%H:%M:%S', time.gmtime(end_time / 1000)) + f".{int(end_time % 1000):03d}"
            transcription_result.append(f"[{sentence_start_time_str} - {sentence_end_time_str}] {' '.join(sentence)}")

        return '\n'.join(transcription_result)

# Usage example
# stt_util = speechToTextUtilities(model.AzureOpenAI)
# transcription = stt_util.transcribe_with_timestamps("path_to_audio_file.wav")
# print(transcription)