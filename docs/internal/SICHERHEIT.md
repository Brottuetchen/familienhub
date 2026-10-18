# Sicherheit

Stand: Prüfung vom 18.10.2026 vor der iOS-App. Dauerhaft in der CI: `.forgejo/workflows/security.yml` (gitleaks, pip-audit,
OSV-Scanner, Trivy, Bandit, Semgrep).

## Grundsätze
- Anmeldung: lokale Konten (bcrypt) oder OIDC mit PKCE, state und nonce. Access-Token (JWT, HS256) kurzlebig, Refresh-Token rotiert.
- Rollen: Admin, Partner, Kind, Gast. Admin-Endpunkte über `require_min_role(admin)`. Haussteuerung erst ab Partner.
- Gespeicherte Geheimnisse:

  | Was | wie gespeichert |
  |---|---|
  | Refresh-Tokens, API-Schlüssel, Dienst-Schlüssel, Einladungscodes | nur als SHA-256 |
  | Zugangsdaten zu Diensten (Nextcloud, Paperless, Habitica, Plugin-Geheimnisse) | Fernet-verschlüsselt |
- Persönliche Daten nur mit dem eigenen Zugang (z. B. Paperless-Token je Person, Seerr per `X-Api-User`).
- Keine Geheimnisse im Repo, keine Hausdaten im Code.

## Öffentliche Endpunkte (ohne Anmeldung)
`/api/health`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/oidc/{start,callback,exchange}`, `/api/setup/{status,admin}`
(nur solange kein Admin existiert, mit Einrichtungscode), `/api/invites/accept` (Code, Fehlversuche begrenzt),
`/api/push/vapid-public-key`, `/api/reminders/{id}/action` (eigenes kurzlebiges Token je Erinnerung und Person).
Alle anderen der rund 130 Endpunkte verlangen eine Anmeldung.

## Prüfung 18.10.2026: Befunde und Stand

| # | Befund | Schwere | Stand |
|---|---|---|---|
| 1 | OIDC-Rücksprung `familienhub://auth?code=…` war nicht an die App gebunden: Eine fremde App mit demselben Schema hätte den Code abfangen und einlösen können. | hoch | **behoben**: PKCE-Bindung (App schickt SHA-256 eines Geheimnisses beim Start, Geheimnis beim Einlösen; Fehlversuch verbrennt den Code). Ohne Hash bleibt der Altweg vorerst offen für ältere App-Versionen. |
| 2 | iOS meldete noch `hubstinger://` statt `familienhub://` an: Der Rücksprung kam in der iPhone-App nicht an. | Funktion | **behoben** |
| 3 | Refresh-Tokens im Klartext in der Datenbank | mittel | **behoben**: nur SHA-256, Migration hasht bestehende Tokens (Sitzungen bleiben gültig). |
| 4 | Passwort ändern ohne Mindestlänge, andere Geräte blieben angemeldet | mittel | **behoben**: mindestens 10 Zeichen, andere Sitzungen enden. |
| 5 | CORS-Standard `*` zusammen mit Anmelde-Cookies (Starlette spiegelt dann jede Herkunft) | mittel (bei Neuinstallationen) | **behoben**: Standard leer = nur gleiche Herkunft; `*` nie mit Cookies. |
| 6 | API-Doku `/docs` im Betrieb offen | niedrig | **behoben**: im Betrieb aus (außer `DEBUG=true`). |
| 7 | Keine Sicherheits-Header | niedrig | **behoben**: `nosniff`, `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `object-src 'none'`, `Referrer-Policy`. |
| 8 | Standard- oder zu kurzer `SECRET_KEY` nur als Warnung | mittel (Neuinstallationen) | **behoben**: im Betrieb startet der Server nicht. |
| 9 | Keine Größenbegrenzung für Anfragen | niedrig | **behoben**: 413 ab 2 MB. |
| 10 | Rollen Kind/Gast haben (außer Haus/Verwaltung) dieselben Schreibrechte wie Partner; seit „Einladen“ vergebbar | Produktentscheidung | **umgesetzt** (Entscheidung 18.10.), siehe unten. |
| 11 | Derselbe `SECRET_KEY` signiert Tokens und ist Basis der Fernet-Verschlüsselung | niedrig | offen (Umstellung braucht Umschlüsselung der gespeicherten Zugangsdaten). |
| 12 | Android erlaubt Klartext-HTTP (`usesCleartextTraffic`), iOS lokale Netze | niedrig | bewusst: Hubs im Heimnetz ohne Zertifikat. Empfehlung: HTTPS über Reverse-Proxy. |

**Rollen (umgesetzt 18.10.):**
- **Gast** (z. B. Babysitter): sieht Heute, Einkauf, Termine; darf Einkauf abhaken und hinzufügen und eigene Erinnerungen anlegen. Kein Löschen von Rezepten und Essensplan, keine Familienaufgaben ändern.
- **Kind:** wie Gast, dazu Aufgaben und Familien-Erinnerungen abhaken, Einkauf löschen, Bücher und Filme wünschen, eigenes Nextcloud-/Habitica-Konto verbinden.
- **Partner/Admin:** Aufgaben, Termine, Essensplan, Rezepte und Familien-Erinnerungen anlegen und ändern, Haus schalten (Admin zusätzlich Verwaltung).
- Der Server prüft jede Aktion (`require_min_role`). Die App blendet zusätzlich aus, was die Rolle nicht darf.

## Melden
Sicherheitslücken bitte nicht als öffentliches Issue, sondern über einen privaten GitHub-Sicherheitshinweis
(Security → Report a vulnerability) melden.
