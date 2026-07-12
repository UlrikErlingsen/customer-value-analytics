FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only app code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY app.py README.md LICENSE PRIVACY.md SECURITY.md CHANGELOG.md ./
COPY src/ ./src/
COPY examples/ ./examples/
COPY docs/ ./docs/
COPY assets/ ./assets/
COPY .streamlit/config.toml ./.streamlit/config.toml

# Make the computation package importable without an editable install.
ENV PYTHONPATH=/app/src

# The application does not need root privileges at runtime.
RUN useradd --create-home --uid 10001 worthsignal
USER worthsignal

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.address", "0.0.0.0", \
    "--server.port", "8501", \
    "--browser.gatherUsageStats", "false"]
