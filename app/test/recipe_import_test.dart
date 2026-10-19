import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/meals/recipe_import_screen.dart';
import 'package:familienhub/screens/meals/recipes_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Import a recipe from a link: preview, edit, save; pages without a recipe save nothing.
void main() {
  setUp(setUpTestEnv);

  const link = 'https://kochen.example.test/rezept/1';
  final draft = {
    'title': 'Spaghetti Bolognese',
    'description': 'Klassiker',
    'ingredients': ['500 g Spaghetti', '400 g Hack'],
    'instructions': 'Sauce:\nHack anbraten.',
    'servings': 4,
    'prep_minutes': 105,
    'tags': 'Pasta',
    'source_url': link,
    'image_url': 'https://img.example.test/bolo.jpg',
  };

  FakeBackend backend(Map<String, dynamic> preview) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/recipes', []);
    b.json('POST', '/api/recipes/import/preview', preview);
    b.json('POST', '/api/recipes', {...draft, 'id': 9});
    return b;
  }

  testWidgets('preview opens in the editor, edits are saved with picture and source link', (tester) async {
    final b = backend({'status': 'ok', 'recipe': draft});
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const RecipesScreen()));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('recipe-import')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('import-link')), link);
    await tester.tap(find.byKey(const Key('import-read')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipes/import/preview').single)['url'], link);
    expect(b.sent('POST', '/api/recipes'), isEmpty, reason: 'nothing is saved before the person confirms');
    expect(find.byKey(const Key('recipe-hint')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('recipe-title')), 'Bolognese');
    await tester.tap(find.byKey(const Key('recipe-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/recipes').single);
    expect(body['title'], 'Bolognese');
    expect(body['ingredients'], ['500 g Spaghetti', '400 g Hack']);
    expect(body['image_url'], 'https://img.example.test/bolo.jpg');
    expect(body['source_url'], link);
    expect(body['servings'], 4);
    expect(find.byKey(const Key('import-link')), findsNothing, reason: 'back in the recipe book');
  });

  for (final c in {
    'no_recipe': 'Auf dieser Seite wurden keine Rezeptdaten gefunden. Es wurde nichts gespeichert.',
    'blocked': 'Diese Adresse darf der Hub nicht abrufen.',
    'unreachable': 'Die Seite konnte nicht geladen werden.',
  }.entries) {
    testWidgets('status ${c.key} shows a clear message and saves nothing', (tester) async {
      final b = backend({'status': c.key, 'recipe': null});
      await setScreenSize(tester, const Size(420, 1400));
      await tester.pumpWidget(appWith(b.api(), const RecipeImportScreen()));
      await tester.enterText(find.byKey(const Key('import-link')), link);
      await tester.tap(find.byKey(const Key('import-read')));
      await tester.pumpAndSettle();
      expect(find.text(c.value), findsOneWidget);
      expect(b.sent('POST', '/api/recipes'), isEmpty);
    });
  }

  testWidgets('a shared link is read right away', (tester) async {
    final b = backend({'status': 'ok', 'recipe': draft});
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const RecipeImportScreen(initialUrl: link)));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/recipes/import/preview'), hasLength(1));
    expect(find.byKey(const Key('recipe-hint')), findsOneWidget);
  });

  test('extractSharedUrl finds the link in shared text', () {
    expect(extractSharedUrl([null, 'Tolles Rezept $link bitte ansehen']), link);
    expect(extractSharedUrl(['', 'kein Link']), isNull);
    expect(extractSharedUrl([link, 'https://other.example.test']), link);
  });

  testWidgets('no overflow at text scale 2.0 on 360 dp', (tester) async {
    final b = backend({'status': 'no_recipe', 'recipe': null});
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await setScreenSize(tester, const Size(360, 700));
    await tester.pumpWidget(appWith(b.api(), const RecipeImportScreen()));
    await tester.enterText(find.byKey(const Key('import-link')), link);
    await tester.tap(find.byKey(const Key('import-read')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    final b2 = backend({'status': 'ok', 'recipe': draft});
    await tester.pumpWidget(appWith(b2.api(), const RecipeImportScreen()));
    await tester.enterText(find.byKey(const Key('import-link')), link);
    await tester.tap(find.byKey(const Key('import-read')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recipe-hint')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
