FROM python:3.10-slim

# Chromium ve Chromedriver'ı kur (Chrome'dan daha hafif)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    unzip \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Chromium yolunu ortam değişkenine ata
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Çıktıları anında görmek için -u flag'i
CMD ["python", "-u", "app.py"]
