import 'package:familienhub/screens/more/api_tokens_screen.dart';
import 'dart:async';

import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:http/testing.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('creating a token shows it once and lists it', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    var created = false;
    backend.on('GET', '/api/auth/api-tokens', (_) => jsonResponse(created
        ? [
            {'id': 1, 'name': 'Sprachassistent', 'hint': 'fhp_abcd', 'created_at': '2026-10-14T16:00:00', 'last_used_at': null},
          ]
        : []));
    backend.on('POST', '/api/auth/api-tokens', (_) {
      created = true;
      return jsonResponse({'id': 1, 'name': 'Sprachassistent', 'hint': 'fhp_abcd', 'token': 'fhp_abcdGEHEIM'}, status: 201);
    });

    await tester.pumpWidget(appWith(backend.api(), const ApiTokensScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Noch kein Zugang angelegt'), findsOneWidget);

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();

    expect(bodyOf(backend.sent('POST', '/api/auth/api-tokens').single), {'name': 'Sprachassistent'});
    expect(find.text('fhp_abcdGEHEIM'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Fertig'));
    await tester.pumpAndSettle();
    expect(find.text('fhp_abcdGEHEIM'), findsNothing);
    expect(find.textContaining('fhp_abcd…'), findsOneWidget);
  });

  testWidgets('double tap on Create and the real response shape do not crash', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.on('GET', '/api/auth/api-tokens', (_) => jsonResponse([]));
    // Exactly what backend/app/routers/auth.py returns for POST /api/auth/api-tokens.
    backend.on(
        'POST',
        '/api/auth/api-tokens',
        (_) => jsonResponse({
              'id': 7,
              'name': 'Sprachassistent',
              'hint': 'fhp_abcd',
              'created_at': '2026-10-18T09:00:00.123456',
              'last_used_at': null,
              'token': 'fhp_abcdGEHEIM',
            }, status: 201));

    await tester.pumpWidget(appWith(backend.api(), const ApiTokensScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    final create = find.widgetWithText(FilledButton, 'Anlegen');
    await tester.tap(create);
    await tester.tap(create, warnIfMissed: false);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(backend.sent('POST', '/api/auth/api-tokens'), hasLength(1));
    expect(find.text('fhp_abcdGEHEIM'), findsOneWidget);

    // Copy shows a snackbar from inside the dialog
    await tester.tap(find.widgetWithText(TextButton, 'Kopieren'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Kopiert'), findsOneWidget);
  });

  testWidgets('a response without plaintext shows a hint instead of crashing', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.on('GET', '/api/auth/api-tokens', (_) => jsonResponse([]));
    backend.on('POST', '/api/auth/api-tokens',
        (_) => jsonResponse({'id': 7, 'name': 'Sprachassistent', 'hint': 'fhp_abcd'}, status: 201));

    await tester.pumpWidget(appWith(backend.api(), const ApiTokensScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('new-token')), findsNothing);
    expect(find.textContaining('Schlüssel kam nicht an'), findsOneWidget);
  });

  testWidgets('leaving the screen while the key is being created does not crash', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.on('GET', '/api/auth/api-tokens', (_) => jsonResponse([]));
    backend.on('POST', '/api/auth/api-tokens',
        (_) => jsonResponse({'id': 7, 'name': 'Sprachassistent', 'hint': 'fhp_abcd', 'created_at': null, 'last_used_at': null, 'token': 'fhp_abcdGEHEIM'}, status: 201));
    // Slow server: the answer only arrives after the user went back.
    final gate = Completer<void>();
    final api = ApiClient(
      httpClient: MockClient((request) async {
        if (request.method == 'POST') await gate.future;
        return backend.routes['${request.method} ${request.url.path}']!(request);
      }),
      store: MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1'),
    );

    await tester.pumpWidget(appWith(
        api,
        Builder(
            builder: (context) => Scaffold(
                body: Center(
                    child: ElevatedButton(
                        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ApiTokensScreen())),
                        child: const Text('open')))))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Anlegen'));
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byType(ApiTokensScreen), findsNothing);

    gate.complete();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
