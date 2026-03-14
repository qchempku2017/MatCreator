---
name: database
description: Skills for materials datasets operations. You help users query datasets (in ASE db format) stored in a normalized SQLite database organized into nodes (groups of datasets sharing the same DFT settings) and datasets (one per element-set per node). You assist with finding relevant datasets by chemical composition or node metadata, inspecting and querying structures within datasets, exporting structures, and saving new calculation data to an appropriate node.
tags: [general, sequential, simple]
tools: [database_sql_agent,validate_sql_code_query,query_information_database,query_compounds,export_entries]
dependent_skills: []
---

Use this flow for dataset search:
1) search for available dataset domains:
  -`database_sql_agent` to generate one safe SELECT.
  - `validate_sql_code_query`.
  - `query_information_database` to check available domain datasets (e.g., "domain_SemiCond").
2) Use `query_compounds` to find target dataframes in the selected domain dataset.

When preparing training/validation dataset for machine learning force fields,
always export to extxyz format.