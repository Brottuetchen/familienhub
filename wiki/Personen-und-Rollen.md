# Personen und Rollen

## Personen einladen (empfohlen)

*Mehr → Verwaltung → Familie & Rollen → Person einladen.* Der Hub erzeugt eine Nachricht mit **App-Link, Server-Adresse und einem Einmal-Code** (7 Tage gültig). Die Person löst ihn in der App ein und **vergibt ihr eigenes Passwort**. So muss niemand ein Passwort per Chat verschicken.

## Person direkt anlegen

Admins können Konten auch direkt anlegen (Benutzername, E-Mail, Passwort, Rolle).

### Regeln für den Benutzernamen

- Nur **Kleinbuchstaben, Ziffern und `. _ -`**, ohne Leerzeichen, 2 bis 40 Zeichen (im Formular erklärt die App: *klein, ohne Leerzeichen*).
- Großbuchstaben werden beim Anlegen automatisch zu Kleinbuchstaben (`Mia` wird `mia`). Ab 1.0.0-beta.3 nimmt das Formular sie an; frühere Versionen lehnten sie ab.
- Die **Anmeldung ist unabhängig von Groß- und Kleinschreibung**: `Mia` und `mia` melden dasselbe Konto an.
- Beispiele: `mia`, `ben.mueller`, `oma-gerda`.

## Rollen

Es gibt vier Rollen. Der Server setzt sie durch; die App blendet nur aus, was eine Rolle nicht darf.

| Was | Gast | Kind | Partner | Admin |
|---|:-:|:-:|:-:|:-:|
| Heute, Einkauf, Termine, Erinnerungen, Essen, Aufgaben ansehen | ✓ | ✓ | ✓ | ✓ |
| Einkauf ergänzen und abhaken, eigene Erinnerungen, ntfy | ✓ | ✓ | ✓ | ✓ |
| Aufgaben und Familien-Erinnerungen abhaken, Einkauf löschen | | ✓ | ✓ | ✓ |
| Bücher, Filme, Serien wünschen; eigenes Nextcloud/Habitica verbinden | | ✓ | ✓ | ✓ |
| Aufgaben, Termine, Essensplan, Rezepte, Familien-Erinnerungen anlegen und ändern | | | ✓ | ✓ |
| Haus steuern (Licht, Schalter, Szenen) | | | ✓ | ✓ |
| Verwaltung: Personen, Plugins (auch aus GitHub), Themes, Dienst-Schlüssel, Log | | | | ✓ |

Typische Wahl: Eltern **Partner** (oder Admin), Kinder **Kind**, Großeltern und Besuch **Gast**. Wer technisch verwaltet, ist **Admin**.

Weitere Besonderheiten:

- **Kindermodus:** Sterne vergeben und Belohnungen freigeben dürfen nur Partner und Admins, siehe [Kindermodus und Belohnungen](Kindermodus-und-Belohnungen).
- **Geburtstage:** Gäste sehen sie nicht, siehe [Geburtstage](Geburtstage).
- **Stundenplan:** gehört den Konten mit der Rolle *Kind*, siehe [Stundenplan](Stundenplan).

## Anmeldung über OIDC (optional)

Authentik, Keycloak u. ä.: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` setzen und die Weiterleitungs-Adressen aus der `.env.example` beim Anbieter eintragen (bei Authentik die Grant-Typen `authorization_code` und `refresh_token`). Eingeladene Personen melden sich mit derselben E-Mail-Adresse an. Mit `OIDC_AUTO_CREATE=true` werden Konten bei der ersten Anmeldung angelegt: Beschränkt dann die Anwendung beim Anbieter auf eure Familie. Passkeys und 2FA sind im Hub nicht eingebaut, nutzt sie über euren Identitätsanbieter.

Referenz (Englisch): [Security: Roles](https://github.com/Brottuetchen/familienhub/blob/main/docs/security.md#roles) · [Getting started: People and sign-in](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#4-people-and-sign-in)
