"""Shared helpers for test doubles of the LLM client."""
from pydantic import ValidationError


class StructuredFromJson:
    """Gives a fake LLM client complete_structured(), built on its scripted complete_json().

    The fake's scripted JSON goes through the same Pydantic models as production, so tests
    exercise the real validation. There is no repair retry here: a fake that returns invalid
    JSON yields None, the same result as a real client whose repair also failed.
    """

    async def complete_structured(self, system, messages, output, max_tokens=None):
        # Keyword arguments, as production calls it, so fakes with **kwargs signatures work too.
        data = await self.complete_json(system=system, messages=messages, schema_hint="")
        try:
            return output.model_validate(data)
        except ValidationError:
            return None
