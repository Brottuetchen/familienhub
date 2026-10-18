import 'dart:convert';
import 'dart:io';

import 'package:familienhub/l10n/l10n.dart';
import 'package:familienhub/models/task.dart';
import 'package:familienhub/screens/more/appearance_screen.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// Englische Fassung (#5): Sprache nach Gerät oder Wahl, alle Texte übersetzt.
void main() {
  setUp(setUpTestEnv);
  tearDown(() => setAppLanguage('de'));

  test('Jeder deutsche Text hat eine englische Übersetzung mit denselben Platzhaltern', () {
    Map<String, dynamic> arb(String lang) =>
        jsonDecode(File('lib/l10n/app_$lang.arb').readAsStringSync()) as Map<String, dynamic>;
    final de = arb('de'), en = arb('en');
    final keys = de.keys.where((k) => !k.startsWith('@')).toList();
    expect(keys.length, greaterThan(500));
    final placeholder = RegExp(r'(?<![\w=])\{(\w+)[,}]'); // nicht die Zweige von plural ({Termin})
    for (final k in keys) {
      expect(en[k], isA<String>(), reason: 'fehlt im Englischen: $k');
      final want = placeholder.allMatches(de[k] as String).map((m) => m.group(1)).toSet();
      final got = placeholder.allMatches(en[k] as String).map((m) => m.group(1)).toSet();
      expect(got, want, reason: 'Platzhalter in $k');
    }
  });

  test('Sprache: Wahl schlägt Gerät, unbekannte Gerätesprache wird Englisch', () {
    expect(resolveLanguage('en', device: const Locale('de')), 'en');
    expect(resolveLanguage('de', device: const Locale('en')), 'de');
    expect(resolveLanguage('system', device: const Locale('de', 'AT')), 'de');
    expect(resolveLanguage('system', device: const Locale('fr')), 'en');
    expect(resolveLanguage(null, device: const Locale('en', 'GB')), 'en');
  });

  test('Datum und Plural auf Englisch', () {
    setAppLanguage('en');
    final now = DateTime(2026, 10, 19, 9);
    expect(dayLabel(DateTime(2026, 10, 19), now: now), 'Today');
    expect(dayLabel(DateTime(2026, 10, 22), now: now), 'Thursday, October 22');
    expect(l10n.pendingWaiting(1), '1 change waiting for network');
    expect(l10n.pendingWaiting(3), '3 changes waiting for network');
    expect(TaskView.forMe.label, 'For me');
    setAppLanguage('de');
    expect(dayLabel(DateTime(2026, 10, 22), now: now), 'Donnerstag, 22. Oktober');
    expect(l10n.pendingWaiting(3), '3 Änderungen warten auf Netz');
  });

  testWidgets('Mehr-Seite auf Englisch', (tester) async {
    setAppLanguage('en');
    await setScreenSize(tester, const Size(420, 2400));
    final backend = FakeBackend();
    addDefaults(backend);
    await tester.pumpWidget(appWith(backend.api(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.text('More'), findsOneWidget);
    expect(find.text('Reminders'), findsOneWidget);
    expect(find.text('Sign out'), findsOneWidget);
    expect(find.text('Erinnerungen'), findsNothing);
  });

  testWidgets('Darstellung: Sprache wählen wird auf dem Gerät gespeichert', (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/themes', {'items': []});
    await tester.pumpWidget(appWith(backend.api(), const AppearanceScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect((await SharedPreferences.getInstance()).getString(languagePrefKey), 'en');
  });
}
