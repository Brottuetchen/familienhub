import 'package:familienhub/screens/more/api_tokens_screen.dart';
import 'package:flutter/material.dart';
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
}
