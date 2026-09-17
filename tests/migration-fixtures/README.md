# Anonymized migration snapshots

These JSON files are synthetic schema snapshots only. They contain no
production credentials, topics, paths, media, queues, or other user data.
`schema-3-current.json` represents the immediately preceding supported
settings schema; `schema-0-empty.json` represents an absent/legacy-shaped
settings payload. The compatibility test seals each snapshot into schema 4 in
an isolated root and verifies current records remain current while historical
tombstones do not become active rows.
