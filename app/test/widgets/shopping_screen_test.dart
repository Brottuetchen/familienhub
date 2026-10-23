import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  Future<FakeBackend> pump(WidgetTester tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/shopping', {
      'status': 'ok',
      'error': null,
      'groups': [
        {
          'key': 'manual',
          'entity': 'todo.einkauf',
          'items': [
            {'uid': 'm1', 'summary': 'Milch', 'status': 'needs_action'},
          ],
        },
        {
          'key': 'recipes',
          'entity': 'todo.cookidoo',
          'items': [
            {'uid': 'r1', 'summary': 'Tomaten', 'status': 'needs_action'},
          ],
        },
      ],
    });
    backend.json('PATCH', '/api/shopping/r1', {'status': 'ok'});
    backend.json('DELETE', '/api/shopping/m1', {'status': 'ok'});
    await tester.pumpWidget(appWith(backend.api(), const ShoppingScreen()));
    await tester.pumpAndSettle();
    return backend;
  }

  testWidgets('groups manual and recipes', (tester) async {
    await pump(tester);
    final manualHeader = tester.getTopLeft(find.byKey(const Key('group-manual')));
    final recipeHeader = tester.getTopLeft(find.byKey(const Key('group-recipes')));
    final milch = tester.getTopLeft(find.text('1. Milch'));
    final tomaten = tester.getTopLeft(find.text('Tomaten'));

    expect(find.text('Allgemein'), findsOneWidget);
    expect(find.text('Aus Rezepten'), findsOneWidget);
    // Milch steht unter „Freie Artikel“, Tomaten unter „Aus Rezepten“
    expect(manualHeader.dy < milch.dy && milch.dy < recipeHeader.dy, isTrue);
    expect(recipeHeader.dy < tomaten.dy, isTrue);
  });

  testWidgets('recipe items cannot be deleted', (tester) async {
    final backend = await pump(tester);

    await tester.drag(find.text('Tomaten'), const Offset(-500, 0));
    await tester.pumpAndSettle();
    expect(find.text('Tomaten'), findsOneWidget);
    expect(backend.sent('DELETE', '/api/shopping/r1'), isEmpty);

    // Freie Artikel lassen sich wegwischen
    await tester.drag(find.text('1. Milch'), const Offset(-500, 0));
    await tester.pumpAndSettle();
    expect(backend.sent('DELETE', '/api/shopping/m1'), hasLength(1));
    expect(find.text('1. Milch'), findsNothing);
  });

  testWidgets('checking a recipe item marks it done', (tester) async {
    final backend = await pump(tester);
    await tester.tap(find.text('Tomaten'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('PATCH', '/api/shopping/r1').single), {'done': true});
  });

  testWidgets('add sheet suggests recently bought items from server', (tester) async {
    final backend = await pump(tester);
    backend.json('GET', '/api/shopping/recent', ['Hafermilch', 'Brot']);
    backend.json('POST', '/api/shopping', {'status': 'ok'});

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(ActionChip, 'Hafermilch'), findsOneWidget);

    await tester.tap(find.widgetWithText(ActionChip, 'Hafermilch'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/shopping').single), {'item': 'Hafermilch'});
  });
}
