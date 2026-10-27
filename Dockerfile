FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY . .
ENV GA_BIND_HOST=0.0.0.0
EXPOSE 8765
CMD ["python", "-m", "geoacceptance.server", "--port", "8765", "--data-dir", "/app/work/app"]
