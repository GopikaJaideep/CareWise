"""Streaming a reply to the user as the model writes it, without skipping the safety filter.

The chat stream endpoint opens a ReplySink for the request. LLMClient.complete(..., stream=True),
used only for the text a person reads (never for routing, the risk screen or extraction), then
feeds the sink as chunks arrive. Agents don't change: they still get the full text back.

The sink releases text one sentence at a time, and only after the sentence passes the same output
filter as the final reply (app/core/safety.validate_response: no doses, diagnoses or cure promises).
If a sentence fails, nothing more is released and the final reply, filtered as always, replaces the
preview. Internal markers such as "[HANDOFF: safety]" are never released.

What streams is a preview: the final reply (with source links, notes and any safety replacement)
is sent at the end and is what the app shows and saves.
"""
from __future__ import annotations

import asyncio
import re
from contextvars import ContextVar

from app.core.safety import validate_response

_current_sink: ContextVar["ReplySink | None"] = ContextVar("carewise_reply_sink", default=None)

# The end of a complete sentence (or line) in the text so far.
_SENTENCE_END = re.compile(r"[.!?][\"')\]]*\s|\n")
_MARKER = re.compile(r"\[HANDOFF:[^\]]*\]?", re.I)


class ReplySink:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        self._buffer = ""
        self._released_any = False
        self._separate_next = False
        self.blocked = False

    # --- called by LLMClient --------------------------------------------------------------------

    def start(self) -> None:
        """A new streamed reply begins (e.g. the second agent of a multi-request message)."""
        if self._released_any:
            self._separate_next = True

    def feed(self, chunk: str) -> None:
        if self.blocked:
            return
        self._buffer += chunk
        last_end = None
        for match in _SENTENCE_END.finditer(self._buffer):
            last_end = match.end()
        if last_end is not None:
            ready, self._buffer = self._buffer[:last_end], self._buffer[last_end:]
            # Check each sentence on its own, so a safe sentence isn't held back by an unsafe one
            # that arrived in the same chunk.
            start = 0
            for match in _SENTENCE_END.finditer(ready):
                self._release(ready[start:match.end()])
                start = match.end()

    def end(self) -> None:
        """The streamed reply is complete: release what's left (it may lack final punctuation)."""
        if self._buffer and not self.blocked:
            self._release(self._buffer)
        self._buffer = ""

    # --- internal -------------------------------------------------------------------------------

    def _release(self, text: str) -> None:
        if self.blocked:
            return
        text = _MARKER.sub("", text)
        if not text.strip():
            return
        ok, reason = validate_response(text)
        if not ok:
            # Stop previewing; the final reply is filtered and replaces what was shown.
            self.blocked = True
            self.queue.put_nowait(("blocked", reason or ""))
            return
        if self._separate_next:
            text = "\n\n" + text.lstrip()
            self._separate_next = False
        self._released_any = True
        self.queue.put_nowait(("delta", text))


def current_sink() -> ReplySink | None:
    return _current_sink.get()


def open_sink(sink: ReplySink):
    """Make `sink` receive streamed text for model calls in the current context."""
    return _current_sink.set(sink)
