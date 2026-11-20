import os

import httpx


MODEL = "gemini-3.1-flash-lite"


def generate_content(payload: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY in this terminal before running the check.")

    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=30,
        )
    except httpx.RequestError as error:
        raise SystemExit(f"Gemini connection failed ({type(error).__name__}).") from None

    if not response.is_success:
        raise SystemExit(f"Gemini returned HTTP {response.status_code}. Check API access and quota.")

    candidates = response.json().get("candidates", [])
    if not candidates or not candidates[0].get("content", {}).get("parts"):
        raise SystemExit("Gemini returned no content.")
    return candidates[0]["content"]


def answer_text(content: dict) -> str:
    parts = content["parts"]
    answer = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
    if not answer:
        raise SystemExit("Gemini returned no text.")
    return answer


def main() -> None:
    content = generate_content({
        "contents": [{"parts": [{"text": "Reply with exactly: Gemini connection OK"}]}],
    })
    print(answer_text(content))


if __name__ == "__main__":
    main()
