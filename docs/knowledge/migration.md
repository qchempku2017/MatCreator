# Knowledge Migration

MatCreator uses the unified Know-Do Graph data model. Durable knowledge and working memory are stored together in one graph database. Legacy files are read-only migration sources and are not deleted by migration.

Run all commands in this guide from the MatCreator project root.

## What Is Migrated

| Previous source | New representation |
| --- | --- |
| `.adk/know_do_graph.db` | Entries and edges stored in the unified default database |
| `.adk/skill_graph.db` | Skills become capability entries; dependency edges are preserved |
| `.adk/memory_graph.db` | Memories become native memory nodes |
| `.adk/memory/*.json` | Imported once as native memory nodes |
| `MEMORY.md` | Each usable line becomes a native memory node |

Migration is idempotent, so running it again does not duplicate previously imported records.

## Back Up Existing Data

Stop the MatCreator agent, API server, and any process writing to the old graph. Then create a timestamped backup:

```bash
backup_dir="backup/knowledge-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir/legacy-adk" "$backup_dir/current-data"

cp -a agents/MatCreator/.adk/skill_graph.db "$backup_dir/legacy-adk/" 2>/dev/null || true
cp -a agents/MatCreator/.adk/memory_graph.db "$backup_dir/legacy-adk/" 2>/dev/null || true
cp -a agents/MatCreator/.adk/know_do_graph.db "$backup_dir/legacy-adk/" 2>/dev/null || true
cp -a agents/MatCreator/.adk/memory "$backup_dir/legacy-adk/" 2>/dev/null || true
cp -a agents/MatCreator/.adk/know_do_graph.db "$backup_dir/current-data/" 2>/dev/null || true
```

Back up a workspace `MEMORY.md` separately if one exists.

## Run Migration

Migrate detected legacy databases:

```bash
matcreator knowledge migrate
```

Import a specific `MEMORY.md`:

```bash
matcreator knowledge migrate --memory-md /absolute/path/to/MEMORY.md
```

After migration, seed the current skills and guides:

```bash
matcreator knowledge seed
```

## Verify The Result

Check MatCreator's combined statistics:

```bash
matcreator knowledge stats
```

Check the same database through the Know-Do Graph CLI:

```bash
know-do-graph graph stats
```

Both commands should use the same `KDG_DB_PATH`. By default MatCreator points that at `~/.matcreator/.adk/know_do_graph.db`.

## Distill Working Memory

Agent observations remain memory nodes until repeated evidence is promoted:

```bash
matcreator knowledge distill --min-evidence 3
```

Use a different threshold when needed:

```bash
matcreator knowledge distill --min-evidence 5 --stale-days 60
```

## Rollback

Stop all graph writers before rollback. Restore the backed-up unified database:

```bash
cp backup/knowledge-TIMESTAMP/current-data/know_do_graph.db \
  ~/.matcreator/.adk/know_do_graph.db
```

If no unified database existed before migration, move the new database aside and keep the legacy sources untouched for another migration attempt.
