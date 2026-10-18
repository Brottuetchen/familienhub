import 'package:familienhub/screens/admin/admin_feedback_screen.dart';
import 'package:familienhub/screens/more/feedback_screen.dart';
import 'package:familienhub/services/app_info.dart';
import 'package:familienhub/services/error_reporter.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  test('GitHub-Issue vorausgefüllt: Titel, Text, Version, Plattform, Bereich – ohne Server-Adresse', () {
    final uri = githubIssueUri(text: 'Einkauf lädt langsam\nSeit gestern', area: 'Einkauf');
    expect(uri.toString(), startsWith('https://github.com/Brottuetchen/familienhub/issues/new?'));
    expect(uri.queryParameters['title'], 'Einkauf lädt langsam');
    expect(uri.queryParameters['body'], contains('Seit gestern'));
    expect(uri.queryParameters['body'], contains('App-Version: $appVersion'));
    expect(uri.queryParameters['body'], contains('Bereich: Einkauf'));
    expect(uri.queryParameters['labels'], 'feedback');
    expect(uri.toString(), isNot(contains('hub.test')));
  });

  testWidgets('Feedback: an die Familie senden oder als GitHub-Issue öffnen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('POST', '/api/feedback', {'id': 1}, status: 201);
    final opened = <Uri>[];
    await tester.pumpWidget(appWith(b.api(), FeedbackScreen(openUrl: (u) async {
      opened.add(u);
      return true;
    })));
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(find.byKey(const Key('feedback-family'))).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('feedback-text')), 'Haken auf Heute hängt');
    await tester.pump();
    await tester.tap(find.byKey(const Key('feedback-github')));
    await tester.pump();
    expect(opened.single.queryParameters['title'], 'Haken auf Heute hängt');
    await tester.tap(find.byKey(const Key('feedback-family')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/feedback').single);
    expect(body['text'], 'Haken auf Heute hängt');
    expect(body['app_version'], appVersion);
    expect(body['platform'], isNotEmpty);
  });

  testWidgets('Verwaltung: Feedback erledigen und an GitHub weitergeben', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/admin/feedback', {'items': [
      {'id': 3, 'text': 'Pixel-Theme zu dunkel', 'area': 'Darstellung', 'platform': 'android', 'app_version': '1.0.0+420',
       'created_at': '2026-10-18T07:00:00', 'done': false, 'from': 'Mia'},
    ]});
    b.json('POST', '/api/admin/feedback/3/done', {'done': true});
    final opened = <Uri>[];
    await tester.pumpWidget(appWith(b.api(), AdminFeedbackScreen(openUrl: (u) async {
      opened.add(u);
      return true;
    })));
    await tester.pumpAndSettle();
    expect(find.text('Pixel-Theme zu dunkel'), findsOneWidget);
    await tester.tap(find.byTooltip('Auf GitHub melden'));
    await tester.pump();
    expect(opened.single.queryParameters['body'], contains('Bereich: Darstellung'));
    await tester.tap(find.byTooltip('Erledigt'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/admin/feedback/3/done'), hasLength(1));
  });

  test('App-Fehler: einmal je Meldung, nur angemeldet', () async {
    final b = FakeBackend();
    b.json('POST', '/api/client-errors', {'accepted': true}, status: 202);
    ErrorReporter.reset();
    ErrorReporter.api = b.api();
    ErrorReporter.report('Null check operator', StackTrace.current);
    ErrorReporter.report('Null check operator', StackTrace.current);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(b.sent('POST', '/api/client-errors'), hasLength(1));
    ErrorReporter.reset();
    ErrorReporter.api = b.api(store: MemorySessionStore(url: 'https://hub.test'));
    ErrorReporter.report('Abgemeldet', null);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(b.sent('POST', '/api/client-errors'), hasLength(1), reason: 'ohne Anmeldung nichts senden');
    ErrorReporter.api = null;
  });
}
