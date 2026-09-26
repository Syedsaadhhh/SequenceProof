FROM python:3.12-slim
WORKDIR /app
COPY sequenceproof.py server.py index.html ./
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
