# Sandbox where agents run skill scripts. It has no database access, no API keys, and by default
# no internet; it only sees the task workspaces (./data/work) and the skill packages (./skills, read-only).
FROM python:3.12-slim

ARG RUNNER_UID=1000
ARG RUNNER_GID=1000

# Tools the public Agent Skills (pptx, docx, xlsx, pdf) expect.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nodejs npm \
        libreoffice-impress libreoffice-writer libreoffice-calc \
        fonts-noto-cjk fonts-noto-color-emoji \
        zip unzip poppler-utils ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv \
    && pip install --no-cache-dir \
        python-pptx python-docx openpyxl pypdf pdfplumber pandas matplotlib pillow defusedxml \
        "markitdown[pptx,docx,xlsx,pdf]"

RUN npm install -g --no-fund --no-audit pptxgenjs docx react react-dom react-icons sharp \
    && npm cache clean --force
ENV NODE_PATH=/usr/local/lib/node_modules

RUN groupadd -g "${RUNNER_GID}" runner && useradd -m -u "${RUNNER_UID}" -g runner runner
COPY server.py /opt/sandbox/server.py

USER runner
EXPOSE 8000
CMD ["python", "/opt/sandbox/server.py"]
