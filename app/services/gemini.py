"""Google Gemini moderation provider."""
import json
import logging

import google.generativeai as genai

from app.services.ai import AIProvider, ModerationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a content moderation AI. Evaluate the message for: "
    "hate speech, threats, harassment, sexual content, spam. "
    'Respond ONLY with valid JSON: {"safe": bool, "reason": str | null, "severity": "low"|"medium"|"high"|null}. '
    "If safe, set reason and severity to null. "
    "Do not wrap the JSON in markdown code fences or add any other text."
)


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self._model_name = model

    async def moderate(self, message: str) -> ModerationResult:
        text = ""
        try:
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=_SYSTEM_PROMPT,
            )
            response = await model.generate_content_async(message)
            text = response.text.strip()

            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(lines[1:-1]).strip()

            data = json.loads(text)
            return ModerationResult(
                safe=bool(data["safe"]),
                reason=data.get("reason"),
                severity=data.get("severity"),
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("Failed to parse Gemini response (%s); raw: %s", e, text)
            return ModerationResult(safe=True)
        except Exception as e:
            logger.error("Gemini moderation error: %s", e)
            return ModerationResult(safe=True)
