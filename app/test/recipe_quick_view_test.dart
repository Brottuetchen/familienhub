import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/screens/meals/recipe_quick_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:familienhub/providers/providers.dart';

import 'helpers.dart';

/// #68: one quick view sheet for recipes from search results and from the week plan.
void main() {
  setUp(setUpTestEnv);

  String day(int add) => DateTime.now().add(Duration(days: add)).toIso8601String().substring(0, 10);

  const mealieDetails = {
    'status': 'ok', 'error': null, 'id': 'r1', 'source': 'mealie', 'title': 'Shakshuka', 'image': null, 'minutes': 30,
    'servings': 4, 'ingredients': ['4 Eier', '1 Dose Tomaten'], 'steps': ['Tomaten kochen', 'Eier einschlagen'],
    'url': 'https://mealie.test/g/home/r/shakshuka',
  };

  FakeBackend backend({List<Map<String, Object?>> today = const []}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true},
      'meal_planning': {'enabled': true, 'plugin': 'mealie'}}, 'plugins': []});
    b.json('GET', '/api/recipe-sources', [{'id': 'mealie', 'name': 'Mealie'}]);
    b.json('GET', '/api/recipe-sources/mealie/search', {'status': 'ok', 'error': null, 'total': 1,
      'items': [{'id': 'r1', 'name': 'Shakshuka', 'thumbnail': null, 'url': 'https://mealie.test/g/home/r/shakshuka'}]});
    b.json('GET', '/api/recipe-sources/mealie/recipes/r1', mealieDetails);
    b.json('POST', '/api/recipe-sources/mealie/plan', {'date': day(0), 'recipe_id': 'r1'});
    b.json('POST', '/api/recipe-sources/mealie/shopping', {'added': 1});
    b.json('DELETE', '/api/recipe-sources/mealie/plan/${day(0)}/r1', {'removed': true});
    b.json('GET', '/api/meals', {'status': 'ok', 'error': null, 'days': [
      for (var i = 0; i < 7; i++) {'date': day(i), 'entries': [if (i == 0) ...today]},
    ]});
    return b;
  }

  final mealieEntry = {'title': 'Shakshuka', 'source': 'mealie', 'recipe_id': 'r1', 'minutes': 30, 'url': 'https://mealie.test/r'};

  Future<void> pump(WidgetTester tester, FakeBackend b, {Size size = const Size(420, 1600), double scale = 1.0}) async {
    await setScreenSize(tester, size);
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        builder: (context, w) => MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
        home: const MealsScreen(),
      ),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> openSearchResult(WidgetTester tester) async {
    await tester.tap(find.byTooltip('Essen eintragen').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rezept aus Mealie'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'shak');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Shakshuka').last);
    await tester.pumpAndSettle();
  }

  testWidgets('search result opens the quick view with details and plans on the day', (tester) async {
    final b = backend();
    await pump(tester, b);
    await openSearchResult(tester);

    expect(b.sent('GET', '/api/recipe-sources/mealie/recipes/r1'), hasLength(1));
    expect(find.byKey(const Key('recipe-quick-view')), findsOneWidget);
    expect(find.text('30 Min.'), findsOneWidget);
    expect(find.text('4 Portionen'), findsOneWidget);
    expect(find.text('•  4 Eier'), findsOneWidget);
    expect(find.text('2. Eier einschlagen'), findsOneWidget);
    expect(find.text('In Mealie öffnen'), findsOneWidget);
    expect(b.sent('POST', '/api/recipe-sources/mealie/plan'), isEmpty, reason: 'tapping only opens the view');

    await tester.tap(find.byKey(const Key('recipe-shopping')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipe-sources/mealie/shopping').single), {'recipe_ids': ['r1']});
    expect(find.byKey(const Key('recipe-quick-view')), findsOneWidget); // still open

    await tester.tap(find.byKey(const Key('recipe-plan')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipe-sources/mealie/plan').single), {'date': day(0), 'recipe_id': 'r1'});
    expect(find.byKey(const Key('recipe-quick-view')), findsNothing);
    expect(find.text('Shakshuka'), findsNothing); // search screen closed, back on the week
  });

  testWidgets('plan entry opens the quick view; remove from plan', (tester) async {
    final b = backend(today: [mealieEntry]);
    await pump(tester, b);
    await tester.tap(find.text('Shakshuka'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-quick-view')), findsOneWidget);
    expect(find.text('•  1 Dose Tomaten'), findsOneWidget);
    expect(find.byKey(const Key('recipe-remove')), findsOneWidget);
    expect(find.text('Auf einen Tag legen'), findsOneWidget); // no fixed day when opened from the plan

    await tester.tap(find.byKey(const Key('recipe-remove')));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/recipe-sources/mealie/plan/${day(0)}/r1'), hasLength(1));
    expect(find.byKey(const Key('recipe-quick-view')), findsNothing);
  });

  testWidgets('Cookidoo entry: shopping uses the Cookidoo endpoint; the ⋯ menu stays', (tester) async {
    final b = backend(today: [
      {'title': 'Lasagne', 'source': 'cookidoo', 'cookidoo_id': 'r70', 'minutes': 70, 'url': 'https://cookidoo.test/r70'}]);
    b.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true},
      'meal_planning': {'enabled': true, 'plugin': 'cookidoo'}}, 'plugins': []});
    b.json('GET', '/api/recipe-sources/cookidoo/recipes/r70', {...mealieDetails, 'source': 'cookidoo', 'title': 'Lasagne', 'id': 'r70'});
    b.json('POST', '/api/cookidoo/shopping', {'added': 5});
    await pump(tester, b);
    expect(find.byTooltip('Rezept-Aktionen'), findsOneWidget);
    await tester.tap(find.text('Lasagne'));
    await tester.pumpAndSettle();
    expect(find.text('In Cookidoo öffnen'), findsOneWidget);
    await tester.tap(find.byKey(const Key('recipe-shopping')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/cookidoo/shopping').single), {'recipe_ids': ['r70']});
    expect(find.text('5 Zutaten auf der Cookidoo-Einkaufsliste'), findsOneWidget);
  });

  testWidgets('hub recipe in the plan: details from the hub, remove deletes the entry', (tester) async {
    final b = backend(today: [{'id': 9, 'title': 'Linsencurry', 'source': 'hub', 'recipe_id': 5}]);
    b.json('GET', '/api/recipe-sources/hub/recipes/5', {...mealieDetails, 'source': 'hub', 'title': 'Linsencurry', 'url': null,
      'ingredients': ['200 g Linsen'], 'steps': ['Köcheln.']});
    b.json('DELETE', '/api/meals/9', {'ok': true});
    await pump(tester, b);
    await tester.tap(find.text('Linsencurry'));
    await tester.pumpAndSettle();
    expect(find.text('•  200 g Linsen'), findsOneWidget);
    expect(find.byKey(const Key('recipe-open-source')), findsNothing);
    await tester.tap(find.byKey(const Key('recipe-remove')));
    await tester.pumpAndSettle();
    expect(b.requests.where((r) => r.method == 'DELETE').map((r) => r.url.path), ['/api/meals/9']);
  });

  testWidgets('details failing: error state with retry, actions stay usable', (tester) async {
    final b = backend(today: [mealieEntry]);
    var calls = 0;
    b.on('GET', '/api/recipe-sources/mealie/recipes/r1', (_) {
      calls++;
      return calls == 1
          ? jsonResponse({...mealieDetails, 'status': 'unavailable', 'error': 'Mealie nicht erreichbar', 'ingredients': [], 'steps': []})
          : jsonResponse(mealieDetails);
    });
    await pump(tester, b);
    await tester.tap(find.text('Shakshuka'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-quick-error')), findsOneWidget);
    expect(find.text('Mealie nicht erreichbar'), findsOneWidget);
    expect(find.byKey(const Key('recipe-remove')), findsOneWidget);
    await tester.tap(find.byKey(const Key('recipe-quick-retry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-quick-error')), findsNothing);
    expect(find.text('•  4 Eier'), findsOneWidget);
    expect(calls, 2);
  });

  testWidgets('HTTP error while loading shows the error state', (tester) async {
    final b = backend(today: [mealieEntry]);
    b.json('GET', '/api/recipe-sources/mealie/recipes/r1', {'detail': 'kaputt'}, status: 500);
    await pump(tester, b);
    await tester.tap(find.text('Shakshuka'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-quick-error')), findsOneWidget);
  });

  for (final scale in [1.0, 1.3, 2.0]) {
    testWidgets('quick view fits 360 dp at text scale $scale', (tester) async {
      final b = backend();
      b.json('GET', '/api/recipe-sources/mealie/recipes/r1', {...mealieDetails, 'title': 'Ein Rezept mit einem wirklich sehr langen Namen',
        'ingredients': [for (var i = 0; i < 12; i++) '${i + 1} sehr lange Zutatenbeschreibung mit vielen Wörtern']});
      await setScreenSize(tester, const Size(360, 740));
      await tester.pumpWidget(ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(b.api())],
        child: MaterialApp(
          locale: const Locale('de', 'DE'),
          builder: (context, w) => MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
          home: Builder(builder: (context) => Scaffold(body: Center(child: FilledButton(
            onPressed: () => showRecipeQuickView(context,
                const RecipeRef(source: 'mealie', id: 'r1', title: 'Shakshuka', url: 'https://mealie.test/r', minutes: 30),
                planDay: DateTime.now(), onRemove: () async {}),
            child: const Text('open'))))),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('recipe-quick-view')), findsOneWidget);
      expect(tester.takeException(), isNull);
      for (final k in ['recipe-plan', 'recipe-shopping', 'recipe-remove', 'recipe-open-source']) {
        final r = tester.getRect(find.byKey(Key(k)));
        expect(r.left, greaterThanOrEqualTo(0), reason: k);
        expect(r.right, lessThanOrEqualTo(360.01), reason: k);
      }
      final rects = [for (final k in ['recipe-plan', 'recipe-shopping', 'recipe-remove']) tester.getRect(find.byKey(Key(k)))];
      for (var i = 1; i < rects.length; i++) {
        expect(rects[i].top, greaterThanOrEqualTo(rects[i - 1].bottom));
      }
    });
  }
}
