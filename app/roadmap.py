from dotenv import load_dotenv
import json
import time
import ollama
from openai import OpenAI, RateLimitError
import os

load_dotenv()
client = OpenAI()
API_ENABLED = os.getenv("OPENAI_API_KEY") is not None


def clean_json_output(raw: str) -> str:
    """
    Removes Markdown fences (```json ... ```) if present
    and returns clean JSON string.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if "```" in raw else raw
        raw = raw.replace("json", "", 1).strip()
    return raw


async def get_gpt_response(prompt: str, retries: int = 5) -> dict:
    """
    Calls OpenAI and returns JSON roadmap (with fixed schema).
    Retries with exponential backoff on rate limit errors.
    """
    global API_ENABLED

    SYSTEM_PROMPT = """
    You are a roadmap builder AI.
    Always return the roadmap in this JSON format, and nothing else:

    {
      "roadmap": {
        "stages": [
          {
            "id": "stage_1",
            "title": "string",
            "goal": "string",
            "topics": ["string", "string"],
            "resources": [
              {"title": "string", "type": "string", "url": "string"}
            ],
            "duration": "string"
          }
        ]
      }
    }

    - Always include at least 3 stages.
    - Ensure valid JSON (no comments, no trailing commas).
    - Do NOT add explanations outside JSON.
    """

    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )

            raw_output = resp.choices[0].message.content.strip()
            clean_output = clean_json_output(raw_output)

            try:
                roadmap = json.loads(clean_output)
            except json.JSONDecodeError:
                roadmap = {"error": "Invalid JSON", "raw": raw_output}

            return roadmap

        except RateLimitError:
            wait_time = 2**attempt
            print(f"⚠️ Rate limit hit. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    API_ENABLED = False
    return {"error": "Max retries reached due to rate limits"}


async def get_ollama_response(prompt: str) -> dict:
    SYSTEM_PROMPT = """
    You are a roadmap builder AI.
    Always return the roadmap in this JSON format, and nothing else:

    {
      "roadmap": {
        "stages": [
          {
            "id": "stage_1",
            "title": "string",
            "goal": "string",
            "topics": ["string", "string"],
            "resources": [
              {"title": "string", "type": "string", "url": "string"}
            ],
            "duration": "string"
          }
        ]
      }
    }

    - Always include at least 3 stages.
    - Ensure valid JSON (no comments, no trailing commas).
    - Do NOT add explanations outside JSON.
    """
    resp = ollama.chat(
        model="llama3",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw_output = resp["message"]["content"].strip()
    clean_output = clean_json_output(raw_output)

    try:
        roadmap = json.loads(clean_output)
    except json.JSONDecodeError:
        roadmap = {"error": "Invalid JSON", "raw": raw_output}

    return roadmap


async def generate_roadmap(prompt: str):
    if API_ENABLED:
        return await get_gpt_response(prompt)
    return await get_ollama_response(prompt)
