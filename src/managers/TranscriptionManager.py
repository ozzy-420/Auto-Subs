import asyncio
import threading
import whisper
from src.utils.constants import WHISPER_MODEL
from logging import getLogger
logger = getLogger(__name__)


class TranscriptionManager:
    def __init__(self, whisper_model: str = WHISPER_MODEL):
        self._model = None
        self._model_loading_thread = None
        self._model_lock = asyncio.Lock()
        self._transcription_listeners = []
        self._model_loaded_event = threading.Event()  # Event to signal model loading completion
        self._transcription_process = None
        self._current_audio_path = None
        self.load_model(whisper_model)

    def load_model(self, whisper_model: str) -> None:
        """
        Loads the Whisper model in a separate thread.
        """

        def worker():
            try:
                logger.info("Loading Whisper model...")
                self._model = whisper.load_model(whisper_model)
                logger.info("Whisper model loaded successfully.")
                self._model_loaded_event.set()  # Signal that the model is loaded
            except Exception as e:
                logger.exception("Failed to load Whisper model")
                self._model_loaded_event.set()  # Ensure the event is set even on failure
                raise RuntimeError(f"Failed to load model: {e}") from e

        # Start the worker in a separate thread
        self._model_loading_thread = threading.Thread(target=worker, daemon=True)
        self._model_loading_thread.start()

    async def transcribe(self, audio_path: str, word_timestamps: bool = True, language: str = None) -> dict | None:
        """
        Asynchronously transcribes an audio file to text using the Whisper model.

        Args:
            audio_path (str): Path to the input audio file.
            word_timestamps (bool): Whether to include word-level timestamps.

        Returns:
            dict: Transcription result.
        """
        # Wait for the model to load
        await asyncio.to_thread(self._model_loaded_event.wait)

        if not self._model:
            raise RuntimeError("Model is not loaded. Cannot transcribe.")

        async with self._model_lock:
            if self._current_audio_path != audio_path:
                return
            try:
                logger.info(f"Starting transcription for {audio_path}...")
                transcription = await asyncio.to_thread(
                    self._model.transcribe, audio_path, word_timestamps=word_timestamps, language=language
                )
                if self._current_audio_path != audio_path:
                    return
                logger.info("Transcription completed successfully.")
                self.notify_listeners(transcription)
            except Exception as e:
                logger.exception("Transcription failed")
                raise RuntimeError(f"Transcription failed: {e}") from e

    def notify_listeners(self, transcription: dict) -> None:
        """
        Notify all registered listeners with the transcription result.

        Args:
            transcription: The transcription result to pass to listeners.
        """
        for listener in self._transcription_listeners:
            listener(transcription)

    def add_transcription_listener(self, listener):
        """
        Adds a listener to be notified when transcription is complete.

        Args:
            listener (callable): A coroutine function to call with the transcription result.
        """
        self._transcription_listeners.append(listener)

    def on_video_changed(self, video_path: str):
        """
        Called when the video changes. Can be used to reset or update the transcription manager.

        Args:
            video_path (str): Path to the new video file.
        """
        self._current_audio_path = video_path
        asyncio.create_task(self.transcribe(video_path))
