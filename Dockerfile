Below is an updated Dockerfile that runs the token setup command and then starts the Flask app—all in one file using a shell command with `sh -c`:

```dockerfile
# Use Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install git and other dependencies
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir flask modal gunicorn

# Clone the repository
RUN git clone https://github.com/Bharani77/Modal.git /app/Modal

# Set up the Flask application
COPY app.py /app/
COPY modal_container.py /app/

# Expose port for Flask
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to set token and run the Flask app
CMD sh -c 'modal token set --token-id ak-vPJ3ATtFnoYAVNKB1vdN4l --token-secret as-lsyeIinELaOxnfhiw3mM1v && gunicorn --bind 0.0.0.0:5000 app:app'
