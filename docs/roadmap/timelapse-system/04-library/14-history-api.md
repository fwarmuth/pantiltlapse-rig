# Task 14 — Historical Run API

## Goal

Browse completed, cancelled, failed, and interrupted runs directly from filesystem manifests without adding a database.

## Prerequisites

- Tasks 10B and 12.

## Checklist

- [ ] Add paginated run listing with stable newest-first ordering.
- [ ] Support simple filters for plan ID, state, date range, and name text without building a query framework.
- [ ] Return compact summaries: identity, name, state, timestamps, shot/success/gap counts, duration, and thumbnail availability.
- [ ] Add run detail, paginated shot records, event retrieval, and safe artifact endpoints.
- [ ] Reuse `RunStore` reads and artifact resolution; route handlers must not rescan/parse the filesystem independently.
- [ ] Resolve artifacts only inside the configured output root and set correct media/download headers.
- [ ] Keep RAW/original downloads separate from browser preview responses.
- [ ] Report malformed/incomplete run directories as isolated diagnostics rather than failing the entire listing.
- [ ] Ensure deleted source plans do not affect run discovery or plan snapshots.
- [ ] Verify the immutable snapshot hash on detail reads and expose corruption as diagnostics without hiding unaffected runs.
- [ ] Add tests for pagination stability, filters, mixed states, corrupt manifests, missing previews, RAW downloads, path traversal, and deleted plans.

## Functional check

Generate a fixture library containing successful, gap-containing, cancelled, error, and interrupted runs across multiple dates. Browse every page/filter and retrieve previews, metadata, events, and originals.

## Acceptance criteria

- Filesystem manifests remain the source of truth; no SQLite index is added.
- Listing work is bounded by pagination and remains acceptable for a realistic local library.
- Corruption in one run does not hide other history.
- Original media is never modified while being served.

## Not in this task

- History frontend.
- Deleting runs or bulk media management.
- Rendering video.

## Implementation notes

- Record test-library size and measured listing latency here.
