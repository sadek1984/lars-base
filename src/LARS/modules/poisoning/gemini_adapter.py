import os
import google.generativeai as genai

def make_gemini_call():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    genai.configure(api_key=key)
    model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))

    def call(prompt: str) -> str:
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0, "max_output_tokens": 512},
        )
        return resp.text

    return call