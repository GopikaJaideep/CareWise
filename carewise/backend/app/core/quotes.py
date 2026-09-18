"""Positive, caregiver-relevant quotes used in reminders and the dashboard."""
import hashlib
import random
from datetime import date

POSITIVE_QUOTES: list[str] = [
    "You don't have to be perfect to be a wonderful caregiver.",
    "Rest is not a reward for finishing — it's part of the work.",
    "You are allowed to take up space in your own life too.",
    "Small acts of care, repeated daily, are what actually hold a family together.",
    "It's okay to not be okay today. Tomorrow gets to be different.",
    "Asking for help is not giving up — it's how you keep going.",
    "You can't pour from an empty cup. Filling yours isn't selfish.",
    "Whatever today looked like, showing up was enough.",
    "Your presence matters more than your perfection.",
    "One deep breath, right now, counts as self-care too.",
    "Caregiving is love with its sleeves rolled up.",
    "You're doing a hard thing well, even on the days it doesn't feel like it.",
    "The fact that you're worried about doing enough means you're doing enough.",
    "Grief and gratitude can sit in the same room. Both are allowed.",
    "You are someone's whole world today — including your own.",
    "Progress isn't always visible. Keep going anyway.",
    "It's okay to grieve the plans that changed.",
    "You are stronger than the moment that's testing you.",
    "A five-minute pause is still a pause worth taking.",
    "Someone, somewhere, is grateful you exist — even if they haven't said it today.",
]


def quote_of_the_day(seed_key: str | None = None) -> str:
    """A deterministic-per-day quote, optionally varied per user/subscription key."""
    today = date.today().isoformat()
    basis = f"{today}:{seed_key or ''}"
    idx = int(hashlib.sha256(basis.encode()).hexdigest(), 16) % len(POSITIVE_QUOTES)
    return POSITIVE_QUOTES[idx]


def random_quote() -> str:
    return random.choice(POSITIVE_QUOTES)
