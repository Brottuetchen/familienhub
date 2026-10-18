import 'package:familienhub/screens/more/ntfy_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// ntfy per person (#23).
void main() {
  setUp(setUpTestEnv);

  Widget card(FakeBackend b) => appWith(b.api(), const Scaffold(body: SingleChildScrollView(child: NtfyCard())));

  const off = {'available': true, 'server': 'https://ntfy.example.test', 'enabled': false, 'topic': null, 'subscribe_url': null};
  const on = {'available': true, 'server': 'https://ntfy.example.test', 'enabled': true, 'topic': 'fh_geheim123456789',
      'subscribe_url': 'https://ntfy.example.test/fh_geheim123456789'};

  testWidgets('without an ntfy server on the hub the card stays hidden', (tester) async {
    final b = FakeBackend()..json('GET', '/api/me/ntfy', {'available': false, 'enabled': false});
    await tester.pumpWidget(card(b));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ntfy-enabled')), findsNothing);
  });

  testWidgets('switching on shows server, secret topic and actions', (tester) async {
    final b = FakeBackend();
    var state = off;
    b.on('GET', '/api/me/ntfy', (_) => jsonResponse(state));
    b.on('PUT', '/api/me/ntfy', (r) {
      expect(bodyOf(r)['enabled'], true);
      state = on;
      return jsonResponse(on);
    });
    await tester.pumpWidget(card(b));
    await tester.pumpAndSettle();
    expect(find.text('Mitteilungen über ntfy'), findsOneWidget);
    expect(find.byKey(const Key('ntfy-topic')), findsNothing);

    await tester.tap(find.byKey(const Key('ntfy-enabled')));
    await tester.pumpAndSettle();
    expect(b.sent('PUT', '/api/me/ntfy'), hasLength(1));
    expect(find.text('fh_geheim123456789'), findsOneWidget);
    expect(find.textContaining('https://ntfy.example.test'), findsOneWidget);
    expect(find.text('Topic kopieren'), findsOneWidget);
    expect(find.text('In ntfy öffnen'), findsOneWidget);
  });

  testWidgets('new topic only after confirmation', (tester) async {
    final b = FakeBackend();
    var state = on;
    b.on('GET', '/api/me/ntfy', (_) => jsonResponse(state));
    b.on('POST', '/api/me/ntfy/new-topic', (_) {
      state = {...on, 'topic': 'fh_neu98765432100', 'subscribe_url': 'https://ntfy.example.test/fh_neu98765432100'};
      return jsonResponse(state);
    });
    await tester.pumpWidget(card(b));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('ntfy-new-topic')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Abbrechen'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/me/ntfy/new-topic'), isEmpty);

    await tester.tap(find.byKey(const Key('ntfy-new-topic')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Neues Topic'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/me/ntfy/new-topic'), hasLength(1));
    expect(find.text('fh_neu98765432100'), findsOneWidget);
  });
}
