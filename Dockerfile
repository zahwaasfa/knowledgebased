FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .

# 1. Install PyTorch CPU terlebih dahulu agar tidak mengunduh paket GPU/CUDA yang besar (~2-3 GB)
# 2. Tambahkan parameter timeout agar tidak putus koneksi saat proses unduh berlangsung
RUN pip install --no-cache-dir --default-timeout=1000 torch --index-url https://download.pytorch.org/whl/cpu

# Install sisa dependensi lainnya
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY . .
EXPOSE 8000 8501

CMD ["uvicorn", "kb_api.main:app", "--host", "0.0.0.0", "--port", "8000"]