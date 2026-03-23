"""Speech-to-text service using OpenAI Whisper API."""

import logging
from pathlib import Path
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY, OPENAI_BASE_URL

logger = logging.getLogger(__name__)


async def transcribe_audio(file_path: Path, language: str = "ru") -> str:
    """
    Transcribe audio file to text using OpenAI Whisper API.
    
    Falls back to a simulated response if API is not available.
    """
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )

    try:
        with open(file_path, "rb") as audio_file:
            logger.info(f"Sending audio to Whisper API: {file_path.name} ({file_path.stat().st_size} bytes)")
            
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="text",
                prompt="Медицинский приём, разговор врача и пациента. Жалобы, анамнез, осмотр, диагноз, назначения.",
            )
            
            text = response if isinstance(response, str) else response.text
            logger.info(f"Transcription complete: {len(text)} chars")
            return text.strip()

    except Exception as e:
        logger.error(f"Whisper API error: {e}")
        # If the proxy doesn't support whisper, raise the error
        raise RuntimeError(
            f"Ошибка распознавания речи: {str(e)}. "
            "Убедитесь, что API поддерживает endpoint /audio/transcriptions."
        ) from e
