import 'package:familienhub/models/task.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/tasks/habitica_tasks.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

/// #57: the task sheets must not overflow or overlap on a 360 dp phone, also with larger text.
void main() {
  setUp(setUpTestEnv);

  const scales = [1.0, 1.3, 2.0];

  Widget host(ApiClient api, Widget child, double scale) => ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: MaterialApp(
          locale: const Locale('de', 'DE'),
          builder: (context, w) => MediaQuery(
              data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
          home: child,
        ),
      );

  /// Phone width, very tall so that lazily built lists lay out every field.
  Future<void> phone(WidgetTester tester) => setScreenSize(tester, const Size(360, 5000));

  /// Input-like boxes of the current page: text fields, dropdowns and keyed decorators (date fields).
  Finder boxes() => find.byWidgetPredicate((w) => w is TextField ||
      w.runtimeType.toString().startsWith('DropdownButtonFormField') || (w is InputDecorator && w.key != null));

  void expectClean(WidgetTester tester, {int minBoxes = 2}) {
    expect(tester.takeException(), isNull, reason: 'RenderFlex overflow or other layout exception');
    final rects = <Rect>[];
    for (final e in boxes().evaluate()) {
      rects.add(tester.getRect(find.byElementPredicate((x) => x == e)));
    }
    expect(rects.length, greaterThanOrEqualTo(minBoxes));
    for (var i = 0; i < rects.length; i++) {
      expect(rects[i].left, greaterThanOrEqualTo(0));
      expect(rects[i].right, lessThanOrEqualTo(360.01));
      for (var j = i + 1; j < rects.length; j++) {
        expect(rects[i].overlaps(rects[j]), isFalse, reason: 'fields $i ${rects[i]} and $j ${rects[j]} overlap');
      }
    }
  }

  FakeBackend backend({List<Map<String, Object?>> mine = const []}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/tasks', {'status': 'ok', 'error': null, 'items': mine});
    b.json('GET', '/api/habitica/options', {'writes_enabled': true, 'tags': [
      {'id': '11111111-1111-4111-8111-111111111111', 'name': 'Sehr wichtig und dringend'},
      {'id': '22222222-2222-4222-8222-222222222222', 'name': 'Haushalt'},
    ]});
    return b;
  }

  final hubTask = {'uid': 'h1', 'title': 'Ein sehr langer Aufgabentitel, der in der Detailansicht umbrechen muss', 'notes': 'Notiz ' * 20,
    'done': false, 'due': '2030-03-04', 'priority': 3, 'provider': 'hub_tasks', 'account': '1:hub', 'assignee': 2, 'created_by': 1,
    'list': {'name': 'Familienliste mit langem Namen', 'kind': 'family'}};
  final caldavTask = {...hubTask, 'uid': 'c1', 'provider': 'nextcloud', 'account': '1', 'priority': 5};
  final assignedTask = {'uid': 'a1', 'title': 'Müll rausbringen und Altpapier wegstellen', 'done': false, 'provider': 'assigned',
    'account': '', 'read_only': true, 'via': 'habitica', 'stale': true, 'assignee': 2, 'created_by': 1};
  final rotationTask = {...hubTask, 'uid': 'r1', 'recurrence': 'weekly', 'rotation': [1, 2]};

  for (final scale in scales) {
    group('text scale $scale', () {
      for (final (name, json) in [('hub', hubTask), ('CalDAV', caldavTask)]) {
        testWidgets('edit sheet of a $name task', (tester) async {
          await phone(tester);
          final b = backend(mine: [json]);
          await tester.pumpWidget(host(b.api(), Scaffold(body: TaskDetails(task: Task.fromJson(json), onClose: () {})), scale));
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          await tester.tap(find.text('Aufgabe bearbeiten'));
          await tester.pumpAndSettle();
          expect(find.byKey(const Key('edit-title')), findsOneWidget);
          expectClean(tester, minBoxes: 3);
          // title, notes, priority, due and save are stacked in this order
          final keys = ['edit-title', 'edit-notes', 'edit-priority', 'edit-due', 'edit-save'];
          final rects = [for (final k in keys) tester.getRect(find.byKey(Key(k)))];
          for (var i = 1; i < rects.length; i++) {
            expect(rects[i].top, greaterThanOrEqualTo(rects[i - 1].bottom), reason: '${keys[i]} below ${keys[i - 1]}');
          }
        });
      }

      for (final (name, json) in [('hub', hubTask), ('CalDAV', caldavTask), ('assigned', assignedTask), ('rotation', rotationTask)]) {
        testWidgets('details of a $name task', (tester) async {
          await phone(tester);
          final b = backend(mine: [json]);
          await tester.pumpWidget(host(b.api(), Scaffold(body: TaskDetails(task: Task.fromJson(json), onClose: () {})), scale));
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          expect(find.byIcon(Icons.close), findsOneWidget);
        });
      }

      testWidgets('create sheet, household and recipient chips', (tester) async {
        await phone(tester);
        final b = backend();
        await tester.pumpWidget(host(b.api(), const Scaffold(body: TaskCreateSheet()), scale));
        await tester.pumpAndSettle();
        expectClean(tester, minBoxes: 1);
        await tester.tap(find.byKey(const Key('household-toggle')));
        await tester.pumpAndSettle();
        expectClean(tester, minBoxes: 2);
        final title = tester.getRect(find.byKey(const Key('task-title')));
        final recurrence = tester.getRect(find.byType(DropdownButtonFormField<String>));
        expect(title.overlaps(recurrence), isFalse);
        expect(tester.getRect(find.byKey(const Key('task-save'))).right, lessThanOrEqualTo(360.01));
      });

      final todo = Task.fromJson({'uid': '33333333-3333-4333-8333-333333333333', 'title': 'Habitica to-do', 'provider': 'habitica',
        'account': 'acc', 'done': false, 'native': {'type': 'todo', 'priority': 1.5, 'attribute': 'per', 'tags': [],
          'checklist': [{'id': 'x1', 'text': 'Ein langer Unterpunkt, der umbrechen soll', 'completed': false}],
          'reminders': [{'id': '44444444-4444-4444-8444-444444444444', 'time': '2030-01-01T08:00:00Z'}], 'updatedAt': 'v1'}});
      for (final type in ['todo', 'daily', 'habit', 'reward', 'new']) {
        testWidgets('Habitica editor ($type)', (tester) async {
          await phone(tester);
          final b = backend();
          final task = type == 'new' ? null : Task(uid: todo.uid, title: todo.title, provider: 'habitica', account: 'acc',
              native: {...todo.native, 'type': type, 'frequency': 'weekly', 'everyX': 1, 'up': true, 'down': true, 'value': 10,
                'repeat': {'m': true}, 'daysOfMonth': [1], 'weeksOfMonth': [], 'streak': 3});
          await tester.pumpWidget(host(b.api(), HabiticaTaskEditor(account: 'acc', task: task), scale));
          await tester.pumpAndSettle();
          expect(find.byKey(const Key('native-priority')), findsOneWidget);
          expectClean(tester, minBoxes: 5);
          if (type == 'daily') {
            expect(find.byKey(const Key('native-everyX')), findsOneWidget);
          }
        });
      }
    });
  }
}
