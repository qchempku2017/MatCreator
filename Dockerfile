FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl bash \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv -i https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

ENV UV_SYSTEM_PYTHON=1
RUN uv pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY web/vite-frontend/package*.json web/vite-frontend/
RUN cd web/vite-frontend && npm install

COPY . .

# Build the production frontend bundle (served as static files by web/main.py)
RUN cd web/vite-frontend && npm run build

ENV PYTHONUNBUFFERED=1
EXPOSE 8000 8001 5173
CMD ["bash", "script/start_matcreator.sh"]
