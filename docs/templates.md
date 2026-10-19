# Template lists

Reusable lists for things that come back: a packing list for the weekend, the weekly shopping, a school-start checklist.

A template has a name and items. Each item has a name and an optional note or quantity (`2 l`, `size 128`). Templates belong to the family: everybody sees the same ones.

## Where to find them

- **Shopping screen, menu:** *Templates* (apply to the shopping list) and *Save shopping list as template* (adults only; stores the open entries of the current list).
- **Tasks screen, menu:** *Templates* (create tasks from a template).

Tap a template to choose which items to use (all are ticked) and apply it.

## Applying to the shopping list

Items go onto whatever shopping list is active (the hub's own list, Home Assistant or Mealie), through the same path as any other new entry. An item with a note is added as `Milk (2 l)`.

Items that are already open on the list are not added twice. The comparison ignores case and extra whitespace, and `Milk (2 l)` on the list counts as `Milk`. Done entries do not count. The answer says how many were added and how many were skipped. If the list cannot be read, nothing is added and the app says so.

## Applying to tasks

Tasks have no list-with-items concept of their own (tasks live in the person's task source: Nextcloud, Habitica, or the hub), so applying a template creates **one task per item**. The note becomes the task's notes. The tasks are placed like any new task: in your own place, or on the family list if you switch *Create on the family list* on. Rotation, due dates and assignees are not part of a template.

## Roles

| Action | Minimum role |
| --- | --- |
| See templates | guest |
| Apply to the shopping list | guest (same as adding to the shopping list) |
| Apply to tasks | partner (same as creating a task) |
| Create, edit, delete a template, save the shopping list as one | partner |

## API

All under `/api/templates`:

- `GET /` list, `GET /{id}`
- `POST /` and `PUT /{id}` with `{"name": "...", "items": [{"name": "...", "note": "..."}]}` (blank items are dropped), `DELETE /{id}`
- `POST /from-shopping` with `{"name": "..."}`
- `POST /{id}/apply/shopping` with `{"item_ids": [..] | null}` returns `{status, added, skipped, failed}`
- `POST /{id}/apply/tasks` with `{"item_ids": [..] | null, "list": "family" | null}` returns `{status, created, failed}`

Database: tables `list_templates` and `list_template_items` (Alembic revision `20a1b2c3d4e5`).
