"""Run a loopback-only development server with `python run.py`."""
import os
import uvicorn
from app.config import settings_from_env
from app.main import create_app

if __name__ == '__main__':
    settings = settings_from_env()
    print('\nNorthstar Internal IT Support Copilot')
    print('Admin key: use APP_ADMIN_KEY from .env, or read .runtime/admin-key if it was generated.')
    print(f'Answer mode: {settings.answer_mode}\n')
    uvicorn.run(create_app(settings), host='127.0.0.1', port=int(os.getenv('APP_PORT', '8000')))
