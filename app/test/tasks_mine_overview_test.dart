import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// "Meine" is the overview of everything I have to do: tasks others gave me show who they are from.
void main() {
  setUp(setUpTestEnv);

  testWidgets('Meine: assigned task shows its creator, own task does not', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/tasks', {
      'status': 'ok', 'error': null,
      'items': [
        {'uid': 'a', 'title': 'Eigene Aufgabe', 'done': false, 'created_by': 1},
        {'uid': 'b', 'title': 'Von Sam', 'done': false, 'created_by': 2, 'assignee': 1},
      ],
    });
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const TasksScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Eigene Aufgabe'), findsOneWidget);
    expect(find.text('Von Sam'), findsOneWidget);
    final subtitles = tester.widgetList<ListTile>(find.byType(ListTile))
        .map((t) => t.subtitle is Text ? (t.subtitle as Text).data : null)
        .whereType<String>()
        .toList();
    expect(subtitles.where((s) => s.contains('Sam')), hasLength(1));
    expect(b.sent('GET', '/api/tasks').first.url.queryParameters['view'], 'mine');
  });
}
