import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from gemini_cli import run_gemini_cli


BASE_DIR = Path(__file__).resolve().parent
UPLOADED_FILE = BASE_DIR / "uploaded_topics.json"
WIKIMEDIA_UA = "youtube-bot/1.0 (topic-finder)"

WIKIPEDIA_CATEGORIES = [
    "American_serial_killers",
    "English_serial_killers",
    "Unsolved_murders_in_the_United_States",
    "Cold_cases_in_the_United_States",
    "Spree_killers_in_the_United_States",
    "Crimes_in_the_United_Kingdom",
    "Unsolved_murders_in_the_United_Kingdom",
    "Female_serial_killers",
    "Contract_killers",
    "Cult_leaders",
]

NEWS_QUERIES = [
    "serial killer documentary case",
    "unsolved murder cold case crime",
    "notorious criminal true crime",
]


def load_uploaded() -> set[str]:
    if not UPLOADED_FILE.is_file():
        return set()
    try:
        data = json.loads(UPLOADED_FILE.read_text(encoding="utf-8"))
        return {t.lower().strip() for t in data.get("uploaded", [])}
    except Exception:
        return set()


def fetch_wikipedia_category(category: str, limit: int = 80) -> list[str]:
    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            headers={"User-Agent": WIKIMEDIA_UA},
            params={
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmlimit": limit,
                "cmtype": "page",
                "format": "json",
            },
            timeout=12,
        )
        response.raise_for_status()
        members = response.json().get("query", {}).get("categorymembers", [])
        return [
            m["title"] for m in members
            if ":" not in m["title"] and len(m["title"]) < 60
        ]
    except Exception as exc:
        print(f"  Wikipedia [{category}]: {exc}")
        return []


def fetch_google_news(query: str) -> list[str]:
    try:
        url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return [
            item.text.strip()
            for item in root.findall(".//item/title")
            if item.text
        ]
    except Exception as exc:
        print(f"  Google News [{query}]: {exc}")
        return []


def pick_best_topic(candidates: list[str], uploaded: set[str]) -> str | None:
    fresh = [c for c in candidates if c.lower().strip() not in uploaded]
    if not fresh:
        return None

    # Deduplicate and limit list sent to Gemini
    seen: set[str] = set()
    unique = []
    for c in fresh:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    candidates_text = "\n".join(f"- {c}" for c in unique[:80])
    uploaded_text = ", ".join(sorted(uploaded)) if uploaded else "none yet"

    prompt = (
        "You are selecting the next topic for a true crime YouTube channel called Killer Timeline. "
        "The channel covers serial killers, unsolved murders, notorious criminals, and dark historical cases. "
        f"Already uploaded: {uploaded_text}. "
        "From the candidate list below, pick ONE topic that is:\n"
        "1. A real, well-documented criminal case or person\n"
        "2. Has strong visual storytelling potential\n"
        "3. Is not already covered above\n"
        "4. Is likely to get high YouTube engagement (shocking, mysterious, or famous case)\n\n"
        f"Candidates:\n{candidates_text}\n\n"
        "Reply with ONLY the exact topic name from the list. No explanation, no quotes, no punctuation."
    )

    try:
        result = run_gemini_cli(prompt)
        # Strip any surrounding quotes or whitespace
        topic = result.strip().strip('"').strip("'").strip()
        # Validate it's from our list (case-insensitive)
        topic_lower = topic.lower()
        for candidate in unique:
            if candidate.lower() == topic_lower:
                return candidate
        # If exact match not found, return raw result if it looks reasonable
        if 2 < len(topic) < 80 and topic_lower not in uploaded:
            return topic
    except Exception as exc:
        print(f"  Gemini topic selection failed: {exc}")

    # Fallback: return first fresh candidate
    return unique[0]


def find_topic() -> str | None:
    print("Searching for new true crime topics...")
    uploaded = load_uploaded()

    candidates: list[str] = []

    print("  Fetching Wikipedia categories...")
    for category in WIKIPEDIA_CATEGORIES:
        candidates.extend(fetch_wikipedia_category(category))

    print("  Fetching Google News...")
    for query in NEWS_QUERIES:
        candidates.extend(fetch_google_news(query))

    print(f"  Found {len(candidates)} candidates, {len(uploaded)} already uploaded.")
    topic = pick_best_topic(candidates, uploaded)

    if topic:
        print(f"  Selected: {topic}")
    else:
        print("  No new topics found.")

    return topic


if __name__ == "__main__":
    result = find_topic()
    print(f"\nNext topic: {result}")
