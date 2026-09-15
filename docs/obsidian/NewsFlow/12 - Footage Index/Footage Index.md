# Footage Index

## Active Light path

`Footage screen → index-footage → bridge.index_footage → ClipIndex.remove_missing → ClipIndex.index_folders → ClipIndex.enrich_semantic_tags → footage-index.sqlite3`.

The index identity is absolute path plus file size and `mtime_ns`. Existing matching CLIP rows are skipped; a changed file is sampled/indexed again; missing paths are removed before the index pass. The indexed path/size/mtime duration cache is then used by montage only when the source still matches, otherwise normal strict media validation remains the authority.

## Regression evidence — 2026-09-11

`test_incremental_index_reuses_unchanged_clips_reindexes_changes_and_removes_missing` verifies new, unchanged, changed and deleted clip behavior with local fake embeddings. `tests.test_footage` passed. No user footage folder or production index was opened.
