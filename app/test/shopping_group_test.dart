import 'package:familienhub/models/shopping.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// Shopping list grouped by recipe (#69) with merged entries (#70).
void main() {
  setUp(setUpTestEnv);

  Map<String, dynamic> item(String uid, String summary, [List<String> recipes = const []]) =>
      {'uid': uid, 'summary': summary, 'status': 'needs_action', 'recipes': recipes};

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/shopping', {
      'status': 'ok',
      'error': null,
      'groups': [
        {
          'key': 'manual',
          'entity': 'hub',
          'items': [
            item('1', '2 Zwiebeln + 200 g', ['Spaghetti Bolognese', 'Chili']),
            item('2', '400 g Hackfleisch', ['Spaghetti Bolognese']),
            item('3', 'Klebeband'),
          ],
        },
      ],
    });
    return b;
  }

  Future<void> pump(WidgetTester tester, FakeBackend b, {Size size = const Size(360, 800), double scale = 1}) async {
    await setScreenSize(tester, size);
    await tester.pumpWidget(MediaQuery(
      data: MediaQueryData(size: size, textScaler: TextScaler.linear(scale)),
      child: appWith(b.api(), const ShoppingScreen()),
    ));
    await tester.pumpAndSettle();
  }

  test('ShoppingItem reads the recipes, older servers send none', () {
    final i = ShoppingItem.fromJson({'uid': 'a', 'summary': 'Milch', 'recipes': ['Pfannkuchen']});
    expect(i.recipes, ['Pfannkuchen']);
    expect(ShoppingItem.fromJson({'uid': 'a', 'summary': 'Milch'}).recipes, isEmpty);
  });

  testWidgets('list view is the default and shows the merged hint', (tester) async {
    await pump(tester, backend());
    expect(find.byKey(const Key('recipe-group-none')), findsNothing);
    expect(find.text('1. 2 Zwiebeln + 200 g'), findsOneWidget);
    expect(find.text('aus 2 Rezepten'), findsOneWidget);
  });

  testWidgets('toggle groups by recipe, shows items of several recipes under each, and is remembered', (tester) async {
    await pump(tester, backend());
    await tester.tap(find.byKey(const Key('shopping-view-toggle')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-group-r:Spaghetti Bolognese')), findsOneWidget);
    expect(find.byKey(const Key('recipe-group-r:Chili')), findsOneWidget);
    expect(find.byKey(const Key('recipe-group-none')), findsOneWidget);
    expect(find.text('Ohne Rezept'), findsOneWidget);
    expect(find.text('2 Zwiebeln + 200 g'), findsNWidgets(2)); // under both recipes
    expect(find.text('400 g Hackfleisch'), findsOneWidget);
    expect(find.text('Klebeband'), findsOneWidget);
    expect((await SharedPreferences.getInstance()).getBool('shopping_group_by_recipe'), isTrue);

    // a new screen starts in the remembered view
    await pump(tester, backend());
    expect(find.byKey(const Key('recipe-group-none')), findsOneWidget);
  });

  testWidgets('checking an entry in the grouped view sends one request', (tester) async {
    final b = backend();
    b.json('PATCH', '/api/shopping/2', {'status': 'ok'});
    SharedPreferences.setMockInitialValues({'shopping_group_by_recipe': true});
    await pump(tester, b);
    await tester.tap(find.byKey(const Key('item-r:Spaghetti Bolognese-2')));
    await tester.pumpAndSettle();
    expect(b.sent('PATCH', '/api/shopping/2'), hasLength(1));
  });

  testWidgets('grouped view fits 360 dp with large text', (tester) async {
    SharedPreferences.setMockInitialValues({'shopping_group_by_recipe': true});
    await pump(tester, backend(), scale: 2);
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('recipe-group-r:Spaghetti Bolognese')), findsOneWidget);
  });
}
