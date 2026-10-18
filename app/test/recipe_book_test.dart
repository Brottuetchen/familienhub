import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/screens/meals/recipes_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Recipe book in the hub: create, view, plan, ingredients to the shopping list.
void main() {
  setUp(setUpTestEnv);

  final curry = {'id': 5, 'title': 'Linsencurry', 'ingredients': ['200 g Linsen', 'Kokosmilch'], 'instructions': 'Köcheln.',
      'servings': 4, 'prep_minutes': 30, 'source_url': null};

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/recipes', [curry]);
    b.json('GET', '/api/recipes/5', curry);
    b.json('POST', '/api/recipes', {...curry, 'id': 6, 'title': 'Pesto'});
    b.json('POST', '/api/recipes/5/shopping', {'added': 2, 'ingredients': curry['ingredients']});
    b.json('POST', '/api/meals/plan', {'id': 1});
    return b;
  }

  testWidgets('create a recipe: title, ingredients per line, servings', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const RecipesScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Linsencurry'), findsOneWidget);
    expect(find.text('4 Portionen · 30 Min.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('recipe-new')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('recipe-title')), 'Pesto');
    await tester.enterText(find.byKey(const Key('recipe-ingredients')), 'Basilikum\n\n  Pinienkerne ');
    await tester.enterText(find.byKey(const Key('recipe-servings')), '3');
    await tester.tap(find.byKey(const Key('recipe-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/recipes').single);
    expect(body['title'], 'Pesto');
    expect(body['ingredients'], ['Basilikum', 'Pinienkerne']);
    expect(body['servings'], 3);
  });

  testWidgets('recipe details: ingredients to the list and plan on a day', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const RecipeDetailScreen(recipeId: 5)));
    await tester.pumpAndSettle();
    expect(find.text('•  200 g Linsen'), findsOneWidget);
    expect(find.text('Köcheln.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('recipe-shopping')));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/recipes/5/shopping'), hasLength(1));
    expect(find.text('2 Zutaten auf der Einkaufsliste'), findsOneWidget);

    await tester.tap(find.byKey(const Key('recipe-plan')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/meals/plan').single)['recipe_id'], 5);
  });

  testWidgets('add meal from the recipe book plans it for that day', (tester) async {
    final b = backend();
    b.json('GET', '/api/meals', {'status': 'ok', 'error': null, 'days': [
      for (var i = 0; i < 7; i++)
        {'date': DateTime.now().add(Duration(days: i)).toIso8601String().substring(0, 10), 'entries': []},
    ]});
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Essen eintragen').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('meal-from-book')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Linsencurry'));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/meals/plan').single)['recipe_id'], 5);
    expect(find.byType(RecipesScreen), findsNothing); // closed again
  });

  testWidgets('children see recipes but cannot change them', (tester) async {
    final b = backend();
    b.json('GET', '/api/auth/me', {'id': 3, 'username': 'kim', 'role': 'child', 'is_admin': false});
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const RecipeDetailScreen(recipeId: 5)));
    await tester.pumpAndSettle();
    expect(find.text('•  200 g Linsen'), findsOneWidget);
    expect(find.byKey(const Key('recipe-edit')), findsNothing);
    expect(find.byKey(const Key('recipe-shopping')), findsNothing);
  });
}
