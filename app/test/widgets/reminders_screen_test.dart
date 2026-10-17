import 'package:familienhub/screens/more/reminders_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('family switch sends for_family and list marks family reminders', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/reminders', [
      {'id': 1, 'title': 'Müll raus', 'due_at': null, 'completed': false, 'for_family': true},
      {'id': 2, 'title': 'Geschenk besorgen', 'due_at': null, 'completed': false, 'for_family': false},
    ]);
    backend.json('POST', '/api/reminders', {'id': 3, 'title': 'Elternabend', 'completed': false, 'for_family': true});
    await tester.pumpWidget(appWith(backend.api(), const RemindersScreen()));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.groups_outlined), findsOneWidget);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Elternabend');
    await tester.tap(find.byKey(const Key('reminder-family')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();

    final body = bodyOf(backend.sent('POST', '/api/reminders').single);
    expect(body['title'], 'Elternabend');
    expect(body['for_family'], isTrue);
  });

  testWidgets('recurrence is sent and snooze uses the menu', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/reminders', [
      {'id': 5, 'title': 'Pille', 'due_at': '2026-10-14T18:00:00Z', 'completed': false, 'recurrence': 'daily'},
    ]);
    backend.json('POST', '/api/reminders', {'id': 6, 'title': 'Müll', 'completed': false});
    backend.json('POST', '/api/reminders/5/snooze', {'id': 5, 'title': 'Pille', 'completed': false});
    await tester.pumpWidget(appWith(backend.api(), const RemindersScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Täglich'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('snooze-5')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('In 1 Stunde'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/reminders/5/snooze').single), {'minutes': 60});

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Müll');
    await tester.tap(find.byKey(const Key('reminder-recurrence')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Wöchentlich').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/reminders').single)['recurrence'], 'weekly');
  });
}
