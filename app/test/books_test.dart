import 'package:familienhub/screens/more/books_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

FakeBackend _backend() {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/books/requests', {'status': 'ok', 'items': [
    {'id': 1, 'status': 'searching', 'status_label': 'Wird gesucht', 'title': 'Momo', 'author': 'Michael Ende', 'book_type': 'audiobook'},
  ]});
  b.json('GET', '/api/books/search', {'status': 'ok', 'items': [
    {'work_id': 'ol:1', 'title': 'Momo', 'author': 'Michael Ende', 'book_types': ['ebook', 'audiobook']},
    {'work_id': 'ol:2', 'title': 'Nur Hörbuch', 'author': 'X', 'book_types': ['audiobook']},
  ]});
  b.json('POST', '/api/books/requests', {'items': [], 'queued': false, 'warnings': []}, status: 201);
  return b;
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Tippen sucht nicht, erst Enter – genau einmal und ohne Art-Filter', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('book-search')), 'Mo');
    await tester.enterText(find.byKey(const Key('book-search')), 'Momo');
    await tester.pump(const Duration(seconds: 3));
    expect(b.sent('GET', '/api/books/search'), isEmpty);
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    final sent = b.sent('GET', '/api/books/search');
    expect(sent, hasLength(1));
    expect(sent.single.url.queryParameters, {'q': 'Momo'});
    expect(find.widgetWithText(ListTile, 'Momo'), findsOneWidget);
  });

  testWidgets('E-Book/Hörbuch wechseln filtert ohne neue Suche', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('book-search')), 'Momo');
    await tester.pump();
    await tester.tap(find.byKey(const Key('book-search-go')));
    await tester.pumpAndSettle();
    expect(find.text('Nur Hörbuch'), findsNothing); // E-Book ist Standard
    await tester.tap(find.text('Hörbuch'));
    await tester.pumpAndSettle();
    expect(find.text('Nur Hörbuch'), findsOneWidget);
    expect(b.sent('GET', '/api/books/search'), hasLength(1));
  });

  testWidgets('Zu kurze Suche fragt Shelfarr nicht', (tester) async {
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('book-search')), 'Mo');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/books/search'), isEmpty);
    expect(find.text('Mindestens 3 Zeichen'), findsOneWidget);
  });

  testWidgets('Schon gewünschte Titel sind markiert, neue lassen sich wünschen', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const BooksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hörbuch'));
    await tester.enterText(find.byKey(const Key('book-search')), 'Momo');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('book-done-ol:1')), findsOneWidget, reason: 'Momo als Hörbuch schon gewünscht');
    await tester.tap(find.byKey(const ValueKey('book-request-ol:2')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/books/requests').single)['book_type'], 'audiobook');
    expect(find.byKey(const ValueKey('book-done-ol:2')), findsOneWidget);
    // Als E-Book ist Momo noch nicht gewünscht
    await tester.tap(find.text('E-Book'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('book-request-ol:1')), findsOneWidget);
  });
}
