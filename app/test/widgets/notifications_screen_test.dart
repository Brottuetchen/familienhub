import 'package:familienhub/screens/more/notifications_screen.dart';
import 'package:familienhub/screens/more/service_keys_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('history shows items with source and marks all read', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/me/notifications', {
      'unread': 1,
      'items': [
        {'id': 2, 'title': 'Waschmaschine fertig', 'body': 'Bitte ausräumen', 'category': 'house', 'route': '/today',
         'source': 'Home Assistant', 'created_at': '2026-10-14T16:00:00Z', 'read': false, 'pushed': true},
        {'id': 1, 'title': 'Neue Aufgabe', 'body': '', 'category': 'task_assigned', 'route': '/tasks',
         'source': 'hub', 'created_at': '2026-10-14T15:00:00Z', 'read': true, 'pushed': false},
      ],
    });
    backend.json('POST', '/api/me/notifications/read', {'marked': 1});
    await tester.pumpWidget(appWith(backend.api(), const NotificationsScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Waschmaschine fertig'), findsOneWidget);
    expect(find.textContaining('Home Assistant'), findsOneWidget);
    expect(find.textContaining('ohne Push'), findsOneWidget);
    expect(bodyOf(backend.sent('POST', '/api/me/notifications/read').single), <String, dynamic>{});
  });

  testWidgets('service key is shown once with a Home Assistant example', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    var created = false;
    backend.on('GET', '/api/admin/service-keys', (_) => jsonResponse(created
        ? [
            {'id': 3, 'name': 'Home Assistant', 'hint': 'fhs_abcd', 'last_used_at': null},
          ]
        : []));
    backend.on('POST', '/api/admin/service-keys', (_) {
      created = true;
      return jsonResponse({'id': 3, 'name': 'Home Assistant', 'hint': 'fhs_abcd', 'key': 'fhs_abcdGEHEIM'}, status: 201);
    });
    await tester.pumpWidget(appWith(backend.api(), const ServiceKeysScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();

    expect(find.text('fhs_abcdGEHEIM'), findsOneWidget);
    expect(find.textContaining('url: "https://hub.test/api/notify"'), findsOneWidget);
    expect(find.textContaining('Bearer fhs_abcdGEHEIM'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Fertig'));
    await tester.pumpAndSettle();
    expect(find.text('fhs_abcdGEHEIM'), findsNothing);
    expect(find.textContaining('fhs_abcd…'), findsOneWidget);
  });
}
