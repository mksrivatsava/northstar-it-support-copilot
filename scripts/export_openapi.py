import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import create_app

if __name__ == '__main__':
    output = Path(__file__).resolve().parent.parent / 'docs' / 'openapi.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(create_app().openapi(), indent=2) + '\n', encoding='utf-8')
    print(output)
