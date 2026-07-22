FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# state.json is written here; mount /app/data as a volume to persist it.
ENV PYTHONUNBUFFERED=1

# Runs the forever-loop. Config/secrets come from env + mounted config.yaml.
CMD ["python", "run.py"]
