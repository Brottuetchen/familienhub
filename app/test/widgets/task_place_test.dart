import 'package:familienhub/screens/more/profile_screen.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

/// #38: tasks go where the recipient works. No provider choice for the creator; the profile sets the own place.
void main() {
  setUp(setUpTestEnv);

  Map<String, Object?> place({String? explicit, String auto = 'nextcloud', bool habitica = true}) => {
        'place': explicit ?? auto,
        'explicit': explicit,
        'auto': auto,
        'options': [
          {'id': 'nextcloud', 'name': 'CalDAV (Nextcloud …)', 'available': true},
          {'id': 'habitica', 'name': 'Habitica', 'available': habitica},
          {'id': 'hub_tasks', 'name': 'Aufgaben im Hub', 'available': true},
        ],
      };

  FakeBackend backendWith({List<Map<String, Object?>> tasks = const []}) {
    final backend = FakeBackend();
    addDefaults(backend);
    // Two configured accounts used to trigger the provider chooser
    backend.json('GET', '/api/tasks/providers', {'items': [
      {'id': 'nextcloud', 'name': 'Nextcloud', 'account': '1', 'configured': true},
      {'id': 'habitica', 'name': 'Habitica', 'account': '1:h', 'configured': true},
    ]});
    backend.json('GET', '/api/tasks', {'status': 'ok', 'error': null, 'items': tasks});
    backend.json('POST', '/api/tasks', {'uid': 'n1', 'title': 'Pakete', 'done': false}, status: 201);
    return backend;
  }

  Future<void> openSheet(WidgetTester tester) async {
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
  }

  testWidgets('task for another person: no provider choice, routed by the server', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = backendWith();
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();

    await openSheet(tester);
    // straight to the sheet, even with two connected accounts
    expect(find.text('Anbieter und eigenes Konto wählen'), findsNothing);
    expect(find.byKey(const Key('task-title')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('task-title')), 'Pakete');
    await tester.tap(find.widgetWithText(ChoiceChip, 'Sam'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('task-lands-hint')), findsOneWidget);
    expect(find.text('Die Aufgabe landet dort, wo Sam sie bekommt.'), findsOneWidget);
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();

    final request = backend.sent('POST', '/api/tasks').single;
    expect(request.url.queryParameters['provider'], 'auto');
    expect(request.url.queryParameters.containsKey('account'), isFalse);
    expect(bodyOf(request)['assignee_id'], 2);
  });

  testWidgets('family task and own task also leave the provider to the server', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = backendWith();
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();

    await openSheet(tester);
    await tester.enterText(find.byKey(const Key('task-title')), 'Gemeinsam');
    await tester.tap(find.widgetWithText(ChoiceChip, 'Familie'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('task-lands-hint')), findsNothing);
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();
    var request = backend.sent('POST', '/api/tasks').single;
    expect(request.url.queryParameters['provider'], 'auto');
    expect(bodyOf(request)['list'], 'family');

    await openSheet(tester);
    await tester.enterText(find.byKey(const Key('task-title')), 'Für mich');
    await tester.tap(find.byKey(const Key('task-save')));
    await tester.pumpAndSettle();
    request = backend.sent('POST', '/api/tasks').last;
    expect(request.url.queryParameters['provider'], 'auto');
    expect(bodyOf(request).containsKey('assignee_id'), isFalse);
  });

  testWidgets('"Von mir" shows a task living in the recipient\'s place as status only', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = backendWith();
    backend.on('GET', '/api/tasks', (r) => jsonResponse({'status': 'ok', 'error': null, 'items': [
      if (r.url.queryParameters['view'] == 'from_me') ...[
        {'uid': 'r1', 'title': 'Müll rausbringen', 'done': false, 'provider': 'assigned', 'account': '', 'read_only': true,
         'via': 'nextcloud', 'assignee': 2, 'created_by': 1},
        {'uid': 'r2', 'title': 'Altpapier', 'done': true, 'provider': 'assigned', 'account': '', 'read_only': true,
         'via': 'habitica', 'stale': true, 'assignee': 2, 'created_by': 1},
      ],
    ]}));
    backend.json('POST', '/api/tasks/r1/complete', {'uid': 'r1'});
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(Tab, 'Von mir'));
    await tester.pumpAndSettle();

    expect(find.text('Müll rausbringen'), findsOneWidget);
    expect(find.textContaining('liegt in Nextcloud'), findsOneWidget);
    final check = tester.widget<Checkbox>(find.byKey(const Key('assigned-check-r1')));
    expect(check.value, isFalse);
    expect(check.onChanged, isNull); // the recipient completes it, not the creator
    expect(tester.widget<Dismissible>(find.byType(Dismissible)).direction, DismissDirection.none); // no swipe to complete or delete someone else's task
    expect(backend.sent('POST', '/api/tasks/r1/complete'), isEmpty);
    expect(find.text('Müll rausbringen'), findsOneWidget);

    // done and stale tasks show up once "show done" is on, with the honest status
    await tester.tap(find.byKey(const Key('tasks-show-done')));
    await tester.pumpAndSettle();
    expect(tester.widget<Checkbox>(find.byKey(const Key('assigned-check-r2'))).value, isTrue);
    expect(find.textContaining('Status unbekannt'), findsOneWidget);
  });

  group('profile: task place', () {
    Future<FakeBackend> pumpProfile(WidgetTester tester, {Object? info, int status = 200}) async {
      await setScreenSize(tester, const Size(420, 1400));
      final b = FakeBackend();
      addDefaults(b);
      if (info != null) b.json('GET', '/api/tasks/me/place', info, status: status);
      await tester.pumpWidget(appWith(b.api(), const ProfileScreen()));
      await tester.pumpAndSettle();
      return b;
    }

    testWidgets('shows the derived default and saves an explicit choice', (tester) async {
      String? stored; // server state: the place chosen so far
      final b = await pumpProfile(tester, info: place());
      b.on('GET', '/api/tasks/me/place', (_) => jsonResponse(place(explicit: stored)));
      b.on('PUT', '/api/tasks/me/place', (r) {
        stored = bodyOf(r)['place'] as String?;
        return jsonResponse(place(explicit: stored));
      });
      expect(find.byKey(const Key('task-place-section')), findsOneWidget);
      expect(find.text('Automatisch (Nextcloud)'), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('task-place-habitica')));
      await tester.tap(find.byKey(const Key('task-place-habitica')));
      await tester.pumpAndSettle();
      expect(bodyOf(b.sent('PUT', '/api/tasks/me/place').single), {'place': 'habitica'});
      expect(find.text('Aufgabenort gespeichert'), findsOneWidget);

      await tester.ensureVisible(find.byKey(const Key('task-place-auto')));
      await tester.tap(find.byKey(const Key('task-place-auto')));
      await tester.pumpAndSettle();
      expect(bodyOf(b.sent('PUT', '/api/tasks/me/place').last), {'place': null});
    });

    testWidgets('a place without a connected account cannot be chosen', (tester) async {
      final b = await pumpProfile(tester, info: place(habitica: false));
      await tester.ensureVisible(find.byKey(const Key('task-place-habitica')));
      await tester.tap(find.byKey(const Key('task-place-habitica')));
      await tester.pumpAndSettle();
      expect(b.sent('PUT', '/api/tasks/me/place'), isEmpty);
    });

    testWidgets('hidden when the server does not know the setting', (tester) async {
      await pumpProfile(tester, info: {'detail': 'Not Found'}, status: 404);
      expect(find.byKey(const Key('task-place-section')), findsNothing);
      expect(find.byKey(const Key('profile-save')), findsOneWidget);
    });
  });
}
