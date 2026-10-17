# Arbeitsregeln für Agenten

- Sprache: UI-Texte, Commits und Doku auf **Deutsch**. Code-Bezeichner auf Englisch.
- **Keine Geheimnisse ins Repo:** keine Tokens, Passwörter, `google-services.json`, Firebase-Service-Account-JSON, VAPID-Private-Keys oder `.env`.
  - Beispiele gehören in `.env.example` mit Platzhaltern.
  - `app/android/app/google-services.json` steht in `.gitignore`.
- **Keine Hausdaten im Code:** keine echten IPs, Domains oder Personennamen als Default. Alles kommt aus der Konfiguration (Projekt soll veröffentlichbar bleiben).
- Bestehende Tests müssen grün bleiben (`cd backend && PYTHONPATH=. pytest -q`). Für neue Backend-Funktionen gibt es Tests mit gemockten Fachsystemen.
- Flutter: `flutter analyze` ohne Fehler, `flutter test` grün.
- Konnektoren degradieren sanft: nicht konfiguriert oder nicht erreichbar → leere Daten und ein Status, keine Exceptions bis in die UI.
- DB-Änderungen nur über Alembic-Migrationen.
- Kleine, thematische Commits. Vor größeren Umbauten erst den bestehenden Code lesen: Hermes hat viele Module schon fertig.
- Zielbild und Entscheidungen: `docs/ENTSCHEIDUNGEN.md`. Bei Widerspruch gilt dieses Dokument.

## Qualitätsregeln (seit 2026-10-13, verbindlich)
- Arbeitsweise, Verbote und Review-Kriterien stehen in `docs/BUILD_PROMPT.md`, Teil A und D. Bei Widerspruch gelten diese.
- Erfolg nur mit kopierter Befehlsausgabe melden. Nie selbst mergen (`main` ist geschützt).
- Tests zuerst. Bestehende Tests nur mit Begründung im PR ändern. Mocks dürfen das Ergebnis nicht vorgeben.
- Testumgebung im Hermes-Container: `~/fh-venv` (`cd backend && PYTHONPATH=. ~/fh-venv/bin/python -m pytest -q`).
