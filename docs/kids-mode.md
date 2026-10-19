# Kids mode: stars and rewards

Built-in motivation for children, without Habitica. Parents put stars on tasks and define rewards; children collect stars by completing tasks and ask for rewards; parents approve or decline.

## How it works

1. **Stars on tasks.** A parent (partner or admin) sets stars when creating or editing a task (field "Stars for this task"). Completing the task pays those stars to **the person who completed it**.
2. **Rewards.** Parents add rewards with a star price ("30 min media time", "1 € pocket money") under **More → Stars**. Hiding a reward keeps the history intact.
3. **Requests.** A child taps *Request* on a reward they can afford. The stars are *reserved* (they cannot be spent twice) and all parents get a notification (category "Stars and rewards"). A parent approves (the stars are booked) or declines (the reservation is released). A child can withdraw an open request.
4. **History.** Every child sees their own history; parents see every child's history, can give a bonus or a deduction, and see the balances.
5. **Optional confirmation.** With **Confirm completed tasks** switched on (More → Stars, parents only), a child's completed starred tasks stay *waiting* until a parent confirms them; only confirmed stars count. A parent can also reject. Stars earned by adults are never held.
6. **Today.** The *Stars* card shows the balance and the next reward with a progress bar (parents also see how many decisions wait). It is a normal card of the customisable Today layout (it is last by default, so move it up for a child). It is only shown for people who use stars: children once a reward exists or they have an account, adults once they have an account or something waits for them. Everyone else sees no card.

## Which task sources work

Stars are stored **hub-side, keyed by `(provider, task uid)`**, so they work for the hub's own tasks and for external sources (Nextcloud/CalDAV) without writing anything into the external task:

- Hub tasks: stars can be set when creating or editing, and a rotating household task passes its stars to the next turn.
- External tasks (Nextcloud etc.): stars can be set when the task is created from the app and from the edit sheet; the stars live in the hub only, so a task created elsewhere gets stars through the edit sheet (`PUT /api/stars/tasks/{provider}/{uid}`). A completed external task pays when it is completed **through the hub** (app or API); completing it in another app does not pay, because the hub is not told.
- Habitica has its own rewards and is excluded.
- A recurring external task pays once per occurrence (the due date is part of the booking key); completing the same occurrence twice pays once.

## Rules enforced by the server

- Only parents (partner, admin) may set stars on tasks, manage rewards, decide on requests and confirmations, change the setting or adjust a balance. A child can only read their own data, request rewards and withdraw their own requests.
- Nobody decides on their own requests, confirms their own stars or changes their own balance.
- The balance never goes negative and never below what open requests reserve: changes are conditional `UPDATE`s (plus a `CHECK` constraint on the table), so concurrent requests or approvals cannot overspend, and two parents approving the same request produce one booking.

## API

All under `/api/stars` (child or higher unless noted; "parent" = partner/admin):

| Endpoint | |
|---|---|
| `GET /me` | balance, reserved, available, next reward, `enabled`, open decisions (parents) |
| `GET/PUT /settings` | `{confirm_tasks}` (PUT: parent) |
| `GET /people` | children and balances (parent) |
| `PUT /tasks/{provider}/{uid}` | `{stars}` 0-100, 0 removes (parent) |
| `GET/POST /rewards`, `PATCH/DELETE /rewards/{id}` | rewards (write: parent; DELETE hides) |
| `POST /requests`, `GET /requests`, `POST /requests/{id}/approve\|decline` (parent), `POST /requests/{id}/cancel` | reward requests |
| `GET /ledger?user_id=` | history (others' history: parent) |
| `GET /pending`, `POST /ledger/{id}/confirm\|reject` | confirmations (parent) |
| `POST /adjust` | `{user_id, delta, title}` bonus or deduction (parent) |

Tasks also accept `stars` on `POST /api/tasks` and `PATCH /api/tasks/{uid}`, return `stars` in task lists, and `POST /api/tasks/{uid}/complete` adds `stars_awarded` when stars were paid or are waiting.

Data lives in the tables `star_tasks`, `star_accounts`, `star_ledger`, `star_rewards` and `star_requests` (one Alembic migration). The confirmation setting is the config key `STARS_CONFIRM_TASKS`.
