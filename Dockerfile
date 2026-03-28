FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow, lxml, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libxml2-dev libxslt1-dev \
    libjpeg62-turbo-dev libpng-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY index.html .
COPY static/ static/
COPY config.json .

# Create output directory
RUN mkdir -p output "input products"

# Default: disable CLIP on cloud (saves ~2GB RAM)
ENV DISABLE_CLIP=true
ENV PORT=10000

EXPOSE 10000

CMD ["python", "app.py"]
