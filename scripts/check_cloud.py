"""Read-only credential check. Never prints keys, URLs with keys, or response bodies."""
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app.config import load_env


def check():
    load_env()
    checks = [
        ('Gemini', 'https://generativelanguage.googleapis.com/v1beta/models',
         {'x-goog-api-key': os.getenv('GEMINI_API_KEY', '')}),
        ('Pinecone', 'https://api.pinecone.io/indexes',
         {'Api-Key': os.getenv('PINECONE_API_KEY', ''), 'X-Pinecone-API-Version': '2025-10'}),
    ]
    success = True
    with httpx.Client(timeout=30, trust_env=False) as client:
        for name, url, headers in checks:
            try:
                response = client.get(url, headers=headers)
                print(f'{name}: HTTP {response.status_code}')
                if response.is_success:
                    payload = response.json()
                    if name == 'Gemini':
                        for item in payload.get('models', []):
                            if any(x in item.get('supportedGenerationMethods', []) for x in ['embedContent', 'generateContent']):
                                print('  available model:', item.get('name', 'unknown'))
                    else:
                        for item in payload.get('indexes', []):
                            print('  existing index:', item.get('name'), 'dimension:', item.get('dimension'))
                else:
                    success = False
                    if name == 'Gemini':
                        error = response.json().get('error', {})
                        print('  status:', error.get('status', 'unknown'))
                        reasons = [x.get('reason') for x in error.get('details', []) if isinstance(x, dict) and x.get('reason')]
                        if reasons:
                            print('  reasons:', ', '.join(reasons))
            except (httpx.HTTPError, ValueError):
                print(name + ': connection or response error (details suppressed to protect credentials)')
                success = False
    return success


if __name__ == '__main__':
    sys.exit(0 if check() else 1)
