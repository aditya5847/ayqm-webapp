# AYQM Webapp Notes

This repo is the FastAPI/DuckDB backend plus the React/Vite frontend for AYQM.

Keep these current behaviors in mind:

- The public home page shows the podcast cover on the left and the latest episode artwork/text on the right.
- The public episode archive uses pagination; the home page “Recent episodes” strip should not repeat the latest episode.
- The admin episode list uses pagination with the same control design at the top and bottom of the list.
- Pagination should hide the `Previous` button on the first page and the `Next` button on the last page.
- The About page guest list is data-driven from public speakers plus published episodes, with host names excluded.
- Guest episode links on About should use `#<episode number>` labels.
- Dev-only placeholder content may be used to inspect layout, but it should not affect production behavior.

Project constraints:

- Preserve DuckDB-backed storage and the existing API contracts unless a change explicitly requires a schema/API update.
- Keep frontend changes consistent with the existing retro UI style.
- Avoid committing generated artifacts, database files, or uploads.
