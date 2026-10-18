import 'package:familienhub/screens/more/books_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Discover: shelves of German books, request directly.
void main() {
  setUp(setUpTestEnv);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/books/requests', {'status': 'ok', 'error': null, 'items': []});
    b.on('GET', '/api/books/discover', (r) => jsonResponse({
          'status': 'ok', 'error': null, 'shelf': r.url.queryParameters['shelf'],
          'items': [
            if (r.url.queryParameters['shelf'] == 'kids')
              {'work_id': 'openlibrary:OL5W', 'title': 'Gregs Tagebuch', 'author': 'Jeff Kinney', 'year': 2007, 'book_types': []}
            else
              {'work_id': 'openlibrary:OL21745884W', 'title': 'Der Astronaut', 'author': 'Andy Weir', 'year': 2021, 'book_types': []},
          ],
        }));
    b.json('POST', '/api/books/requests', {'items': [], 'queued': false, 'warnings': []});
    return b;
  }

  testWidgets('discover tab shows shelves, switching loads another shelf, request works', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1200));
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('books-tab-discover')));
    await tester.pumpAndSettle();
    expect(find.text('Der Astronaut'), findsOneWidget);
    expect(b.sent('GET', '/api/books/discover').single.url.queryParameters['shelf'], 'popular');

    await tester.ensureVisible(find.byKey(const Key('shelf-kids')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('shelf-kids')));
    await tester.pumpAndSettle();
    expect(find.text('Gregs Tagebuch'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Wünschen'));
    await tester.pumpAndSettle();
    final sent = bodyOf(b.sent('POST', '/api/books/requests').single);
    expect(sent['work_id'], 'openlibrary:OL5W');
    expect(sent['title'], 'Gregs Tagebuch');
  });
}
