import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Recipe sources (Mealie): offered when adding a meal, search and plan via /api/recipe-sources.
void main() {
  setUp(setUpTestEnv);

  String day(int add) => DateTime.now().add(Duration(days: add)).toIso8601String().substring(0, 10);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true},
      'meal_planning': {'enabled': true, 'plugin': 'mealie'}}, 'plugins': []});
    b.json('GET', '/api/recipe-sources', [{'id': 'mealie', 'name': 'Mealie'}]);
    b.json('GET', '/api/recipe-sources/mealie/search', {'status': 'ok', 'error': null, 'total': 1,
      'items': [{'id': 'r1', 'name': 'Shakshuka', 'thumbnail': null, 'url': 'https://mealie.test/g/home/r/shakshuka'}]});
    b.json('POST', '/api/recipe-sources/mealie/plan', {'date': day(0), 'recipe_id': 'r1'});
    b.json('DELETE', '/api/recipe-sources/mealie/plan/${day(0)}/r1', {'removed': true});
    b.json('GET', '/api/meals', {'status': 'ok', 'error': null, 'days': [
      for (var i = 0; i < 7; i++)
        {'date': day(i), 'entries': [
          if (i == 0) {'title': 'Shakshuka', 'source': 'mealie', 'recipe_id': 'r1', 'minutes': 30, 'url': 'https://mealie.test/r'},
        ]},
    ]});
    return b;
  }

  testWidgets('add meal offers Mealie and plans the chosen recipe', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Essen eintragen').first);
    await tester.pumpAndSettle();
    expect(find.text('Rezept aus Mealie'), findsOneWidget);
    expect(find.text('Rezept aus Cookidoo'), findsNothing);
    await tester.tap(find.text('Rezept aus Mealie'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'shak');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/recipe-sources/mealie/search').single.url.queryParameters['q'], 'shak');
    await tester.tap(find.text('Shakshuka').last);
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipe-sources/mealie/plan').single)['recipe_id'], 'r1');
  });

  testWidgets('Mealie entry in the week: open in Mealie, remove via the source', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Rezept-Aktionen'));
    await tester.pumpAndSettle();
    expect(find.text('In Mealie öffnen'), findsOneWidget);
    await tester.tap(find.text('Aus dem Plan nehmen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/recipe-sources/mealie/plan/${day(0)}/r1'), hasLength(1));
  });
}
