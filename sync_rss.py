#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from ingest_transcript import ingest_transcript_file


DEFAULT_RSS_URL = "https://rss.beehiiv.com/podcasts/019d2587-e790-7b44-bb7a-6eebcaae225c.xml"
USER_AGENT = "AppleCoreMedia"
TRANSCRIBE_SCRIPT = Path(__file__).with_name("transcribe.py")
RUNPOD_CLIENT_SCRIPT = Path(__file__).with_name("runpod_client.py")


def fetch_rss_xml(url: str) -> bytes:
    result = subprocess.run(
        ["curl", "-fsSL", "-A", USER_AGENT, url],
        check=True,
        capture_output=True,
    )
    return result.stdout


def first_text(item: ET.Element, tag: str) -> str | None:
    element = item.find(tag)
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def first_text_ns(item: ET.Element, namespace: str, tag: str) -> str | None:
    return first_text(item, f"{{{namespace}}}{tag}")


def clean_description(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", unescape(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_duration(value: str | None) -> int | None:
    if not value:
        return None

    parts = value.strip().split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 2:
            minutes, seconds = parts
            return (int(minutes) * 60) + int(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return (int(hours) * 3600) + (int(minutes) * 60) + int(seconds)
    except ValueError:
        return None

    return None


def parse_episode_items(xml_data: bytes) -> list[dict[str, object]]:
    root = ET.fromstring(xml_data)
    episodes = []

    itunes_namespace = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    content_namespace = "http://purl.org/rss/1.0/modules/content/"
    podcast_description = clean_description(first_text(root, "./channel/description"))

    for item in root.findall("./channel/item"):
        title = first_text(item, "title")
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None

        if not title or not audio_url:
            continue

        published_at = None
        pub_date = first_text(item, "pubDate")
        if pub_date:
            try:
                published_at = parsedate_to_datetime(pub_date)
            except (TypeError, ValueError):
                published_at = None

        duration = parse_duration(first_text_ns(item, itunes_namespace, "duration"))
        description = clean_description(
            first_text_ns(item, content_namespace, "encoded") or first_text(item, "description")
        )

        episodes.append(
            {
                "title": title,
                "podcast_description": podcast_description,
                "description": description,
                "published_at": published_at,
                "audio_url": audio_url,
                "duration": duration,
            }
        )

    return episodes


def get_indexed_audio_urls(database_url: str) -> set[str]:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT audio_url FROM episodes")
            return {row[0] for row in cursor.fetchall()}


def transcript_path_from_process(result: subprocess.CompletedProcess[bytes]) -> Path:
    output = result.stdout.decode().strip()
    if not output:
        raise RuntimeError("Transcription command did not print a transcript path")
    return Path(output.splitlines()[-1])


def transcribe_episode(
    audio_url: str,
    episode_description: str | None = None,
    podcast_description: str | None = None,
) -> Path:
    execution_mode = os.getenv("TRANSCRIBE_EXECUTION", "local").strip().lower()
    if execution_mode == "runpod":
        command = [sys.executable, str(RUNPOD_CLIENT_SCRIPT), audio_url]
        if podcast_description:
            command.extend(["--podcast-description", podcast_description])
        if episode_description:
            command.extend(["--episode-description", episode_description])
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
        )
        return transcript_path_from_process(result)

    if execution_mode != "local":
        raise ValueError("TRANSCRIBE_EXECUTION must be 'local' or 'runpod'")

    command = [sys.executable, str(TRANSCRIBE_SCRIPT), audio_url]
    if podcast_description:
        command.extend(["--podcast-description", podcast_description])
    if episode_description:
        command.extend(["--episode-description", episode_description])
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    return transcript_path_from_process(result)


def main() -> int:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL missing. Add it to .env or export it.", file=sys.stderr)
        return 1

    rss_url = os.getenv("RSS_URL", DEFAULT_RSS_URL)
    xml_data = fetch_rss_xml(rss_url)
    rss_episodes = parse_episode_items(xml_data)
    indexed_audio_urls = get_indexed_audio_urls(database_url)

    for episode in rss_episodes:
        if episode["audio_url"] not in indexed_audio_urls:
            print(episode["title"])
            transcript_path = transcribe_episode(
                str(episode["audio_url"]),
                str(episode["description"]) if episode.get("description") else None,
                str(episode["podcast_description"]) if episode.get("podcast_description") else None,
            )
            ingest_transcript_file(transcript_path, episode, database_url)
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
