import 'package:familienhub/screens/more/reminders_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('Erinnerung beim Heimkommen anzeigen und anlegen', (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/reminders', [
      {'id': 1, 'title': 'Pakete reinholen', 'due_at': null, 'priority': 'info', 'recurrence': 'none',
       'completed': false, 'source': 'user', 'for_family': false, 'fire_on': 'arrival'},
    ]);
    backend.json('POST', '/api/reminders', {'id': 2});

    await tester.pumpWidget(appWith(backend.api(), const RemindersScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Pakete reinholen'), findsOneWidget);
    expect(find.text('Wenn du heimkommst'), findsOneWidget);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Wäsche aufhängen');
    await tester.tap(find.text('Beim Heimkommen'));
    await tester.pumpAndSettle();
    // ohne Uhrzeit: kein Zeit-Knopf mehr
    expect(find.byIcon(Icons.alarm), findsNothing);
    await tester.tap(find.text('Anlegen'));
    await tester.pumpAndSettle();

    final body = bodyOf(backend.sent('POST', '/api/reminders').single);
    expect(body['title'], 'Wäsche aufhängen');
    expect(body['fire_on'], 'arrival');
    expect(body.containsKey('due_at'), isFalse);
  });
}
