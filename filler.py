"""
Supports ANY public Google Form. Pass a viewform URL and the script will:
  1. Scrape the form to discover every field (entry ID, type, options).
  2. Build a random payload using the rules below.
  3. POST the payload N times.

FIELD TYPE MAPPING
  Google type 0  -> "short"    -> random short sentence
  Google type 1  -> "long"     -> random paragraph
  Google type 2  -> "radio"    -> pick ONE random option
  Google type 4  -> "checkbox" -> pick 1..n random options (all eligible)
  Google type 5  -> "dropdown" -> pick ONE random option from the list
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
  python fill.py <viewform_url> <num_responses>

  Example:
    python fill.py https://docs.google.com/forms/d/e/XXX/viewform 30

  No editing of this file is required.
"""

import re
import sys
import json
import time
import random
import urllib.request

try:
    import requests
except ImportError:
    sys.exit("requests is not installed — run: pip install requests")

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
    Build a plausible email from first + last name chosen for this submission.
    Examples for 'Riya Singh':
      riya.singh@gmail.com
      riyasingh42@yahoo.com
      r.singh91@outlook.com
      riya_singh@hotmail.com
    """
    f = _normalize(first_name)
    l = _normalize(last_name)
    n = random.randint(1, 999)
    domain = random.choice(EMAIL_DOMAINS)
    templates = [
        "{}.{}@{}".format(f, l, domain),
        "{}{}{}@{}".format(f, l, n, domain),
        "{}.{}{}@{}".format(f[0], l, n, domain),
        "{}_{}@{}".format(f, l, domain),
    ]
    return random.choice(templates)


# ---------------------------------------------------------------------------
# FORM SCRAPER
# ---------------------------------------------------------------------------
_GTYPE_SHORT    = 0
_GTYPE_LONG     = 1
_GTYPE_RADIO    = 2
_GTYPE_SCALE    = 3   # linear scale / multiple-choice grid — pick one option
_GTYPE_CHECKBOX = 4
_GTYPE_DROPDOWN = 5


def scrape_form(viewform_url):
    """
    Download the viewform page, parse the embedded FB_PUBLIC_LOAD_DATA_ JSON,
    and return a dict describing the form structure.
    """
    req = urllib.request.Request(
        viewform_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; fill.py/2.0)"},
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
    for q in questions_raw:
        try:
            q_title  = q[1]
            g_type   = q[3]
            entry_id = q[4][0][0]
            entry_key = "entry.{}".format(entry_id)

            # Some questions have no title; treat them as empty so heuristics
            # fall through gracefully instead of crashing on None.lower().
            if not isinstance(q_title, str):
                q_title = ""

            raw_options = q[4][0][1] or []
            options = [o[0] for o in raw_options if o and o[0]]

            if g_type in (_GTYPE_RADIO, _GTYPE_SCALE):
                field_type = "radio"
            elif g_type == _GTYPE_DROPDOWN:
                field_type = "dropdown"
            elif g_type == _GTYPE_CHECKBOX:
                field_type = "checkbox"
            elif g_type == _GTYPE_LONG:
                field_type = "long"
            else:
                field_type = "short"

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
        "submit_url": submit_url,
        "title":      form_title,
        "fields":     fields,
    }


# ---------------------------------------------------------------------------
# PAYLOAD BUILDER
# ---------------------------------------------------------------------------

def build_payload(fields):
    """
    Returns a list of (key, value) tuples.
    Checkboxes produce multiple tuples with the same key.

    A single (first_name, last_name) pair is generated once per submission so
    that name fields AND the email field all refer to the same person.
    """
    payload = []

    # One name for the whole submission — email is derived from this.
    first_name, last_name = fake_name_parts()

    for entry_key, cfg in fields.items():
        ftype   = cfg["type"]
        options = cfg["options"]

        if ftype == "name":
            payload.append((entry_key, "{} {}".format(first_name, last_name)))

        elif ftype == "first_name":
            payload.append((entry_key, first_name))

        elif ftype == "last_name":
            payload.append((entry_key, last_name))

        elif ftype == "email":
            # Derived from the same first/last name chosen for this submission
            payload.append((entry_key, fake_email(first_name, last_name)))

        elif ftype == "short":
            payload.append((entry_key, random.choice(SHORT_SENTENCES)))

        elif ftype == "long":
            payload.append((entry_key, random.choice(LONG_PARAGRAPHS)))

        elif ftype == "radio":
            if options:
                payload.append((entry_key, random.choice(options)))

        elif ftype == "dropdown":
            if options:
                payload.append((entry_key, random.choice(options)))

        elif ftype == "checkbox":
            if options:
                k = random.randint(1, len(options))
                for c in random.sample(options, k=k):
                    payload.append((entry_key, c))

    return payload


# ---------------------------------------------------------------------------
# SUBMIT
# ---------------------------------------------------------------------------

def submit_one(submit_url, fields):
    payload = build_payload(fields)
    resp = requests.post(submit_url, data=payload, timeout=15)
    return resp.status_code, payload


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    _USAGE = (
        "Usage: python fill.py <viewform_url> <num_responses>\n"
        "\n"
        "  viewform_url   Full Google Form URL ending in /viewform\n"
        "  num_responses  How many fake responses to submit (positive integer)\n"
        "\n"
        "Example:\n"
        "  python fill.py "
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
        print("Fields    : {} detected".format(len(form["fields"])))
        for ek, cfg in form["fields"].items():
            print("  {:30s}  [{:10s}]  options={}".format(ek, cfg["type"], cfg["options"]))

        submit_url = form["submit_url"]
        fields     = form["fields"]

        print("\nSubmitting {} responses -> {}".format(num_responses, submit_url))
        for i in range(1, num_responses + 1):
            try:
                status, payload = submit_one(submit_url, fields)
                ok = "OK" if status in (200, 302) else "FAILED ({})".format(status)
                print("  [{:>3}/{}] {}  (payload_pairs={})".format(i, num_responses, ok, len(payload)))
            except Exception as exc:
                print("  [{:>3}/{}] ERROR: {}".format(i, num_responses, exc))
            time.sleep(DELAY_BETWEEN_SUBMITS)

    print("\nDone.")


if __name__ == "__main__":
    main()
