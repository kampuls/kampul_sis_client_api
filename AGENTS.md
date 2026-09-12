# Mandatory API repository instructions

Before planning, reviewing, or changing this repository, read
`docs/DESKTOP_API_DEVELOPMENT.md` in full.

- `/api/desktop` is the only data boundary for the Windows client.
- Never expose database credentials or permit non-desktop tokens on the desktop
  compatibility surface.
- Store media in `StorageService` and persist URL/path strings only, except for
  the temporary pre-existing `students.image` BLOB needed by released desktop
  builds. Do not add any other SQLAlchemy `LargeBinary` field or MySQL binary
  media column. Current desktop writes must still upload a resource first.
- Own all schema changes on the API through models/migrations; never rely on the
  client to create or alter tables.
- Keep transactions atomic and test SQL validation, authentication scope, and
  resource behavior before handoff.
