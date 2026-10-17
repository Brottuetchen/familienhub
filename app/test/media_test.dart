import 'package:familienhub/screens/more/media_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

FakeBackend _backend({String status = 'ok'}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/media/requests', {'status': status, 'items': status != 'ok' ? [] : [
    {'id': 11, 'media_type': 'movie', 'tmdb_id': 603, 'title': 'Matrix', 'year': 1999, 'status': 1,
     'status_label': 'Wartet auf Freigabe', 'available': false, 'can_cancel': true},
    {'id': 12, 'media_type': 'tv', 'tmdb_id': 1399, 'title': 'Game of Thrones', 'status': 5,
     'status_label': 'Verfügbar', 'available': true, 'can_cancel': false},
  ]});
  b.json('GET', '/api/media/search', {'status': 'ok', 'items': [
    {'tmdb_id': 120, 'media_type': 'movie', 'title': 'Die Gefährten', 'year': 2001, 'status': 5,
     'status_label': 'Verfügbar', 'requestable': false},
    {'tmdb_id': 84773, 'media_type': 'tv', 'title': 'Die Ringe der Macht', 'year': 2022, 'requestable': true},
  ]});
  b.json('POST', '/api/media/requests', {'id': 20, 'status': 1, 'status_label': 'Wartet auf Freigabe'}, status: 201);
  b.json('DELETE', '/api/media/requests/11', {'deleted': true});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Meine Wünsche mit Stand; wartende lassen sich zurückziehen', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const MediaScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Wartet auf Freigabe'), findsOneWidget);
    expect(find.text('Verfügbar'), findsOneWidget);
    expect(find.descendant(of: find.byKey(const ValueKey('media-req-12')), matching: find.byTooltip('Wunsch zurückziehen')),
        findsNothing);
    await tester.tap(find.descendant(of: find.byKey(const ValueKey('media-req-11')), matching: find.byTooltip('Wunsch zurückziehen')));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/media/requests/11'), hasLength(1));
  });

  testWidgets('Suche nur per Enter; Vorhandenes nicht wünschbar, Neues schon', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const MediaScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('media-search')), 'herr der ringe');
    await tester.pump(const Duration(seconds: 3));
    expect(b.sent('GET', '/api/media/search'), isEmpty);
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/media/search').single.url.queryParameters, {'q': 'herr der ringe'});
    expect(find.byKey(const ValueKey('media-request-movie:120')), findsNothing);
    expect(find.text('Verfügbar'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('media-request-tv:84773')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/media/requests').single), {'media_type': 'tv', 'tmdb_id': 84773});
    expect(find.byKey(const ValueKey('media-done-tv:84773')), findsOneWidget);
  });

  testWidgets('Filme/Serien filtert ohne neue Suche', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const MediaScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('media-search')), 'ringe');
    await tester.pump();
    await tester.tap(find.byKey(const Key('media-search-go')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Serien'));
    await tester.pumpAndSettle();
    expect(find.text('Die Gefährten'), findsNothing);
    expect(find.text('Die Ringe der Macht'), findsOneWidget);
    expect(b.sent('GET', '/api/media/search'), hasLength(1));
  });

  testWidgets('Ohne Seerr-Zugang: Hinweis statt Fehler', (tester) async {
    final b = _backend(status: 'no_account');
    await tester.pumpWidget(appWith(b.api(), const MediaScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('noch keinen Seerr-Zugang'), findsOneWidget);
  });
}
