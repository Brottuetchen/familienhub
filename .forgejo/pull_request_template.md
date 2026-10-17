## Arbeitspaket
WP <nr> – <Titel>  (Auftrag: docs/BUILD_PROMPT.md, Teil C)

## Pflicht-Ausgaben (wörtlich, nicht zusammenfassen)
```
<pytest -q | tail -15>
```
```
<ruff check app tests | tail -5>
```
```
<flutter analyze / flutter test, falls app/ geändert, sonst "app/ unverändert">
```

## Neue Tests (Namen laut Testliste)
- 

## Geänderte bestehende Tests
<keine> | <Testname – Grund – Verweis auf docs/ENTSCHEIDUNGEN.md>

## Abweichungen vom Auftrag
<keine> | <was, warum>

## Selbstprüfung (Teil D)
- [ ] 0 failed / 0 errors
- [ ] keine Mocks, die das Ergebnis vorgeben
- [ ] kein geschlucktes `except` ohne Log + Status + Test
- [ ] keine Platzhalter / TODO-Stubs
- [ ] Bibliotheks-APIs in der installierten Version geprüft
- [ ] keine Hausdaten / Geheimnisse
