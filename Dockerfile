FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only app code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY app.py README.md ./
COPY src/ ./src/
COPY examples/ ./examples/
COPY docs/ ./docs/

# Make the computation package importable without an editable install.
ENV PYTHONPATH=/app/src

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.address", "0.0.0.0", \
    "--server.port", "8501", \
    "--browser.gatherUsageStats", "false"]
