FROM python:3.11-slim

WORKDIR /app

# System dependencies for Playwright + Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    libx11-6 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Force remove Telethon (this is the fix for your error)
RUN pip uninstall -y telethon || true

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium --with-deps

COPY . .

CMD ["python", "main.py"]
