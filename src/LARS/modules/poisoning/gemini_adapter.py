# src/LARS/modules/poisoning/gemini_adapter.py
import os
from google import genai
from google.genai import types
from google.oauth2 import service_account


def make_gemini_call():
    project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("LOCATION", "us-central1")
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-001")

    if not project_id:
        return None

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.exists(creds_path):
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        client = genai.Client(vertexai=True, project=project_id, location=location, credentials=credentials)
    else:
        # ADC — works automatically on Cloud Run with the right IAM role
        client = genai.Client(vertexai=True, project=project_id, location=location)

    def call(prompt: str) -> str:
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=512),
        )
        return resp.text

    return call