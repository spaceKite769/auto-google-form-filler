# auto-google-form-filler

Automatically submits randomised fake responses to any public Google Form.

## Disclaimer

Use only on forms you own or have explicit permission to test. Submitting spam responses to third-party forms without consent may violate Google's Terms of Service and applicable laws.## How it works
## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

## Setup

```bash
git clone https://github.com/spaceKite769/auto-google-form-filler.git
cd auto-google-form-filler
pip install requests
```

---

## Quickstart

### 1. Customise `customize.py` (optional but recommended)

**`customize.py`** is the only file you ever need to edit. It contains every user-facing setting:

### 2. Run — no other file editing required

Pass the form URL and the number of responses directly on the command line:

```bash
python src/main.py <viewform_url> <num_responses>
```

**Example:**

```bash
python src/main.py https://docs.google.com/forms/d/e/<ID>/viewform 30
```

| Argument | Description |
|---|---|
| `src/main.py` | Path to main.py |
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
| `DATE_RANGE_START` | Start of random date range (`YYYY-MM-DD`, default `2000-01-01`) |
| `DATE_RANGE_END` | End of random date range (`YYYY-MM-DD`, default `2025-12-31`) |
| `TIME_RANGE_START` | Start of random time range (`HH:MM` 24h, default `08:00`) |
| `TIME_RANGE_END` | End of random time range (`HH:MM` 24h, default `22:00`) |

> **Note:** The form URL and response count are set exclusively via CLI arguments — there is no hardcoded list to edit in the script.

---

## How it works

1. Downloads the form page and parses its internal JSON (`FB_PUBLIC_LOAD_DATA_`).
2. Detects every field — short text, long text, radio, checkbox, dropdown — and applies name/email heuristics.
3. Generates a random payload from your data pools and POSTs it as a real form submission.
4. Repeats `N` times with a configurable delay between submissions.

---

## Field-type detection

| Google type | Detected as | Answer source |
|---|---|---|
| 0 (short text) | `short` / name heuristic | `SHORT_SENTENCES` or name pool |
| 1 (long text) | `long` | `LONG_PARAGRAPHS` |
| 2 (radio) | `radio` | Random option from the form |
| 4 (checkbox) | `checkbox` | Random 1–N options from the form |
| 5 (dropdown) | `dropdown` | Random option from the form |
| 5 (linear scale) | `scale` | Random value within scale range |
| 7 (grid – radio) | `grid_radio` | One random column per row |
| 7 (grid – checkbox) | `grid_checkbox` | 1–N random columns per row |
| 8 (section break) | _(page divider)_ | N/A (drives multi-page navigation) |
| 9 (date) | `date` | Random date from `DATE_RANGE_*` |
| 10 (time) | `time` | Random time from `TIME_RANGE_*` |
| 18 (rating) | `rating` | Random value 1–max |
