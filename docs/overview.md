# Overview

MatCreator is organized as an agent harness around the Google ADK runtime, a skill library, a workspace, and a persistent knowledge base. The harness gives users a stable CLI and web interface while allowing the agent to plan, execute, remember, and improve over time.

## Harness Architecture

```text
User
  |
  v
CLI / Web UI / API
  |
  v
MatCreator Agent App
  |
  +-- Flash mode: direct interactive execution
  |
  +-- Plan mode: thinking agent -> execution graph -> execution agent
  |
  v
Skills, Tools, Workspace, Knowledge
```

## Runtime Layers

| Layer | Role |
| --- | --- |
| CLI | Provides `matcreator chat`, `matcreator run`, `matcreator config`, and knowledge commands. |
| ADK server | Hosts the MatCreator agent app for web and API usage. |
| Web backend | Adds project-specific APIs, artifact management, settings, and server-mode control-plane behavior. |
| Vite frontend | Provides the browser interface for chat, graph visualization, and artifact interaction. |
| Skills | Modular Markdown capabilities that describe domain procedures and required tools. |
| Workspace | Stores user sessions, generated artifacts, local skills, guides, and memory files. |
| Knowledge graph | Stores durable capabilities, procedures, memories, and distilled heuristics. |

## Execution Modes

### Flash Mode

Flash mode is the default for `matcreator chat`. It lets the agent respond and act directly, which is useful for interactive exploration and quick tasks.

```bash
matcreator chat --workspace .
```

### Plan Mode

Plan mode asks the thinking agent to build an execution graph before work is handed to the execution agent. It is useful when a task has multiple dependent steps or when the user wants to inspect the workflow shape.

```bash
matcreator chat --workspace . --plan
```

The graph is a directed acyclic graph whose nodes are discrete actions and whose edges encode dependencies. Independent nodes can run in parallel, while failed nodes block their dependents.

## Configuration And State

MatCreator stores persistent user-level configuration at:

```text
~/.matcreator/config.yaml
```

ADK session state and the default Know-Do Graph database live under:

```text
~/.matcreator/.adk/
```

Workspace-specific sessions and artifacts live under the workspace selected with `--workspace` or `MATCLAW_WORKSPACE`.