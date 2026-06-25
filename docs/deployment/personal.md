# Personal Application Deployment

Personal application mode runs MatCreator for one user on a local machine or single-user server. It does not require Docker, authentication, or a control plane.

## Install And Configure

Install MatCreator from the repository root:

```bash
pip install uv
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

Configure LLM access with the CLI:

```bash
matcreator config set llm.model=openai/qwen3-plus
matcreator config set llm.api_key=your-api-key
matcreator config set llm.base_url=https://api.example.com/v1
```

## CLI Usage

Start an interactive session:

```bash
matcreator chat --workspace .
```

Run in full planning mode:

```bash
matcreator chat --workspace . --plan
```

Run a one-shot prompt:

```bash
matcreator run -p "Build a silicon FCC structure"
```

## Web UI

Start all local web services:

```bash
bash script/start_matcreator.sh
```

This starts:

- ADK API server on `http://localhost:8000`
- FastAPI middle layer on `http://localhost:8001`
- Vite frontend on `http://localhost:5173`

Logs are written to `~/.matcreator/logs/{api-server,web-main,vite}.log` by default. Set `MATCREATOR_LOG_DIR=/path/to/logs` to override this location.

## Data Locations

| Data | Default location |
| --- | --- |
| User configuration | `~/.matcreator/config.yaml` |
| ADK sessions and graph database | `~/.matcreator/.adk/` |
| Workspace artifacts | selected `--workspace` directory |
| Local logs | `~/.matcreator/logs/` |