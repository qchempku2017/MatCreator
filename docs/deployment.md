# Deployment

MatCreator supports two primary deployment shapes:

- [Personal application](deployment/personal.md): run the CLI and web UI on a local workstation or single-user server.
- [Server deployment](deployment/server.md): run a shared multi-user Docker deployment with isolated user workers.

The documentation site itself is deployed separately with MkDocs Material and GitHub Pages.

## Documentation Site

The public documentation is built with MkDocs Material and deployed to GitHub Pages by GitHub Actions.

Local preview:

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

Production build:

```bash
mkdocs build --strict
```

The published site is expected at:

```text
https://nlz25.github.io/PFD-Agent/
```

In the GitHub repository settings, set `Settings -> Pages -> Build and deployment -> Source` to `GitHub Actions`.

## Choosing A Deployment Mode

| Mode | Best for | Main command |
| --- | --- | --- |
| Personal application | Local development, individual research workflows, workstation use | `bash script/start_matcreator.sh` |
| Server deployment | Shared group server with multiple registered users | `docker compose -f docker-compose.server.yml up -d` |

Use personal application mode first unless you specifically need multi-user isolation, centralized auth, and Docker worker lifecycle management.
