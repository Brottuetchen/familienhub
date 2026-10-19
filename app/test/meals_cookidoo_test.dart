import 'package:familienhub/models/meals.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

String _day(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

void main() {
  setUp(setUpTestEnv);

  FakeBackend backendWith({required bool planning}) {
    final monday = mondayOf(DateTime.now());
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/modules', {
      'modules': {
        'today': {'enabled': true}, 'meals': {'enabled': true},
        'meal_planning': {'enabled': planning, 'plugin': planning ? 'cookidoo' : null},
      },
      'plugins': [],
    });
    backend.json('GET', '/api/meals', {
      'status': 'ok',
      'error': null,
      'days': [
        for (var i = 0; i < 7; i++)
          {
            'date': _day(monday.add(Duration(days: i))),
            'entries': [
              if (i == 0)
                {'title': 'Kräuterfaltenbrot', 'source': 'cookidoo', 'cookidoo_id': 'r70717', 'minutes': 70,
                 'image': null, 'url': 'https://cookidoo.test/r70717'},
            ],
          },
      ],
    });
    return backend;
  }

  testWidgets('Rezept aus Cookidoo suchen und auf einen Tag legen', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = backendWith(planning: true);
    backend.json('GET', '/api/cookidoo/search', {
      'status': 'ok', 'error': null, 'total': 1,
      'items': [{'id': 'r364443', 'name': 'Lasagne', 'image': null, 'thumbnail': null, 'url': 'https://cookidoo.test/r364443'}],
    });
    backend.json('POST', '/api/cookidoo/plan', {'date': 'x', 'recipe_id': 'r364443'});

    await tester.pumpWidget(appWith(backend.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Kräuterfaltenbrot'), findsOneWidget);
    expect(find.text('70 Min.'), findsOneWidget);

    await tester.tap(find.byTooltip('Essen eintragen').at(2)); // Mittwoch
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rezept aus Cookidoo'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Lasagne');
    await tester.pump(const Duration(milliseconds: 900));
    await tester.pumpAndSettle();
    expect(backend.sent('GET', '/api/cookidoo/search').single.url.queryParameters['q'], 'Lasagne');

    await tester.tap(find.widgetWithText(ListTile, 'Lasagne'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('recipe-plan'))); // the quick view opens first (#68)
    await tester.pumpAndSettle();
    final body = bodyOf(backend.sent('POST', '/api/cookidoo/plan').single);
    expect(body, {'date': _day(mondayOf(DateTime.now()).add(const Duration(days: 2))), 'recipe_id': 'r364443'});
    expect(find.byType(MealsScreen), findsOneWidget); // Suche ist wieder zu
  });

  testWidgets('Cookidoo-Rezept aus dem Plan nehmen und Zutaten einkaufen', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = backendWith(planning: true);
    final monday = _day(mondayOf(DateTime.now()));
    backend.json('DELETE', '/api/cookidoo/plan/$monday/r70717', {'removed': true});
    backend.json('POST', '/api/cookidoo/shopping', {'added': 7});

    await tester.pumpWidget(appWith(backend.api(), const MealsScreen()));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Rezept-Aktionen'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Zutaten auf die Einkaufsliste'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/cookidoo/shopping').single), {'recipe_ids': ['r70717']});
    expect(find.text('7 Zutaten auf der Cookidoo-Einkaufsliste'), findsOneWidget);

    await tester.tap(find.byTooltip('Rezept-Aktionen'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aus dem Plan nehmen'));
    await tester.pumpAndSettle();
    expect(backend.sent('DELETE', '/api/cookidoo/plan/$monday/r70717'), hasLength(1));
  });

  testWidgets('ohne Cookidoo-Plugin bleibt alles wie bisher', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = backendWith(planning: false);
    await tester.pumpWidget(appWith(backend.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Rezept-Aktionen'), findsNothing);
    await tester.tap(find.byTooltip('Essen eintragen').first);
    await tester.pumpAndSettle();
    // Since the recipe book (18.10.): own dish or recipe book, but no Cookidoo option
    expect(find.text('Rezept aus Cookidoo'), findsNothing);
    expect(find.text('Rezept aus dem Rezeptbuch'), findsOneWidget);
    await tester.tap(find.text('Eigenes Gericht'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget); // the existing dialog
  });
}
