import 'dart:async';

import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  FakeBackend tasks(String view) {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.on('GET', '/api/tasks', (request) => jsonResponse({
      'status': 'ok',
      'items': request.url.queryParameters['view'] == view ? [{
        'uid': 'duty', 'title': 'Müll rausbringen', 'done': false,
        'list': {'name': 'Liste', 'kind': view == 'family' ? 'family' : 'personal'},
        if (view == 'family') ...{'recurrence': 'weekly', 'rotation': [1, 2]},
      }] : [],
    }));
    backend.json('POST', '/api/tasks/duty/complete', {'uid': 'duty', 'done': true});
    return backend;
  }

  for (final view in ['mine', 'family']) {
    testWidgets('visible checkbox completes $view task without deleting', (tester) async {
      await setScreenSize(tester, const Size(400, 900));
      final backend = tasks(view);
      await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
      await tester.pumpAndSettle();
      if (view == 'family') {
        final tab = find.widgetWithText(Tab, 'Familie');
        await tester.ensureVisible(tab);
        await tester.pumpAndSettle();
        await tester.tap(tab);
        await tester.pumpAndSettle();
      }
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      expect(backend.sent('POST', '/api/tasks/duty/complete'), hasLength(1));
      expect(backend.sent('DELETE', '/api/tasks/duty'), isEmpty);
      expect(find.text('Müll rausbringen'), findsNothing);
    });
  }

  testWidgets('failed checkbox completion keeps task and permits retry', (tester) async {
    final backend = tasks('mine');
    backend.json('POST', '/api/tasks/duty/complete', {'detail': 'Nicht erreichbar'}, status: 503);
    await tester.pumpWidget(appWith(backend.api(), const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(find.text('Müll rausbringen'), findsOneWidget);
    expect(find.text('Nicht erreichbar'), findsOneWidget);
    expect(tester.widget<Checkbox>(find.byType(Checkbox)).onChanged, isNotNull);
    backend.json('POST', '/api/tasks/duty/complete', {'uid': 'duty', 'done': true});
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(backend.sent('POST', '/api/tasks/duty/complete'), hasLength(2));
    expect(find.text('Müll rausbringen'), findsNothing);
  });

  testWidgets('pending checkbox disables repeat completion and swipe', (tester) async {
    final backend = tasks('mine');
    final response = Completer<http.Response>();
    var completions = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/api/tasks/duty/complete') {
          completions++;
          return response.future;
        }
        return backend.routes['${request.method} ${request.url.path}']!(request);
      }),
    );
    await tester.pumpWidget(appWith(api, const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Checkbox));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(tester.widget<Checkbox>(find.byType(Checkbox)).onChanged, isNull);
    await tester.drag(find.text('Müll rausbringen'), const Offset(500, 0));
    await tester.pumpAndSettle();
    expect(completions, 1);
    response.complete(jsonResponse({'uid': 'duty', 'done': true}));
    await tester.pumpAndSettle();
    expect(find.text('Müll rausbringen'), findsNothing);
  });
}
