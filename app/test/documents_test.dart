import 'package:familienhub/screens/more/documents_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

Map<String, dynamic> _doc(int id, String title, {String? deadline, String? task}) => {
      'id': id,
      'title': title,
      'created': '2026-10-10',
      'correspondent': 'Telekom',
      'document_type': 'Rechnung',
      'tags': <String>[],
      'url': 'https://paperless.example/documents/$id/details',
      'thumb': '',
      if (deadline != null) 'deadline': deadline,
      if (task != null) 'task': task,
    };

void main() {
  setUp(setUpTestEnv);

  testWidgets('Ohne eigenen Zugang: Token eingeben und verbinden', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    var connected = false;
    b.on('GET', '/api/paperless/recent', (_) => jsonResponse(connected
        ? {'status': 'ok', 'items': [_doc(9, 'Neu')]}
        : {'status': 'no_account', 'items': []}));
    b.json('GET', '/api/paperless/deadlines', {'status': 'ok', 'items': []});
    b.on('PUT', '/api/paperless/account', (_) {
      connected = true;
      return jsonResponse({'connected': true, 'username': 'Alex'});
    });
    await tester.pumpWidget(appWith(b.api(), const DocumentsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Paperless verbinden'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('paperless-token')), ' abc123 ');
    await tester.tap(find.byKey(const Key('paperless-connect')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/paperless/account').single), {'token': 'abc123'});
    expect(find.text('Neu'), findsOneWidget);
  });

  testWidgets('Suche startet erst mit Enter, nicht beim Tippen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/paperless/recent', {'status': 'ok', 'items': [_doc(9, 'Neu')]});
    b.json('GET', '/api/paperless/deadlines', {'status': 'ok', 'items': []});
    b.json('GET', '/api/paperless/search', {'status': 'ok', 'items': [_doc(7, 'Telekom Rechnung')]});
    await tester.pumpWidget(appWith(b.api(), const DocumentsScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('documents-search')), 'telekom');
    await tester.pump(const Duration(seconds: 2));
    expect(b.sent('GET', '/api/paperless/search'), isEmpty);
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    final sent = b.sent('GET', '/api/paperless/search');
    expect(sent, hasLength(1));
    expect(sent.single.url.queryParameters['q'], 'telekom');
    expect(find.text('Telekom Rechnung'), findsOneWidget);
    expect(find.text('Neu'), findsNothing);
  });

  testWidgets('Frist anzeigen und Erinnerung anlegen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/paperless/recent', {'status': 'ok', 'items': []});
    b.json('GET', '/api/paperless/deadlines',
        {'status': 'ok', 'items': [_doc(7, 'Telekom Rechnung', deadline: '2026-10-22', task: 'Rechnung bezahlen')]});
    b.json('POST', '/api/paperless/deadlines/7/remind', {'id': 3, 'created': true}, status: 201);
    await tester.pumpWidget(appWith(b.api(), const DocumentsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Rechnung bezahlen'), findsOneWidget);
    await tester.tap(find.byTooltip('Erinnern'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/paperless/deadlines/7/remind'), hasLength(1));
    expect(find.textContaining('Erinnerung am 22.10.'), findsOneWidget);
  });

  testWidgets('Nicht eingerichtet: nur Hinweis, kein Token-Formular', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/paperless/recent', {'status': 'not_configured', 'items': []});
    b.json('GET', '/api/paperless/deadlines', {'status': 'not_configured', 'items': []});
    await tester.pumpWidget(appWith(b.api(), const DocumentsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Paperless ist nicht eingerichtet'), findsOneWidget);
    expect(find.byKey(const Key('paperless-token')), findsNothing);
  });
}
