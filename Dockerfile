FROM python:3.13-slim

# system deps
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
 && rm -rf /var/lib/apt/lists/*

# workdir
WORKDIR /app

# python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# project
COPY . .

# entrypoint
RUN chmod +x docker/entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["docker/entrypoint.sh"]
