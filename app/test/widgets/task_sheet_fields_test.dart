import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

/// #58: the create sheet shows the fields of the place where the task lands (own place or the recipient's).
void main() {
  setUp(setUpTestEnv);

  Map<String, Object?> place(String id) => {'place': id, 'explicit': null, 'auto': id, 'options': []};

  FakeBackend backend({String mine = 'habitica', String sam = 'nextcloud', String family = 'hub_tasks', bool known = true}) {
    final b = FakeBackend();
    addDefaults(b);
    if (known) {
      b.json('GET', '/api/tasks/me/place', place(mine));
      b.json('GET', '/api/tasks/place/2', {'place': sam});
      b.json('GET', '/api/tasks/place/family', {'place': family});
    }
    b.json('GET', '/api/habitica/options', {'writes_enabled': true, 'tags': [
      {'id': '11111111-1111-4111-8111-111111111111', 'name': 'Haushalt'},
      {'id': '22222222-2222-4222-8222-222222222222', 'name': 'Wichtig'},
    ]});
    b.json('GET', '/api/tasks', {'status': 'ok', 'error': null, 'items': []});
    b.json('POST', '/api/tasks', {'uid': 'n1', 'title': 'X', 'done': false}, status: 201);
    return b;
  }

  Future<void> open(WidgetTester tester, FakeBackend b, {double scale = 1.0, Size size = const Size(400, 2400)}) async {
    await setScreenSize(tester, size);
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        builder: (context, w) => MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
        home: Builder(builder: (context) => Scaffold(body: Center(child: FilledButton(
          onPressed: () => showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true,
              builder: (_) => const TaskCreateSheet()),
          child: const Text('open'))))),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  Future<void> pick(WidgetTester tester, String key, String text) async {
    await tester.tap(find.byKey(Key(key)));
    await tester.pumpAndSettle();
    await tester.tap(find.text(text).last);
    await tester.pumpAndSettle();
  }

  Future<void> save(WidgetTester tester, [String title = 'Aufgabe']) async {
    await tester.enterText(find.byKey(const Key('task-title')), title);
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();
  }

  final difficulty = find.byKey(const Key('task-field-difficulty'));
  final priority = find.byKey(const Key('task-field-priority'));

  testWidgets('own place Habitica: to-do options are offered and sent as native', (tester) async {
    final b = backend();
    await open(tester, b);
    expect(difficulty, findsOneWidget);
    expect(find.byKey(const Key('task-field-attribute')), findsOneWidget);
    expect(find.byKey(const Key('task-field-checklist-hint')), findsOneWidget);
    expect(priority, findsNothing);
    expect(find.byKey(const Key('task-field-tags')), findsOneWidget);

    await pick(tester, 'task-field-difficulty', 'Schwer');
    await tester.tap(find.widgetWithText(FilterChip, 'Wichtig'));
    await tester.pumpAndSettle();
    await save(tester);

    final request = b.sent('POST', '/api/tasks').single;
    expect(request.url.queryParameters['provider'], 'auto');
    final body = bodyOf(request);
    expect(body['native'], {'type': 'todo', 'priority': 2, 'tags': ['22222222-2222-4222-8222-222222222222']});
    expect(body.containsKey('priority'), isFalse);
  });

  testWidgets('switching the recipient switches the fields', (tester) async {
    final b = backend();
    await open(tester, b);
    expect(difficulty, findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Sam'));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/tasks/place/2'), hasLength(1));
    expect(difficulty, findsNothing);
    expect(find.byKey(const Key('task-field-tags')), findsNothing);
    expect(priority, findsOneWidget);
    expect(find.text('CalDAV-Priorität'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Familie'));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/tasks/place/family'), hasLength(1));
    expect(find.text('Priorität'), findsOneWidget); // hub: plain priority
    expect(find.text('CalDAV-Priorität'), findsNothing);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Ich'));
    await tester.pumpAndSettle();
    expect(difficulty, findsOneWidget);
    expect(priority, findsNothing);
  });

  testWidgets('CalDAV recipient: priority is sent, no native options', (tester) async {
    final b = backend();
    await open(tester, b);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Sam'));
    await tester.pumpAndSettle();
    await pick(tester, 'task-field-priority', '3');
    await save(tester);
    final body = bodyOf(b.sent('POST', '/api/tasks').single);
    expect(body['priority'], 3);
    expect(body['assignee_id'], 2);
    expect(body.containsKey('native'), isFalse);
  });

  testWidgets('Habitica recipient: difficulty, but no tags of someone else\'s account', (tester) async {
    final b = backend(mine: 'nextcloud', sam: 'habitica');
    await open(tester, b);
    expect(difficulty, findsNothing);
    expect(priority, findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Sam'));
    await tester.pumpAndSettle();
    expect(difficulty, findsOneWidget);
    expect(find.byKey(const Key('task-field-tags')), findsNothing);
    await pick(tester, 'task-field-difficulty', 'Mittel');
    await save(tester);
    final body = bodyOf(b.sent('POST', '/api/tasks').single);
    expect(body['native'], {'type': 'todo', 'priority': 1.5});
    expect(body['assignee_id'], 2);
  });

  testWidgets('household rotation shows the fields of the family list', (tester) async {
    final b = backend(family: 'nextcloud');
    await open(tester, b);
    await tester.tap(find.byKey(const Key('household-toggle')));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/tasks/place/family'), hasLength(1));
    expect(difficulty, findsNothing);
    expect(find.text('CalDAV-Priorität'), findsOneWidget);
  });

  testWidgets('unknown place (old server): plain sheet, nothing extra is sent', (tester) async {
    final b = backend(known: false);
    await open(tester, b);
    expect(difficulty, findsNothing);
    expect(priority, findsNothing);
    await save(tester);
    final body = bodyOf(b.sent('POST', '/api/tasks').single);
    expect(body.containsKey('native'), isFalse);
    expect(body.containsKey('priority'), isFalse);
  });

  for (final scale in [1.0, 1.3, 2.0]) {
    testWidgets('Habitica fields do not overflow or overlap at 360 dp, text scale $scale', (tester) async {
      final b = backend();
      await open(tester, b, scale: scale, size: const Size(360, 3000));
      expect(tester.takeException(), isNull);
      final keys = ['task-title', 'task-field-difficulty', 'task-field-attribute', 'task-field-tags', 'task-save'];
      final rects = [for (final k in keys) tester.getRect(find.byKey(Key(k)))];
      for (var i = 0; i < rects.length; i++) {
        expect(rects[i].right, lessThanOrEqualTo(360.01));
        for (var j = i + 1; j < rects.length; j++) {
          expect(rects[i].overlaps(rects[j]), isFalse, reason: '${keys[i]} overlaps ${keys[j]}');
        }
      }
    });
  }
}
