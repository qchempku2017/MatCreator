# Knowledge

MatCreator's knowledge layer lets the agent reuse what it knows instead of treating every session as a blank slate. It combines curated skills, procedural guides, runtime memories, and distilled heuristics in a shared Know-Do Graph database.

## Knowledge Sources

| Source | Role |
| --- | --- |
| Skills | Durable capability descriptions and procedures that the agent can invoke while planning or executing. |
| Guides | Longer reusable workflows and domain procedures. |
| Memory | Session-level observations and outcomes written by the agent. |
| Distilled heuristics | Repeated successful memories promoted into durable knowledge. |

## Default Storage

MatCreator stores the active Know-Do Graph under the user-level MatCreator home by default:

```text
~/.matcreator/.adk/know_do_graph.db
```

The database location can be overridden with `KDG_DB_PATH` when needed.

## Common Commands

Seed packaged skills and guides:

```bash
matcreator knowledge seed
```

Search the graph:

```bash
matcreator knowledge query "formation energy workflow"
```

Search skills:

```bash
matcreator knowledge search-skills "structure generation"
```

Show graph statistics:

```bash
matcreator knowledge stats
```

Promote repeated successful memory into durable knowledge:

```bash
matcreator knowledge distill --min-evidence 3
```

## Related Pages

- [Know-Do Graph](../knowledge_graph.md)
- [Knowledge Migration](migration.md)
