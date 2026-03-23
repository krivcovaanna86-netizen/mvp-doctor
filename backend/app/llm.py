"""LLM service for structuring medical text."""

import logging
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, SPECIALTY_TEMPLATES

logger = logging.getLogger(__name__)


async def structure_medical_text(
    transcription: str,
    specialty: str = "general",
) -> str:
    """
    Takes raw transcription text and returns a structured medical document
    using an LLM with carefully crafted prompts.
    """
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )

    # Select specialty template
    template = SPECIALTY_TEMPLATES.get(specialty, SPECIALTY_TEMPLATES["general"])
    system_prompt = template["system_prompt"]

    # Build section hint into the user prompt
    section_hint = "\n".join(f"- {s}" for s in template["sections"])
    enhanced_user_prompt = (
        USER_PROMPT_TEMPLATE.format(transcription=transcription)
        + f"\n\nОбязательные разделы для данного типа приёма ({template['name']}):\n{section_hint}"
    )

    logger.info(f"Sending to LLM ({LLM_MODEL}), specialty={specialty}, text length={len(transcription)}")

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": enhanced_user_prompt},
            ],
            temperature=0.2,  # Low temperature for consistency
            max_tokens=4000,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"LLM response received: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"LLM API error: {e}")
        raise RuntimeError(f"Ошибка обработки текста: {str(e)}") from e


async def structure_medical_text_stream(
    transcription: str,
    specialty: str = "general",
):
    """
    Streaming version — yields chunks of structured medical text.
    """
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )

    template = SPECIALTY_TEMPLATES.get(specialty, SPECIALTY_TEMPLATES["general"])
    system_prompt = template["system_prompt"]

    section_hint = "\n".join(f"- {s}" for s in template["sections"])
    enhanced_user_prompt = (
        USER_PROMPT_TEMPLATE.format(transcription=transcription)
        + f"\n\nОбязательные разделы для данного типа приёма ({template['name']}):\n{section_hint}"
    )

    try:
        stream = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": enhanced_user_prompt},
            ],
            temperature=0.2,
            max_tokens=4000,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    except Exception as e:
        logger.error(f"LLM streaming error: {e}")
        yield f"\n\n⚠️ Ошибка: {str(e)}"
