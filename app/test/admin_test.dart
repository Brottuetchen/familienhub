import 'package:familienhub/screens/admin/admin_house_screen.dart';
import 'package:familienhub/screens/admin/admin_log_screen.dart';
import 'package:familienhub/screens/admin/admin_screen.dart';
import 'package:familienhub/screens/admin/admin_users_screen.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

FakeBackend _backend() {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/admin/overview', {
    'server': {'version': '1.0.0', 'environment': 'production'},
    'plugins': [
      {'id': 'paperless', 'name': 'Paperless-ngx', 'active': true, 'configured': true, 'missing': [],
       'health': {'status': 'ok', 'message': 'Erreichbar', 'latency_ms': 12}},
      {'id': 'seerr', 'name': 'Seerr', 'active': true, 'configured': true, 'missing': [],
       'health': {'status': 'error', 'message': 'Nicht erreichbar'}},
      {'id': 'weather', 'name': 'Wetter', 'active': false, 'configured': false, 'missing': ['X'],
       'health': {'status': 'off', 'message': 'Nicht eingerichtet'}},
    ],
    'push': {'fcm': true, 'webpush': false, 'devices': {'fcm': 3, 'webpush': 0}},
    'users': {'active': 2, 'total': 2},
  });
  b.json('GET', '/api/admin/users', [
    {'id': 1, 'username': 'alex', 'display_name': 'Alex', 'role': 'admin', 'is_active': true, 'devices': 2,
     'links': {'paperless': true, 'seerr': true}},
    {'id': 2, 'username': 'sam', 'display_name': 'Sam', 'role': 'partner', 'is_active': true, 'devices': 1,
     'links': {'paperless': false, 'seerr': null}},
  ]);
  b.json('PATCH', '/api/auth/users/2', {'id': 2});
  b.json('POST', '/api/auth/users', {'id': 3});
  b.json('GET', '/api/admin/house/entities', {
    'status': 'ok',
    'items': [
      {'entity_id': 'light.flur', 'name': 'Flur', 'domain': 'light', 'state': 'off', 'controllable': true},
      {'entity_id': 'light.kueche', 'name': 'Küche', 'domain': 'light', 'state': 'on', 'controllable': true},
      {'entity_id': 'sensor.temp', 'name': 'Wohnzimmer', 'domain': 'sensor', 'state': '21.5', 'unit': '°C', 'controllable': false},
    ],
    'selection': {'display': ['sensor.temp'], 'control': ['light.kueche'], 'max': 6},
  });
  b.json('PUT', '/api/admin/settings', {'saved': true, 'plugins': []});
  b.json('GET', '/api/admin/log', {'items': [
    {'time': '2026-10-17T18:00:00+00:00', 'level': 'WARNING', 'source': 'hermes.media', 'message': 'Seerr nicht erreichbar'},
  ]});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Verwaltung nur für Admins in „Mehr“', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-admin')), findsOneWidget);
    b.json('GET', '/api/auth/me', {...meJson, 'is_admin': false});
    await tester.pumpWidget(appWith(b.api(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-admin')), findsNothing);
  });

  testWidgets('Übersicht: Ampel je Plugin und Probleme oben', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(_backend().api(), const AdminScreen()));
    await tester.pumpAndSettle();
    expect(find.text('1 Problem'), findsOneWidget);
    expect(find.text('Erreichbar · 12 ms'), findsOneWidget);
    expect(find.text('Nicht erreichbar'), findsOneWidget);
    expect(find.textContaining('Push Android: 3 Geräte'), findsOneWidget);
    for (final k in ['admin-users', 'admin-house', 'admin-plugins', 'admin-log']) {
      expect(find.byKey(Key(k)), findsOneWidget);
    }
  });

  testWidgets('Familie: Rolle ändern, eigene Rolle gesperrt, Verbindungen sichtbar', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const AdminUsersScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Alex (du)'), findsOneWidget);
    expect(tester.widget<Switch>(find.byKey(const ValueKey('admin-user-active-1'))).onChanged, isNull);
    expect(find.text('Paperless'), findsNWidgets(2));
    await tester.tap(find.descendant(of: find.byKey(const ValueKey('admin-user-role-2')), matching: find.text('Kind')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/auth/users/2').single), {'role': 'child'});
    await tester.tap(find.byKey(const ValueKey('admin-user-active-2')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/auth/users/2').last), {'is_active': false});
  });

  testWidgets('Person anlegen erst mit gültigen Angaben', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const AdminUsersScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('admin-user-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('new-user-username')), 'oma');
    await tester.enterText(find.byKey(const Key('new-user-email')), 'oma@example.org');
    await tester.enterText(find.byKey(const Key('new-user-password')), 'kurz');
    await tester.pump();
    expect(tester.widget<FilledButton>(find.byKey(const Key('new-user-save'))).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('new-user-password')), 'lang-genug-123');
    await tester.pump();
    await tester.tap(find.byKey(const Key('new-user-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/auth/users').single),
        {'username': 'oma', 'email': 'oma@example.org', 'password': 'lang-genug-123', 'role': 'partner'});
  });

  testWidgets('Haus: Geräte per Auswahl statt IDs, Suche lokal, speichern', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const AdminHouseScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Schalten (1/6)'), findsOneWidget);
    expect(find.text('Anzeigen (1/6)'), findsOneWidget);
    expect(tester.widget<TextButton>(find.byKey(const Key('admin-house-save'))).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('admin-house-search')), 'flur');
    await tester.pump();
    expect(find.byKey(const ValueKey('ha-sensor.temp')), findsNothing);
    expect(b.sent('GET', '/api/admin/house/entities'), hasLength(1));
    await tester.tap(find.descendant(of: find.byKey(const ValueKey('ha-mode-light.flur')), matching: find.byTooltip('Schalten')));
    await tester.pump();
    expect(find.text('Schalten (2/6)'), findsOneWidget);
    await tester.tap(find.byKey(const Key('admin-house-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/settings').single), {
      'values': {'HA_HOUSE_ENTITIES': 'sensor.temp', 'HA_HOUSE_WRITE_ENTITIES': 'light.kueche,light.flur'},
    });
  });

  testWidgets('Sensoren lassen sich nicht schalten', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(appWith(_backend().api(), const AdminHouseScreen()));
    await tester.pumpAndSettle();
    expect(find.descendant(of: find.byKey(const ValueKey('ha-mode-sensor.temp')), matching: find.byTooltip('Schalten')),
        findsNothing);
  });

  testWidgets('Protokoll zeigt die letzten Warnungen', (tester) async {
    await tester.pumpWidget(appWith(_backend().api(), const AdminLogScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Seerr nicht erreichbar'), findsOneWidget);
    expect(find.textContaining('hermes.media'), findsOneWidget);
  });
}
