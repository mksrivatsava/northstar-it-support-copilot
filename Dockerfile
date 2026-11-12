FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home copilot
COPY --chown=copilot:copilot app ./app
COPY --chown=copilot:copilot static ./static
COPY --chown=copilot:copilot data ./data
COPY --chown=copilot:copilot evals ./evals
RUN mkdir -p /app/.runtime && chown copilot:copilot /app/.runtime
USER copilot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/health', timeout=3)"
CMD ["python", "-m", "app.server"]
