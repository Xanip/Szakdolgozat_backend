import logging
import os
import httpx

from szakdolgozat_backend.response_models.ollamaResponses import OllamaGenerateResponse

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "600"))

logger = logging.getLogger(__name__)


async def generate_llm_response(prompt: str) -> str:
    """
    Generate a response using the local Ollama model.
    """

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.0,
                        "num_ctx": 10000,
                    },
                },
            )
            
            response.raise_for_status()

            raw_result = response.json()

            logger.info(
                "Ollama generation completed: "
                "total_duration=%s, "
                "prompt_eval_count=%s, "
                "eval_count=%s, "
                "done_reason=%s",
                raw_result.get("total_duration"),
                raw_result.get("prompt_eval_count"),
                raw_result.get("eval_count"),
                raw_result.get("done_reason"),
            )

            result = OllamaGenerateResponse.model_validate(raw_result)

            if not result.done:
                raise RuntimeError(
                    "Ollama generation did not complete."
                )

            return result.response
    except httpx.HTTPError:
        logger.exception("Ollama request failed")
        raise