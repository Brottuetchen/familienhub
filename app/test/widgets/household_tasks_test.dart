import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('household sends selected rotation order and recurrence', (tester) async {
    await setScreenSize(tester, const Size(400, 1100));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('POST', '/api/tasks', {'uid': 'duty', 'title': 'Müll', 'done': false}, status: 201);
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('task-title')), 'Müll');
    await tester.tap(find.byKey(const Key('household-toggle')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('rotation-2')));
    await tester.tap(find.byKey(const Key('rotation-1')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('task-save')));
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(backend.sent('POST', '/api/tasks').single);
    expect(body['rotation'], [2, 1]);
    expect(body['recurrence'], 'weekly');
    expect(body['list'], 'family');
    expect(body['due'], isNotNull);
    expect(body['habitica'], false);
  });

  testWidgets('household cannot save without a rotation', (tester) async {
    await setScreenSize(tester, const Size(400, 1100));
    final backend = FakeBackend();
    addDefaults(backend);
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('task-title')), 'Müll');
    await tester.tap(find.byKey(const Key('household-toggle')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('task-save')));
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();
    expect(backend.sent('POST', '/api/tasks'), isEmpty);
    expect(find.text('Bitte mindestens eine Person für die Rotation auswählen'), findsOneWidget);
  });

  testWidgets('family duties show recurrence and ordered names', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/tasks', {
      'status': 'ok', 'items': [{
        'uid': 'duty', 'title': 'Müll', 'done': false, 'assignee': 2,
        'recurrence': 'weekly', 'rotation': [2, 1],
        'list': {'name': 'Familie', 'kind': 'family'},
      }],
    });
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.widgetWithText(Tab, 'Familie'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(Tab, 'Familie'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Wöchentlich'), findsWidgets);
    await tester.tap(find.text('Müll').last);
    await tester.pumpAndSettle();
    expect(find.text('Rotation: Sam → Alex'), findsOneWidget);
  });
}
