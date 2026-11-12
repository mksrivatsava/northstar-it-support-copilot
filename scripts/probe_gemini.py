"""Minimal model availability probe with response-body credential scrubbing."""
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app.config import load_env

load_env()
key = os.getenv('GEMINI_API_KEY', '')
with httpx.Client(timeout=30, trust_env=False) as client:
    for model in ['gemini-2.5-flash', 'gemini-3.1-flash-lite']:
        response = client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
            headers={'x-goog-api-key': key}, json={'contents': [{'parts': [{'text': 'Reply with OK.'}]}],
                'generationConfig': {'maxOutputTokens': 32}})
        print(model, 'HTTP', response.status_code, flush=True)
        if response.is_success:
            print('  generation responded successfully', flush=True)
            break
        else:
            message = response.json().get('error', {}).get('message', '')
            print(' ', message.replace(key, '[redacted]')[:500], flush=True)
