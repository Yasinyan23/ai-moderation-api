"""OpenAI moderation provider."""
import json
import logging

from openai import AsyncOpenAI

from app.services.ai import AIProvider, ModerationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a content moderation AI. Evaluate the message for: "
    "hate speech, threats, harassment, sexual content, spam. "
    'Respond ONLY with valid JSON: {"safe": bool, "reason": str | null, "severity": "low"|"medium"|"high"|null}. '
    "If safe, set reason and severity to null. "
    "Do not wrap the JSON in markdown code fences or add any other text."
)


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def moderate(self, message: str) -> ModerationResult:
        text = ""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
            )
            text = response.choices[0].message.content or ""
            text = text.strip()

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
            logger.warning("Failed to parse OpenAI response (%s); raw: %s", e, text)
            return ModerationResult(safe=True)
        except Exception as e:
            logger.error("OpenAI moderation error: %s", e)
            return ModerationResult(safe=True)
