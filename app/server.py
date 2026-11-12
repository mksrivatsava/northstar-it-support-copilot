"""Container entrypoint using the port provided by the hosting platform."""
import os
import uvicorn


if __name__ == '__main__':
    uvicorn.run('app.asgi:app', host='0.0.0.0', port=int(os.getenv('PORT', '8000')))
