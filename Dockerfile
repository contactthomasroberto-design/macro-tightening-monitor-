FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONHASHSEED=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e . --no-deps
EXPOSE 8501
# Default to demo mode so the container runs offline; override with -e MACRO_MODE=live
ENV MACRO_MODE=demo
CMD ["sh", "-c", "python scripts/update_data.py && streamlit run app/streamlit_app.py --server.address=0.0.0.0"]
