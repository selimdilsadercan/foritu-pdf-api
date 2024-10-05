# Temel imaj olarak Debian'ı kullan
FROM debian:stable-slim

# Python ve pip'i yükle
RUN apt-get update && \
  apt-get install -y python3 python3-pip python3-venv && \
  apt-get clean

# Çalışma dizinini ayarla
WORKDIR /app

# Gizli bilgileri mount et ve environment değişkenleri olarak ayarla
RUN --mount=type=secret,id=SUPABASE_URL \
  --mount=type=secret,id=SUPABASE_KEY \
  --mount=type=secret,id=SUPABASE_BUCKET \
  sh -c 'echo "SUPABASE_URL=$(cat /run/secrets/SUPABASE_URL)" >> /etc/environment && \
  echo "SUPABASE_KEY=$(cat /run/secrets/SUPABASE_KEY)" >> /etc/environment && \
  echo "SUPABASE_BUCKET=$(cat /run/secrets/SUPABASE_BUCKET)" >> /etc/environment'

# requirements.txt dosyasını kopyala
COPY requirements.txt .

# .env dosyasını kopyala
COPY .env .

# Sanal ortam oluştur ve etkinleştir
RUN python3 -m venv venv

# Sanal ortamda pip'i kullanarak paketleri yükle
RUN ./venv/bin/pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Uygulamanın çalışması için gerekli environment değişkenlerini ayarlamak
RUN set -a && . /etc/environment && set +a

# Uygulamayı çalıştır
EXPOSE 8080
CMD ["./venv/bin/uvicorn", "main:app", "--host=0.0.0.0", "--port=8080"]
