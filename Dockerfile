FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY castbook ./castbook
RUN uv pip install --system -e .

VOLUME /data
ENV CASTBOOK_DATA_DIR=/data/books CASTBOOK_MODELS_DIR=/data/models

ENTRYPOINT ["castbook"]
CMD ["--help"]
