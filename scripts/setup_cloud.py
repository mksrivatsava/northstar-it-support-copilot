"""Provision this project's index and sync its synthetic corpus. No keys in output."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
from app.main import create_app
from app.cloud import ProviderError

if __name__ == '__main__':
    app = create_app()
    if app.state.settings.retrieval_mode != 'pinecone':
        sys.exit('Set RETRIEVAL_MODE=pinecone in .env first.')
    try:
        status = app.state.workflow.retriever.sync(create=True)
        print(json.dumps(status, indent=2))
    except ProviderError as error:
        print(str(error))
        sys.exit(1)
