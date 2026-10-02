"""
Supports ANY public Google Form. Pass a viewform URL and the script will:
  1. Scrape the form to discover every field (entry ID, type, options).
  2. Build a random payload using the rules below.
  3. POST the payload N times.

FIELD TYPE MAPPING
  Google type 0  -> "short"          -> random short sentence
  Google type 1  -> "long"           -> random paragraph
  Google type 2  -> "radio"          -> pick ONE random option
  Google type 4  -> "checkbox"       -> pick 1..n random options (all eligible)
  Google type 5  -> "dropdown"       -> pick ONE random option from the list
  Google type 5  -> "scale"          -> pick a value within the linear scale
  Google type 7  -> "grid_radio"     -> one random column per row
  Google type 7  -> "grid_checkbox"  -> 1..n random columns per row
  Google type 8  -> (section break)  -> multi-page navigation
  Google type 9  -> "date"           -> random date
  Google type 10 -> "time"           -> random time
  Google type 18 -> "rating"         -> random rating 1..max
  Heuristic: if the question title contains "first" + "name"
             the field is treated as "first_name" -> random first name.
  Heuristic: if the question title contains "last"/"sur" + "name"
             the field is treated as "last_name"  -> random last name.
  Heuristic: if the question title contains "name" (generic)
             the field is treated as "name" -> random full name.
  Heuristic: if the question title contains "email" (case-insensitive)
             the field is treated as "email" -> derived from the first + last
             name chosen for that SAME submission (e.g. riya.singh@gmail.com).

CUSTOMISATION
  Edit customize.py to change names, email domains, filler text, and the
  delay between submissions. That file is the only one you ever need to edit.

USAGE
  pip install requests
  python main.py <viewform_url> <num_responses>

  Example:
    python main.py https://docs.google.com/forms/d/e/XXX/viewform 30

  No editing of this file is required.
"""

import re
import sys
import json
import time
import random
import logging
import urllib.request
from datetime import date, timedelta

try:
    import requests
except ImportError:
    sys.exit("requests is not installed — run: pip install requests")

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("filler")

# ---------------------------------------------------------------------------
# SETTINGS & FAKE DATA POOLS  (edit customize.py to change these)
# ---------------------------------------------------------------------------
try:
    from customize import (
        DELAY_BETWEEN_SUBMITS,
        FIRST_NAMES,
        LAST_NAMES,
        EMAIL_DOMAINS,
        SHORT_SENTENCES,
        LONG_PARAGRAPHS,
        DATE_RANGE_START,
        DATE_RANGE_END,
        TIME_RANGE_START,
        TIME_RANGE_END,
    )
except ImportError:
    sys.exit(
        "customize.py not found.\n"
        "Make sure customize.py is in the same directory as this script."
    )






