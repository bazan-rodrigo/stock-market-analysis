web: gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 1800
worker: python worker.py
mcp: uvicorn mcp_server:app --host 0.0.0.0 --port $PORT
