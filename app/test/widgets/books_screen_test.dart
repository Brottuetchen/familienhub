import 'package:familienhub/screens/more/books_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/books/requests', {
      'status': 'ok',
      'error': null,
      'items': [
        {'id': 7, 'status': 'completed', 'status_label': 'Fertig', 'title': 'Die Kunst des Krieges', 'book_type': 'audiobook'},
      ],
    });
    b.json('GET', '/api/books/search', {
      'status': 'ok',
      'error': null,
      'items': [
        {'work_id': 'ol:1', 'title': 'Momo', 'author': 'Michael Ende', 'year': 1973, 'cover_url': null, 'book_types': ['ebook', 'audiobook']},
      ],
    });
    b.json('POST', '/api/books/requests', {'items': [], 'queued': false, 'warnings': []}, status: 201);
    return b;
  }

  testWidgets('shows own requests with status', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    await tester.pumpWidget(appWith(backend().api(), const BooksScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Die Kunst des Krieges'), findsOneWidget);
    expect(find.text('Fertig'), findsOneWidget);
  });

  testWidgets('search and request sends chosen kind', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final b = backend();
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Hörbuch'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('book-search')), 'Momo');
    // Gesucht wird erst auf Enter; die Art filtert die App selbst (schont Google Books)
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();

    final search = b.sent('GET', '/api/books/search').single;
    expect(search.url.queryParameters, {'q': 'Momo'});
    await tester.tap(find.widgetWithText(FilledButton, 'Wünschen'));
    await tester.pumpAndSettle();

    final body = bodyOf(b.sent('POST', '/api/books/requests').single);
    expect(body['work_id'], 'ol:1');
    expect(body['book_type'], 'audiobook');
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
  });
}
