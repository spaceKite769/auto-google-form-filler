# auto-google-form-filler

Automatically submits randomised fake responses to any public Google Form.

---

## How it works

1. Downloads the form page and parses its internal JSON (`FB_PUBLIC_LOAD_DATA_`).
2. Detects every field — short text, long text, radio, checkbox, dropdown — and applies name/email heuristics.
3. Generates a random payload from your data pools and POSTs it as a real form submission.
4. Repeats `N` times with a configurable delay between submissions.

---

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

## Setup

```bash
pip install requests
```

---

## Quickstart

### 1. Customise `customize.py` (optional but recommended)

**`customize.py`** is the only file you ever need to edit. It contains every user-facing setting:

```python
# Seconds to wait between each POST (keep ≥ 1.0 to be polite)
DELAY_BETWEEN_SUBMITS = 1.0

FIRST_NAMES = ["Alice", "Bob", "Carol"]
LAST_NAMES  = ["Smith", "Jones", "Lee"]

EMAIL_DOMAINS = ["gmail.com", "yahoo.com"]

SHORT_SENTENCES = [
    "Looks great!",
    "Really enjoyed it.",
]

LONG_PARAGRAPHS = [
    "I had a wonderful experience overall. The team was very professional...",
]
```

### 2. Run — no other file editing required

Pass the form URL and the number of responses directly on the command line:

```bash
python fill.py <viewform_url> <num_responses>
```

**Example:**

```bash
python fill.py https://docs.google.com/forms/d/e/<ID>/viewform 30
```

| Argument | Description |
|---|---|
| `<viewform_url>` | Full Google Form URL ending in `/viewform` |
| `<num_responses>` | Number of fake responses to submit (positive integer) |

Running without arguments (or with invalid arguments) prints a usage message.

---

## Configuration

All settings live in **`customize.py`**:

| Variable | Description |
|---|---|
| `DELAY_BETWEEN_SUBMITS` | Seconds to wait between POSTs (default `1.0`) |
| `FIRST_NAMES` | Pool of first names |
| `LAST_NAMES` | Pool of last names |
| `EMAIL_DOMAINS` | Pool of email domains |
| `SHORT_SENTENCES` | Pool of short text answers |
| `LONG_PARAGRAPHS` | Pool of long text answers |

> **Note:** The form URL and response count are set exclusively via CLI arguments — there is no hardcoded list to edit in the script.

---

## Field-type detection

| Google type | Detected as | Answer source |
|---|---|---|
| 0 (short text) | `short` / name heuristic | `SHORT_SENTENCES` or name pool |
| 1 (long text) | `long` | `LONG_PARAGRAPHS` |
| 2 (radio) | `radio` | Random option from the form |
| 4 (checkbox) | `checkbox` | Random 1–N options from the form |
| 5 (dropdown) | `dropdown` | Random option from the form |

**Name heuristics** (title-based, checked in order):

- contains `email` → fake email derived from the submission's chosen name
- contains `first name` / `given name` → first name only
- contains `last` / `sur` / `family name` → last name only
- contains `name` (generic, text fields only) → full name

---

## File layout

```
auto-google-form-filler/
├── fill.py   # Main script — do not edit
├── customize.py                 # ← Edit this: names, text pools, delay
├── LICENSE
└── README.md
```
---

## Disclaimer

Use only on forms you own or have explicit permission to test. Submitting spam responses to third-party forms without consent may violate Google's Terms of Service and applicable laws.
