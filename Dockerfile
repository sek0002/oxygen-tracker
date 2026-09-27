FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html styles.css app.js model.js store.js config.js favicon.svg manifest.webmanifest sw.js pwa.js theme.js icon-180.png icon-192.png icon-512.png ./
RUN useradd --system --uid 10001 oxygen && mkdir /data && chown oxygen:oxygen /data
USER oxygen
ENV OXYGEN_HOST=0.0.0.0 OXYGEN_DB=/data/oxygen.sqlite3 PORT=8070
EXPOSE 8070
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8070/health')"
CMD ["python", "server.py"]
