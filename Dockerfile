# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install git and other dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Expose the port Gradio runs on
EXPOSE 7860

# Command to run the application
CMD ["python", "app.py"]