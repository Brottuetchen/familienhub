import 'package:familienhub/models/meals.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

String _day(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

void main() {
  setUp(setUpTestEnv);

  testWidgets('week button sends the shown week and shows one summary line per source', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final monday = mondayOf(DateTime.now());
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true}}, 'plugins': []});
    backend.json('GET', '/api/meals', {
      'status': 'ok', 'error': null,
      'days': [for (var i = 0; i < 7; i++) {'date': _day(monday.add(Duration(days: i))), 'entries': []}],
    });
    backend.json('POST', '/api/meals/shopping-list', {
      'ingredients': ['Mais'], 'added': 7, 'message': 'Einkaufsliste teilweise aktualisiert.',
      'sources': [
        {'source': 'hub', 'label': 'Hub', 'recipes': 1, 'added': 3, 'status': 'ok', 'message': 'Hub: 1 Zutaten, 3 zur Einkaufsliste hinzugefügt.'},
        {'source': 'cookidoo', 'label': 'Cookidoo', 'recipes': 2, 'added': 4, 'status': 'ok', 'message': 'Cookidoo: 2 Rezepte auf die Einkaufsliste übernommen.'},
        {'source': 'mealie', 'label': 'Mealie', 'recipes': 0, 'added': 0, 'status': 'unavailable', 'message': 'Mealie: nicht erreichbar, übersprungen.'},
      ],
    });

    await tester.pumpWidget(appWith(backend.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Zutaten der Woche auf die Einkaufsliste'));
    await tester.pumpAndSettle();

    final sent = backend.sent('POST', '/api/meals/shopping-list').single;
    expect(sent.url.queryParameters, {'start': _day(monday), 'end': _day(monday.add(const Duration(days: 6)))});
    expect(find.textContaining('Cookidoo: 2 Rezepte auf die Einkaufsliste übernommen.'), findsOneWidget);
    expect(find.textContaining('Mealie: nicht erreichbar, übersprungen.'), findsOneWidget);
    expect(find.textContaining('Hub: 1 Zutaten'), findsOneWidget);
  });
}
