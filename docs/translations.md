# Translations (maintainer setup)

The app's UI texts are ARB files in `app/lib/l10n/`. German (`app_de.arb`) is the template; other languages are `app_<code>.arb`. Community members translate on Hosted Weblate; Weblate sends pull requests. Contributor instructions are in [CONTRIBUTING](../CONTRIBUTING.md#translations).

This page is the checklist for the repository owner. The Weblate project needs the owner's account, so it cannot be created from the repository.

## 1. Apply for the free plan
Hosted Weblate (https://hosted.weblate.org) is free for open source through the "libre" plan.

1. Create an account on hosted.weblate.org and sign in (GitHub login works).
2. Create a project: *Projects -> Add new translation project*. Name `Familienhub`, slug `familienhub`, website `https://github.com/Brottuetchen/familienhub`.
3. Choose the **Libre / open source plan** when asked for a plan (or request it at https://hosted.weblate.org/hosting/). The project must use an OSI-approved license (AGPL-3.0 is) and be publicly accessible.
4. Wait for the approval; until then the project may be limited.

## 2. Create the component for the app
In the project: *Add new translation component -> From version control*.

| Setting | Value |
|---|---|
| Component name | `App` (slug `app`) |
| Source code repository | `https://github.com/Brottuetchen/familienhub.git` |
| Repository branch | `main` |
| Push URL | leave empty at first (see section 3) |
| Repository push branch | `weblate` (Weblate pushes here, never to `main`) |
| Merge style | Rebase |
| File mask | `app/lib/l10n/app_*.arb` |
| Monolingual base language file | `app/lib/l10n/app_de.arb` |
| Template for new translations | `app/lib/l10n/app_de.arb` |
| File format | **ARB file** (Flutter) |
| Source language | German (`de`) |
| Edit base file | off (German is changed in code reviews only) |
| Translation license | AGPL-3.0-only |
| Language code style | Default (`fr`, `pt_BR` become `app_fr.arb`, `app_pt_BR.arb`) |
| Allow translation propagation | off |
| Enable suggestions / reviews | optional: *Enable reviews* is a good idea once there are several translators |

Notes:
- The ARB format is monolingual: keys are identifiers, the German file supplies the source texts.
- The `@key` metadata entries (descriptions, placeholders) are kept by Weblate. `tools/check_arb.py` in CI protects them in pull requests.
- New languages: with *Template for new translations* set, Weblate creates `app_<code>.arb` itself and translators can click *Start new translation*. They must translate `languageName` (the language's own name).

## 3. Version control: pull requests, not direct push
`main` is protected, so Weblate must not push to it.

1. Easiest: install the **Weblate GitHub app / use "GitHub" as VCS integration**: in Weblate *Administration -> Settings* (hosted: *Project -> Manage -> Settings -> Version control*) set *Version control system* to **GitHub** (pull requests). On hosted.weblate.org, sign in with GitHub and authorise Weblate for the repository (https://github.com/apps/weblate or the OAuth prompt) so it may push the `weblate` branch and open pull requests.
2. Alternative without the app: add the Weblate user as collaborator with write access to a fork, set *Push URL* to the fork and let Weblate open pull requests from there (*GitHub* VCS).
3. Pull requests go to `main`; merge them by hand like any other PR (CI runs `tools/check_arb.py`). Weblate rebases its branch afterwards.

## 4. Webhooks (both directions)
- **GitHub -> Weblate** (so Weblate sees merged changes quickly): repository *Settings -> Webhooks -> Add webhook*; payload URL `https://hosted.weblate.org/hooks/github/`, content type `application/json`, event *Just the push event*. Hosted Weblate also accepts the GitHub app for this.
- **Weblate -> GitHub**: handled by the GitHub integration above (it opens and updates the pull requests).

## 5. Add-ons (component -> Manage -> Add-ons)
- **Cleanup translation files**: removes keys that are gone from the template.
- **Update ARB files** (*Update ARB files*, a.k.a. "Update ARB files to match the base file"): keeps ARB files in sync with `app_de.arb`, so new German keys appear in every language as untranslated.
- **Squash Git commits**: one commit per language per push, keeps the history tidy (set *Commit message*: `Translations: update {{ language_name }}`).
- **Statistics / Flag unchanged translations** (optional): marks strings that are identical to the source.
- Component setting *Commit message*: `Translations update from Hosted Weblate`; *Committer*: the Weblate bot. The commit text is English as required by CLAUDE.md.

## 6. Quality checks (component -> Settings -> Translation flags)
- Add the flag `icu-message-format` so Weblate validates ICU plurals and placeholders such as `{count}`.
- Keep the default checks on (placeholders, plurals, trailing punctuation).

## 7. After creating the project
- Replace the placeholder in [CONTRIBUTING](../CONTRIBUTING.md#translations) and in the READMEs' "Help translate" line with the project URL, `https://hosted.weblate.org/projects/familienhub/` (optionally the status badge `https://hosted.weblate.org/widget/familienhub/app/svg-badge.svg` linked to that URL).
- Announce the project (issue #25 can then be closed) and label some issues `good first issue` / `translation`.
- Do not store the Weblate API token or any other secret in the repository.

## How German stays the template
- New or changed UI texts: edit `app_de.arb` (template) and `app_en.arb` in the same pull request. Other languages follow through Weblate.
- Missing translations are fine: `flutter gen-l10n` generates a fallback to the German template text for every key a language file lacks.
- `tools/check_arb.py` (CI job `arb`) fails on duplicate keys, invalid JSON, keys not in the template, a missing `languageName`, and placeholder mismatches. Run `python3 tools/check_arb.py --self-test` for its self-test.
- The language picker in the app is generated from the available locales and the `languageName` key, so a new language needs no Dart change. Only iOS needs the code in `CFBundleLocalizations` (`app/ios/Runner/Info.plist`).

## Server texts
The backend translates German source texts through the dictionary `EN` in `backend/app/core/i18n.py` (plus plugin manifest texts and `backend/app/routers/voice.py` phrases). It is a single Python dictionary per language, keyed by the German text, with `{name}` placeholders. Weblate cannot read a Python dictionary, so these texts are **not connected yet**.

Proposed follow-up (not done here to avoid a large refactor):
1. Export the catalogue to gettext PO files (`backend/locale/<code>.po`, German text as `msgid`) with a small script, and load them at startup instead of the Python dictionary (or generate the dictionary from them).
2. Add a second Weblate component: file format *gettext PO file*, file mask `backend/locale/*.po`, template `backend/locale/de.pot` (the German texts as `msgid`), same push settings as above.
3. Keep `tests/test_i18n.py` as the guard that every German message has a catalogue entry; extend `SUPPORTED` beyond `de`/`en`.
4. The push notification and voice phrases need the same treatment.
