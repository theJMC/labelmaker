FROM python:3.12-slim
 
WORKDIR /app
 
# Install dependencies first so they're cached separately from app code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# App code
COPY app.py generate_labels.py ./
COPY *.ttf ./
 
EXPOSE 5000
 
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
 