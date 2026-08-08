# Task 15 — Sequence Library UI

## Goal

Let the operator inspect previous runs, images, gaps, and metadata from the same zero-build web interface.

## Prerequisites

- Tasks 13 and 14.

## Checklist

- [ ] Add a clear navigation choice between planning/current operation and library.
- [ ] Show paginated run cards/rows with date, plan name, terminal state, shot/gap counts, duration, and representative thumbnail.
- [ ] Add lightweight state/date/name filters matching the backend API.
- [ ] Add run detail with immutable plan summary, acquisition settings, rig snapshot, timing statistics, and error summary.
- [ ] Add a paginated shot gallery that visually distinguishes success from gap.
- [ ] Show preview images first and offer explicit original/RAW download links.
- [ ] Add expandable shot attempts and run events for diagnosis without overwhelming the default view.
- [ ] Handle missing/corrupt artifacts with placeholders and visible explanations.
- [ ] Preserve the current live run view if navigation returns while recording continues.
- [ ] Verify keyboard navigation, meaningful image alternatives, touch targets, and narrow-phone layout.

## Fixture-library check

Browse the fixture library from task 14 on phone/tablet/desktop widths. Filter it, inspect all terminal states, open shot details, download originals, navigate back to an active run, and refresh deep-linked detail views.

## Hardware field check

- [ ] Browse at least one genuine JPEG run and one genuine RAW-producing run from a phone.
- [ ] Compare displayed settings/timestamps with stored artifacts and camera metadata.
- [ ] Confirm large originals are downloaded only on explicit request.

## Acceptance criteria

- Old runs remain understandable without loading their source plan.
- Gaps and interrupted/error states cannot be mistaken for complete sequences.
- Normal browsing uses previews and metadata, not full-size originals.
- No frontend framework or build tool is introduced.

## Not in this task

- Deleting, renaming, or editing historical evidence.
- Video preview/rendering.
- Cloud galleries or sharing.

## Implementation notes

- Record browser/device coverage and any large-library observations here.