def _normalize(text):
    """Lowercase and strip non-alphanumeric chars to make a clean email part."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def fake_name_parts():
    """Return (first_name, last_name) as separate strings."""
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def fake_name():
    first, last = fake_name_parts()
    return "{} {}".format(first, last)


def fake_email(first_name, last_name):
    """
    Build a realistic-looking email from first + last name.

    Rules applied:
      - Only alphanumeric chars (no underscores, no dots as main separator)
      - Numbers are always included to look natural
      - Mix of first-last and last-first orderings
      - Initials (1-2 chars) combined with the other name + digits
      - A dot separator used only ~15% of the time, never underscore
      - Numbers chosen to resemble birth years or short random suffixes

    Examples for 'Arjun Mehta':
      ajmehta2003@gmail.com
      mehtaarj97@yahoo.com
      amehta2847@gmail.com
      arjun2004me@outlook.com
    """
    f = _normalize(first_name)
    l = _normalize(last_name)

    # Numbers that look natural: birth-year, 2-digit, or longer suffix
    num = random.choice([
        str(random.randint(1990, 2005)),
        str(random.randint(10, 99)),
        str(random.randint(100, 9999)),
    ])

    f1 = f[0]
    f2 = f[:2] if len(f) >= 2 else f
    l1 = l[0]
    l2 = l[:2] if len(l) >= 2 else l

    domain = random.choice(EMAIL_DOMAINS)

    # Dot used rarely (~15% chance), never underscore
    def _sep():
        return "." if random.random() < 0.15 else ""

    templates = [
        "{}{}{}{}@{}".format(f2, l, _sep(), num, domain),   # ajmehta2003
        "{}{}{}{}@{}".format(l, f2, _sep(), num, domain),   # mehtaaj97
        "{}{}{}{}@{}".format(l, _sep(), f, num, domain),    # mehta.arjun2003
        "{}{}{}@{}".format(f1, l, num, domain),             # amehta2847
        "{}{}{}@{}".format(l1, f, num, domain),             # marjun1999
        "{}{}{}@{}".format(f, l2, num, domain),             # arjunme2004
        "{}{}{}@{}".format(l, f2, num, domain),             # mehtaaj2001
        "{}{}{}@{}".format(f2, l2, num, domain),            # ajme98
    ]
    return random.choice(templates)


# ---------------------------------------------------------------------------
# FORM SCRAPER
# ---------------------------------------------------------------------------
_GTYPE_SHORT    = 0
_GTYPE_LONG     = 1
_GTYPE_RADIO    = 2
_GTYPE_SCALE    = 3   # linear scale — pick one option (NOTE: g_type 5 with scale labels also maps here)
_GTYPE_CHECKBOX = 4
_GTYPE_DROPDOWN = 5
_GTYPE_GRID     = 7   # multiple-choice grid (radio) or checkbox grid
_GTYPE_SECTION  = 8   # section / page break
_GTYPE_DATE     = 9   # date field
_GTYPE_TIME     = 10  # time field
_GTYPE_RATING   = 18  # star / heart / thumb rating


def scrape_form(viewform_url):
    """
    Download the viewform page, parse the embedded FB_PUBLIC_LOAD_DATA_ JSON,
    and return a dict describing the form structure.

    Returns:
        {
            "submit_url": str,
            "title":      str,
            "fields":     {entry_key: {title, type, options, ...}},
            "page_count": int,   # number of pages (sections + 1)
        }
    """
    req = urllib.request.Request(
        viewform_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; main.py/3.0)"},
    )
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

    m = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>", html, re.DOTALL)
    if not m:
        raise RuntimeError(
            "Could not find FB_PUBLIC_LOAD_DATA_ in:\n  {}\n"
            "Make sure the URL is a public 'viewform' link.".format(viewform_url)
        )

    raw = json.loads(m.group(1))

    submit_url = re.sub(r"\?.*$", "", viewform_url.replace("viewform", "formResponse"))
    form_title = raw[3] if len(raw) > 3 and isinstance(raw[3], str) else "Unknown Form"
    questions_raw = raw[1][1]

    fields = {}
    page_count = 1  # at least one page

    for q in questions_raw:
        try:
            q_title  = q[1]
            g_type   = q[3]

            # Some questions have no title; treat them as empty so heuristics
            # fall through gracefully instead of crashing on None.lower().
            if not isinstance(q_title, str):
                q_title = ""

            # ---------------------------------------------------------------
            # Section break (page divider) — not a question, just count pages
            # ---------------------------------------------------------------
            if g_type == _GTYPE_SECTION:
                page_count += 1
                log.info("Section break detected: '%s' (page %d starts)", q_title, page_count)
                continue

            # ---------------------------------------------------------------
            # Grid (radio or checkbox) — multiple rows, each its own entry
            # ---------------------------------------------------------------
            if g_type == _GTYPE_GRID:
                q4 = q[4] or []
                for row in q4:
                    entry_id  = row[0]
                    entry_key = "entry.{}".format(entry_id)
                    raw_opts  = row[1] or []
                    columns   = [o[0] for o in raw_opts if o and o[0]]
                    row_label = row[3][0] if row[3] else ""

                    # row[11] = [0] for radio grid, [1] for checkbox grid
                    is_checkbox = (
                        len(row) > 11
                        and row[11] is not None
                        and isinstance(row[11], list)
                        and row[11][0] == 1
                    )
                    grid_type = "grid_checkbox" if is_checkbox else "grid_radio"

                    fields[entry_key] = {
                        "title":     "{} — {}".format(q_title, row_label),
                        "type":      grid_type,
                        "options":   columns,
                        "row_label": row_label,
                    }
                    log.info("  Grid row: '%s' [%s] columns=%s", row_label, grid_type, columns)
                continue

            # ---------------------------------------------------------------
            # Date field
            # ---------------------------------------------------------------
            if g_type == _GTYPE_DATE:
                q4_sub = q[4][0] if q[4] else None
                if q4_sub is None:
                    continue
                entry_id  = q4_sub[0]
                entry_key = "entry.{}".format(entry_id)
                # q4_sub[7] = [0, 1] means include year; [0] means no year
                date_flags = q4_sub[7] if len(q4_sub) > 7 and q4_sub[7] else [0]
                include_year = len(date_flags) > 1 and date_flags[1] == 1

                fields[entry_key] = {
                    "title":        q_title,
                    "type":         "date",
                    "options":      [],
                    "include_year": include_year,
                }
                log.info("  Date field: entry=%s include_year=%s", entry_id, include_year)
                continue

            # ---------------------------------------------------------------
            # Time field
            # ---------------------------------------------------------------
            if g_type == _GTYPE_TIME:
                q4_sub = q[4][0] if q[4] else None
                if q4_sub is None:
                    continue
                entry_id  = q4_sub[0]
                entry_key = "entry.{}".format(entry_id)
                # q4_sub[6] = [0] for time-of-day, [1] for duration
                time_flags = q4_sub[6] if len(q4_sub) > 6 and q4_sub[6] else [0]
                is_duration = len(time_flags) > 0 and time_flags[0] == 1

                fields[entry_key] = {
                    "title":       q_title,
                    "type":        "time",
                    "options":     [],
                    "is_duration": is_duration,
                }
                log.info("  Time field: entry=%s is_duration=%s", entry_id, is_duration)
                continue

            # ---------------------------------------------------------------
            # Rating (g_type 18)
            # ---------------------------------------------------------------
            if g_type == _GTYPE_RATING:
                q4_sub = q[4][0] if q[4] else None
                if q4_sub is None:
                    continue
                entry_id  = q4_sub[0]
                entry_key = "entry.{}".format(entry_id)
                raw_opts  = q4_sub[1] or []
                options   = [o[0] for o in raw_opts if o and o[0]]
                max_val   = len(options)

                fields[entry_key] = {
                    "title":   q_title,
                    "type":    "rating",
                    "options": options,
                    "max_val": max_val,
                }
                log.info("  Rating field: entry=%s max=%d", entry_id, max_val)
                continue

            # ---------------------------------------------------------------
            # All other types: short, long, radio, scale, checkbox, dropdown
            # (preserves existing logic exactly)
            # ---------------------------------------------------------------
            entry_id = q[4][0][0]
            entry_key = "entry.{}".format(entry_id)

            raw_options = q[4][0][1] or []
            options = [o[0] for o in raw_options if o and o[0]]

            # Linear scale (g_type 5 with scale labels, or g_type 3)
            if g_type in (_GTYPE_SCALE, _GTYPE_DROPDOWN) and g_type == _GTYPE_SCALE:
                field_type = "scale"
            elif g_type == _GTYPE_DROPDOWN:
                # g_type 5 can be dropdown OR linear scale.
                # Linear scales have labels in q[4][0][3] (a list like ["low","high"]).
                scale_labels = q[4][0][3] if len(q[4][0]) > 3 else None
                if scale_labels and isinstance(scale_labels, list):
                    field_type = "scale"
                else:
                    field_type = "dropdown"
            elif g_type in (_GTYPE_RADIO,):
                field_type = "radio"
            elif g_type == _GTYPE_CHECKBOX:
                field_type = "checkbox"
            elif g_type == _GTYPE_LONG:
                field_type = "long"
            elif g_type == _GTYPE_SHORT:
                field_type = "short"
            else:
                # Unknown type — log and skip
                log.warning(
                    "Unknown question type %d for '%s' (entry %s) — skipping.",
                    g_type, q_title, entry_id,
                )
                continue

            # Safety net: if an unknown type slipped through but the field has
            # predefined options, treat it as "radio" so we pick a valid choice
            # instead of sending free text and getting a 400.
            if field_type in ("short", "long") and options:
                field_type = "radio"

            title_lower = q_title.lower()

            # Heuristic: email field (checked first so "email" beats "name")
            if re.search(r"\bemail\b", title_lower):
                field_type = "email"

            # Heuristic: first-name-only field
            elif re.search(r"first.{0,10}name|given.{0,10}name", title_lower):
                field_type = "first_name"

            # Heuristic: last / surname field
            elif re.search(r"(last|sur|family).{0,10}name", title_lower):
                field_type = "last_name"

            # Heuristic: generic full-name field (short/long text only)
            elif field_type in ("short", "long") and re.search(r"\bname\b", title_lower):
                field_type = "name"

            fields[entry_key] = {
                "title":   q_title,
                "type":    field_type,
                "options": options,
            }
        except (IndexError, TypeError):
            continue

    return {
        "submit_url":  submit_url,
        "title":       form_title,
        "fields":      fields,
        "page_count":  page_count,
    }


# ---------------------------------------------------------------------------
# PAYLOAD BUILDER
# ---------------------------------------------------------------------------

def _random_date():
    """Return a random (year, month, day) tuple within the configured range."""
    start = date.fromisoformat(DATE_RANGE_START)
    end   = date.fromisoformat(DATE_RANGE_END)
    delta = (end - start).days
    d = start + timedelta(days=random.randint(0, max(delta, 0)))
    return d.year, d.month, d.day


def _random_time():
    """Return a random (hour, minute) tuple within the configured range."""
    sh, sm = (int(x) for x in TIME_RANGE_START.split(":"))
    eh, em = (int(x) for x in TIME_RANGE_END.split(":"))
    start_min = sh * 60 + sm
    end_min   = eh * 60 + em
    total = random.randint(start_min, max(end_min, start_min))
    return total // 60, total % 60


def build_payload(fields, page_count=1):
    """
    Returns a list of (key, value) tuples.
    Checkboxes and grid-checkbox rows produce multiple tuples with the same key.

    A single (first_name, last_name) pair is generated once per submission so
    that name fields AND the email field all refer to the same person.

    Adds ``pageHistory`` for multi-page forms.
    """
    payload = []

    # One name for the whole submission — email is derived from this.
    first_name, last_name = fake_name_parts()

    for entry_key, cfg in fields.items():
        ftype   = cfg["type"]
        options = cfg["options"]

        if ftype == "name":
            val = "{} {}".format(first_name, last_name)
            payload.append((entry_key, val))
            log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "first_name":
            payload.append((entry_key, first_name))
            log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, first_name)

        elif ftype == "last_name":
            payload.append((entry_key, last_name))
            log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, last_name)

        elif ftype == "email":
            # Derived from the same first/last name chosen for this submission
            val = fake_email(first_name, last_name)
            payload.append((entry_key, val))
            log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "short":
            val = random.choice(SHORT_SENTENCES)
            payload.append((entry_key, val))
            log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "long":
            val = random.choice(LONG_PARAGRAPHS)
            payload.append((entry_key, val))
            log.info("  %-30s [%-14s] -> %.40s…", cfg["title"][:30], ftype, val)

        elif ftype == "radio":
            if options:
                val = random.choice(options)
                payload.append((entry_key, val))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "dropdown":
            if options:
                val = random.choice(options)
                payload.append((entry_key, val))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "checkbox":
            if options:
                k = random.randint(1, len(options))
                chosen = random.sample(options, k=k)
                for c in chosen:
                    payload.append((entry_key, c))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, chosen)

        # -------------------------------------------------------------------
        # NEW TYPES
        # -------------------------------------------------------------------

        elif ftype == "scale":
            if options:
                val = random.choice(options)
                payload.append((entry_key, val))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "rating":
            max_val = cfg.get("max_val", 5)
            val = str(random.randint(1, max(max_val, 1)))
            payload.append((entry_key, val))
            log.info("  %-30s [%-14s] -> %s/%s", cfg["title"][:30], ftype, val, max_val)

        elif ftype == "date":
            year, month, day = _random_date()
            # Google Forms expects separate _year, _month, _day params
            # keyed off the base entry ID.
            payload.append((entry_key + "_year", str(year)))
            payload.append((entry_key + "_month", str(month)))
            payload.append((entry_key + "_day", str(day)))
            log.info("  %-30s [%-14s] -> %04d-%02d-%02d", cfg["title"][:30], ftype, year, month, day)

        elif ftype == "time":
            hour, minute = _random_time()
            payload.append((entry_key + "_hour", str(hour)))
            payload.append((entry_key + "_minute", str(minute)))
            log.info("  %-30s [%-14s] -> %02d:%02d", cfg["title"][:30], ftype, hour, minute)

        elif ftype == "grid_radio":
            if options:
                val = random.choice(options)
                payload.append((entry_key, val))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, val)

        elif ftype == "grid_checkbox":
            if options:
                k = random.randint(1, len(options))
                chosen = random.sample(options, k=k)
                for c in chosen:
                    payload.append((entry_key, c))
                log.info("  %-30s [%-14s] -> %s", cfg["title"][:30], ftype, chosen)

        else:
            log.warning("  Unhandled field type '%s' for '%s' — skipping.", ftype, cfg["title"])

    # Multi-page: send pageHistory so the server accepts all fields at once.
    if page_count > 1:
        page_history = ",".join(str(i) for i in range(page_count))
        payload.append(("pageHistory", page_history))
        log.info("  %-30s [%-14s] -> %s", "(multi-page)", "pageHistory", page_history)

    return payload


# ---------------------------------------------------------------------------
# SUBMIT
# ---------------------------------------------------------------------------

def submit_one(submit_url, fields, page_count=1):
    payload = build_payload(fields, page_count=page_count)
    resp = requests.post(submit_url, data=payload, timeout=15)
    return resp.status_code, payload


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    _USAGE = (
        "Usage: python main.py <viewform_url> <num_responses>\n"
        "\n"
        "  viewform_url   Full Google Form URL ending in /viewform\n"
        "  num_responses  How many fake responses to submit (positive integer)\n"
        "\n"
        "Example:\n"
        "  python main.py "
        "https://docs.google.com/forms/d/e/XXX/viewform 30\n"
    )

    if len(sys.argv) < 3 or not sys.argv[1].startswith("http"):
        sys.exit(_USAGE)

    viewform_url = sys.argv[1]

    try:
        num_responses = int(sys.argv[2])
        if num_responses < 1:
            raise ValueError
    except ValueError:
        sys.exit("Error: <num_responses> must be a positive integer.\n\n" + _USAGE)

    forms = [(viewform_url, num_responses)]

    for viewform_url, num_responses in forms:
        print("\n" + "=" * 64)
        print("Scraping  : " + viewform_url)

        try:
            form = scrape_form(viewform_url)
        except Exception as exc:
            print("  ERROR: " + str(exc))
            continue

        print("Title     : " + form["title"])
        print("Pages     : {}".format(form["page_count"]))
        print("Fields    : {} detected".format(len(form["fields"])))
        for ek, cfg in form["fields"].items():
            print("  {:30s}  [{:14s}]  options={}".format(ek, cfg["type"], cfg["options"]))

        submit_url  = form["submit_url"]
        fields      = form["fields"]
        page_count  = form["page_count"]

        print("\nSubmitting {} responses -> {}".format(num_responses, submit_url))
        for i in range(1, num_responses + 1):
            try:
                status, payload = submit_one(submit_url, fields, page_count=page_count)
                ok = "OK" if status in (200, 302) else "FAILED ({})".format(status)
                print("  [{:>3}/{}] {}  (payload_pairs={})".format(i, num_responses, ok, len(payload)))
            except Exception as exc:
                print("  [{:>3}/{}] ERROR: {}".format(i, num_responses, exc))
            time.sleep(DELAY_BETWEEN_SUBMITS)

    print("\nDone.")


if __name__ == "__main__":
    main()
