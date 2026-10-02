"""
customize.py – All user-facing settings for main.py

This is the ONLY file you need to edit.
The main script (main.py) reads everything from here.

  • Add/remove names, domains, and text to expand or narrow the fake-data pools.
  • Adjust DELAY_BETWEEN_SUBMITS if you want faster or slower submissions.
"""

# ---------------------------------------------------------------------------
# BEHAVIOUR
# ---------------------------------------------------------------------------

# Seconds to wait between each form POST.
# Keep this at 1.0 or higher to avoid hammering the server.
DELAY_BETWEEN_SUBMITS = 1.0

# ---------------------------------------------------------------------------
# NAMES
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "first_name_here",
]

LAST_NAMES = [
    "last_name_here",
]

# ---------------------------------------------------------------------------
# EMAIL DOMAINS
# ---------------------------------------------------------------------------

EMAIL_DOMAINS = [
    "gmail.com",
]

# ---------------------------------------------------------------------------
# TEXT FILLERS
# ---------------------------------------------------------------------------

# Used for short-answer / text fields
SHORT_SENTENCES = [
    "...",
]

# Used for paragraph / long-answer fields
LONG_PARAGRAPHS = [
    "...",
]

# ---------------------------------------------------------------------------
# DATE SETTINGS
# ---------------------------------------------------------------------------

# Random dates will fall within this range (inclusive).
# Format: YYYY-MM-DD
DATE_RANGE_START = "2000-01-01"
DATE_RANGE_END   = "2025-12-31"

# ---------------------------------------------------------------------------
# TIME SETTINGS
# ---------------------------------------------------------------------------

# Random times will fall within this range (inclusive, 24-hour format).
# Format: HH:MM
TIME_RANGE_START = "08:00"
TIME_RANGE_END   = "22:00"
