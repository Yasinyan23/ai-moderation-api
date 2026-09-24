import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.services.ai import AIProvider, ModerationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a content moderation AI. Evaluate the message for: "
    "hate speech, threats, harassment, sexual content, spam. "
    'Respond ONLY with valid JSON: {"safe": bool, "reason": str | null, "severity": "low"|"medium"|"high"|null}. '
    "If safe, set reason and severity to null. "
    "Do not wrap the JSON in markdown code fences or add any other text."
)


class ClaudeProvider(AIProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-haiku-4-5-20251001",
    ):
        key = api_key or get_settings().anthropic_api_key
        self._client = AsyncAnthropic(api_key=key)
        self._model = model

    async def moderate(self, message: str) -> ModerationResult:
        text = ""
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message}],
            )
            text = response.content[0].text.strip()

            # strip markdown code fences if Claude wraps the JSON
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
            logger.warning("Failed to parse Claude response (%s); raw: %s", e, text)
            return ModerationResult(safe=True)
