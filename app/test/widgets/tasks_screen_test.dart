import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/screens/tasks/habitica_tasks.dart';
import 'package:familienhub/models/task.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  FakeBackend backendWithTask() {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.on('GET', '/api/tasks', (r) {
      final view = r.url.queryParameters['view'];
      return jsonResponse({
        'status': 'ok',
        'error': null,
        'items': view == 'mine'
            ? [
                {'uid': 't1', 'title': 'Steuer machen', 'done': false, 'list': {'name': 'Privat', 'kind': 'personal'}},
              ]
            : [],
      });
    });
    backend.json('POST', '/api/tasks/t1/complete', {'uid': 't1', 'done': true});
    return backend;
  }

  Future<FakeBackend> pump(WidgetTester tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = backendWithTask();
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    return backend;
  }

  testWidgets('shows four tabs', (tester) async {
    await pump(tester);
    for (final label in ['Meine', 'Für mich', 'Von mir', 'Familie']) {
      expect(find.widgetWithText(Tab, label), findsOneWidget);
    }
    expect(find.text('Steuer machen'), findsOneWidget);
  });

  testWidgets('swipe right completes task', (tester) async {
    final backend = await pump(tester);

    await tester.drag(find.text('Steuer machen'), const Offset(500, 0));
    await tester.pumpAndSettle();

    expect(backend.sent('POST', '/api/tasks/t1/complete'), hasLength(1));
    expect(backend.sent('DELETE', '/api/tasks/t1'), isEmpty);
    expect(find.text('Steuer machen'), findsNothing);
  });

  testWidgets('swipe left asks before deleting', (tester) async {
    final backend = await pump(tester);
    backend.on('DELETE', '/api/tasks/t1', (_) => jsonResponse(null, status: 204));

    await tester.drag(find.text('Steuer machen'), const Offset(-500, 0));
    await tester.pumpAndSettle();
    expect(find.text('Aufgabe löschen?'), findsOneWidget);
    expect(backend.sent('DELETE', '/api/tasks/t1'), isEmpty);

    await tester.tap(find.widgetWithText(FilledButton, 'Löschen'));
    await tester.pumpAndSettle();
    expect(backend.sent('DELETE', '/api/tasks/t1'), hasLength(1));
  });

  testWidgets('create for other person sends assignee_id', (tester) async {
    final backend = await pump(tester);
    backend.json('POST', '/api/tasks', {'uid': 'n1', 'title': 'Pakete holen', 'done': false}, status: 201);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('task-title')), 'Pakete holen');
    await tester.tap(find.widgetWithText(ChoiceChip, 'Sam'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();

    final body = bodyOf(backend.sent('POST', '/api/tasks').single);
    expect(body['title'], 'Pakete holen');
    expect(body['assignee_id'], 2);
    expect(body.containsKey('list'), isFalse);
    // Ich selbst stehe nicht als Person in der Auswahl, sondern als „Ich“
    expect(find.widgetWithText(ChoiceChip, 'Alex'), findsNothing);
  });

  testWidgets('shows readable message on 409 no_write_access', (tester) async {
    final backend = await pump(tester);
    backend.json('POST', '/api/tasks', {
      'detail': {'error': 'no_write_access', 'list': 'Sam'}
    }, status: 409);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('task-title')), 'Geheim');
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();

    expect(find.text('Die Liste „Sam“ ist nicht für dich freigegeben'), findsOneWidget);
  });

  testWidgets('native Habitica reward has redemption instead of a checkbox', (tester) async {
    final backend = backendWithTask();
    backend.json('GET', '/api/tasks', {'status': 'ok', 'items': [
      {'uid': 't1', 'title': 'Belohnung', 'provider': 'habitica', 'account': 'mine',
       'native': {'type': 'reward', 'value': 10}, 'done': false},
    ]});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    expect(find.byType(Checkbox), findsNothing);
    expect(find.byTooltip('Belohnung einlösen'), findsOneWidget);
  });

  testWidgets('equal remote UIDs keep provider and account on completion', (tester) async {
    final backend = backendWithTask();
    backend.json('GET', '/api/tasks', {'status': 'ok', 'items': [
      {'uid': 't1', 'title': 'Nextcloud bleibt', 'provider': 'nextcloud', 'account': '1', 'done': false},
      {'uid': 't1', 'title': 'Andere Quelle', 'provider': 'example', 'account': 'own', 'done': false},
    ]});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.byType(Checkbox).last);
    await tester.pumpAndSettle();
    expect(find.text('Nextcloud bleibt'), findsOneWidget);
    final request = backend.sent('POST', '/api/tasks/t1/complete').single;
    expect(request.url.queryParameters['provider'], 'example');
    expect(request.url.queryParameters['account'], 'own');
  });

  testWidgets('native reward scores own provider and remains available', (tester) async {
    final backend = backendWithTask();
    backend.json('GET', '/api/tasks', {'status': 'ok', 'items': [
      {'uid': 't1', 'title': 'Tee', 'provider': 'habitica', 'account': 'own', 'actions': ['up'], 'native': {'type': 'reward', 'value': 5}},
    ]});
    backend.json('POST', '/api/tasks/t1/actions', {'accepted': true});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Belohnung einlösen'));
    await tester.pumpAndSettle();
    final request = backend.sent('POST', '/api/tasks/t1/actions').single;
    expect(bodyOf(request)['action'], 'up');
    expect(request.url.queryParameters['provider'], 'habitica');
    expect(request.url.queryParameters['account'], 'own');
    expect(backend.sent('POST', '/api/tasks/t1/complete'), isEmpty);
    expect(find.text('Tee'), findsOneWidget);
  });

  testWidgets('native editor writes only changed fields and retains version', (tester) async {
    await setScreenSize(tester, const Size(500, 900));
    final backend = FakeBackend(); addDefaults(backend);
    backend.json('GET', '/api/habitica/options', {'tags': [], 'dayStart': 4, 'timezoneOffset': -120, 'writes_enabled': true});
    backend.json('PATCH', '/api/tasks/t1', {'uid': 't1'});
    final task = Task.fromJson({'uid': 't1', 'title': 'Alt', 'provider': 'habitica', 'account': 'own', 'native': {
      'type': 'daily', 'text': 'Alt', 'updatedAt': 'v1', 'frequency': 'yearly', 'everyX': 2, 'unknown': {'preserve': true}, 'repeat': {'m': false},
    }});
    await tester.pumpWidget(appWith(backend.api(), HabiticaTaskEditor(account: 'own', task: task)));
    await tester.pumpAndSettle();
    expect(find.text('Jährlich'), findsOneWidget); // Anzeige deutsch, gespeichert bleibt „yearly“
    await tester.enterText(find.byKey(const Key('native-text')), 'Neu');
    await tester.scrollUntilVisible(find.byKey(const Key('native-save')), 400, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byKey(const Key('native-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(backend.sent('PATCH', '/api/tasks/t1').single);
    expect(body['native'], {'text': 'Neu'});
    expect(body['expected_version'], 'v1');
  });

  testWidgets('account screen selects only explicitly checked own remote task', (tester) async {
    await setScreenSize(tester, const Size(500, 900));
    final backend = FakeBackend(); addDefaults(backend);
    backend.json('GET', '/api/habitica/account', {'configured': true, 'remote_user_id': 'remote-user', 'account': 'own', 'server_url': 'https://habitica.example', 'writes_enabled': false});
    backend.json('GET', '/api/habitica/tasks', {'status': 'ok', 'items': [
      {'uid': 't1', 'title': 'Auswählen', 'provider': 'habitica', 'account': 'own', 'selected': false, 'native': {'type': 'habit'}},
    ]});
    backend.json('PUT', '/api/tasks/t1/selection', {'selected': true});
    await tester.pumpWidget(appWith(backend.api(), const HabiticaAccountScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Auswählen'));
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    final request = backend.sent('PUT', '/api/tasks/t1/selection').single;
    expect(request.url.queryParameters['provider'], 'habitica');
    expect(request.url.queryParameters['account'], 'own');
    expect(bodyOf(request), {'selected': true});
    expect(backend.sent('POST', '/api/tasks'), isEmpty);
  });


  testWidgets('checklist refresh retains local edits and uses the current native version', (tester) async {
    await setScreenSize(tester, const Size(500, 900));
    final backend = FakeBackend(); addDefaults(backend);
    final remote = {'uid': 't1', 'title': 'Alt', 'provider': 'habitica', 'account': 'own', 'native': {
      'type': 'todo', 'text': 'Alt', 'updatedAt': 'v1', 'checklist': [{'id': 'item', 'text': 'Teil', 'completed': false}],
    }};
    backend.json('GET', '/api/habitica/options', {'tags': [], 'writes_enabled': true});
    backend.json('POST', '/api/tasks/t1/actions', {'accepted': true});
    backend.json('GET', '/api/habitica/tasks', {'status': 'ok', 'items': [{...remote, 'native': {
      ...(remote['native']! as Map), 'updatedAt': 'v2', 'checklist': [{'id': 'item', 'text': 'Teil', 'completed': true}],
    }}]});
    backend.json('PATCH', '/api/tasks/t1', {'uid': 't1'});
    await tester.pumpWidget(appWith(backend.api(), HabiticaTaskEditor(account: 'own', task: Task.fromJson(remote))));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('native-text')), 'Neu');
    await tester.scrollUntilVisible(find.byType(Checkbox), 300, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, -700));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('native-save')));
    await tester.tap(find.byKey(const Key('native-save')));
    await tester.pumpAndSettle();
    final sent = backend.sent('PATCH', '/api/tasks/t1');
    expect(sent, hasLength(1), reason: tester.widgetList<Text>(find.byType(Text)).map((t) => t.data).join(' | '));
    final body = bodyOf(sent.single);
    expect(body['native'], {'text': 'Neu'});
    expect(body['expected_version'], 'v2');
  });


  testWidgets('native editor stays read-only without current operator authority', (tester) async {
    await setScreenSize(tester, const Size(500, 900));
    final backend = FakeBackend(); addDefaults(backend);
    backend.json('GET', '/api/habitica/options', {'tags': [], 'writes_enabled': false});
    await tester.pumpWidget(appWith(backend.api(), const HabiticaTaskEditor(account: 'own')));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('native-save')), 400, scrollable: find.byType(Scrollable).first);
    expect(tester.widget<FilledButton>(find.byKey(const Key('native-save'))).onPressed, isNull);
    expect(backend.sent('POST', '/api/tasks'), isEmpty);
  });


  testWidgets('Erledigtes ist ausgeblendet – auch Habitica – und lässt sich einblenden', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final backend = backendWithTask();
    backend.json('GET', '/api/tasks', {'status': 'ok', 'items': [
      {'uid': 'n1', 'title': 'Nextcloud offen', 'provider': 'nextcloud', 'account': '1', 'done': false},
      {'uid': 'n2', 'title': 'Nextcloud erledigt', 'provider': 'nextcloud', 'account': '1', 'done': true},
      {'uid': 'h1', 'title': '2 Liter Wasser', 'provider': 'habitica', 'account': '1:5457159a', 'done': true,
       'actions': ['down'], 'native': {'type': 'daily'}},
      {'uid': 'h2', 'title': 'Früh ins Bett', 'provider': 'habitica', 'account': '1:5457159a', 'done': false,
       'actions': ['up'], 'native': {'type': 'daily'}},
    ]});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Nextcloud offen'), findsOneWidget);
    expect(find.text('Früh ins Bett'), findsOneWidget);
    expect(find.text('2 Liter Wasser'), findsNothing);
    expect(find.text('Nextcloud erledigt'), findsNothing);
    expect(find.textContaining('1:5457159a'), findsNothing, reason: 'keine internen Konto-IDs');
    expect(find.text('Habitica · Täglich'), findsOneWidget);
    await tester.tap(find.byKey(const Key('tasks-show-done')));
    await tester.pumpAndSettle();
    expect(find.text('Erledigt (2)'), findsOneWidget);
    expect(find.text('2 Liter Wasser'), findsOneWidget);
  });

  testWidgets('Haken sitzt bei Nextcloud und Habitica an derselben Stelle (links)', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final backend = backendWithTask();
    backend.json('GET', '/api/tasks', {'status': 'ok', 'items': [
      {'uid': 'n1', 'title': 'Nextcloud', 'provider': 'nextcloud', 'account': '1', 'done': false},
      {'uid': 'h1', 'title': 'Habitica', 'provider': 'habitica', 'account': '1', 'done': false,
       'actions': ['up'], 'native': {'type': 'todo'}},
    ]});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    final boxes = find.byType(Checkbox);
    expect(boxes, findsNWidgets(2));
    final xs = [for (final e in boxes.evaluate()) tester.getCenter(find.byWidget(e.widget)).dx];
    expect((xs[0] - xs[1]).abs(), lessThan(1), reason: 'gleiche Spalte');
    expect(xs.first, lessThan(100), reason: 'links');
  });
}
