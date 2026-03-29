"""Test connectivity to each OpenRouter model used in the processing pipeline."""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

MODELS = [
    "stepfun/step-3.5-flash:free",
    "google/gemma-3-4b-it:free",
    "arcee-ai/trinity-large-preview:free",
]

PROMPT = (
    "What are the most significant AI advancements in the past 6 months? "
    "Summarize the top 3 in a few sentences each."
)


def test_model(model: str, api_key: str) -> bool:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.7,
        "max_tokens": 512,
    }

    print(f"Model: {model}")
    print(f"{'─' * 60}")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if response.status_code == 429:
            print("[RATE LIMITED] Model exists but is temporarily rate-limited upstream\n")
            return True
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if content is None:
            print("[OK] Model reachable but returned empty content\n")
        else:
            print(content.strip())
            print()
        return True
    except requests.exceptions.HTTPError as e:
        print(f"[FAIL] HTTP {e.response.status_code}: {e.response.text[:300]}\n")
        return False
    except Exception as e:
        print(f"[FAIL] {e}\n")
        return False


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    print(f"Question: {PROMPT}\n")
    print(f"{'=' * 60}\n")

    results = {}
    for model in MODELS:
        results[model] = test_model(model, api_key)
        print(f"{'=' * 60}\n")

    print("--- Summary ---")
    passed = sum(results.values())
    for model, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {model}")

    print(f"\n{passed}/{len(MODELS)} models reachable")
    if passed < len(MODELS):
        sys.exit(1)


if __name__ == "__main__":
    main()
