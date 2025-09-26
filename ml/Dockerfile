FROM python:3.8.3

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgthread-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install uv

# Copy requirements first for better caching
COPY pyproject.toml .
RUN uv pip install -r pyproject.toml --system

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/local_storage/input_scans \
    /app/local_storage/cropped_images \
    /app/local_storage/results \
    /app/local_storage/xml_intermediate \
    /app/local_storage/logs

# Set environment variables
ENV OMP_NUM_THREADS=4
ENV PYTHONUNBUFFERED=1

# Make entrypoint executable
RUN chmod +x entrypoint.py

# Set entrypoint
ENTRYPOINT ["python", "entrypoint.py"]
