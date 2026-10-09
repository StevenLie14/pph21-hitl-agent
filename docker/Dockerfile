FROM python:3.13-slim AS korpus
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PPH21_DATA=/data
WORKDIR /app
RUN pip install pydantic==2.13.5 pydantic-settings==2.15.0 PyYAML==6.0.3 neo4j==6.3.1 beautifulsoup4==4.15.0 pymupdf==1.28.2 \
        python-dotenv==1.2.3
COPY pyproject.toml README.md ./
COPY taxagent ./taxagent
COPY scripts ./scripts
COPY docker/update_corpus.sh ./docker/
RUN pip install --no-deps -e . && chmod +x docker/update_corpus.sh \
    && useradd --create-home --uid 1000 pph21 && mkdir -p /data && chown pph21 /data
USER pph21
VOLUME ["/data"]
ENTRYPOINT ["/app/docker/update_corpus.sh"]

FROM python:3.11-slim AS ocr
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PPH21_DATA=/data PADDLE_PDX_CACHE_HOME=/model PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
    && pip install paddleocr==3.7.0 paddlex==3.7.2 pymupdf==1.28.2 psutil==7.2.2
WORKDIR /app
COPY pipeline/ocr_corpus.py pipeline/paddle_common.py ./pipeline/
COPY taxagent/taxes/pph21/data/rantai_pph21.yaml ./taxagent/taxes/pph21/data/
COPY docker/run_ocr.sh ./docker/
RUN chmod +x docker/run_ocr.sh && useradd --create-home --uid 1000 pph21 && mkdir -p /data /model     && chown pph21 /data /model
USER pph21
VOLUME ["/data", "/model"]
ENTRYPOINT ["/app/docker/run_ocr.sh"]

FROM python:3.13-slim AS embed
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PPH21_DATA=/data
RUN pip install neo4j==6.4.0 PyYAML==6.0.3 numpy==2.4.6 requests==2.34.2
WORKDIR /app
COPY pipeline/embed.py ./pipeline/
RUN useradd --create-home --uid 1000 pph21 && mkdir -p /data && chown pph21 /data
USER pph21
VOLUME ["/data"]
ENTRYPOINT ["sh", "-c", "python pipeline/embed.py gemini compute --faq && python pipeline/embed.py gemini write"]
