import 'package:familienhub/models/meals.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

String _day(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Week views at large text sizes on a narrow phone: no overflow stripes.
void main() {
  setUp(setUpTestEnv);

  for (final scale in [1.0, 1.5, 2.0]) {
    testWidgets('meal week plan fits 360 dp at text scale $scale', (tester) async {
      await setScreenSize(tester, const Size(360, 780));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final monday = mondayOf(DateTime.now());
      final backend = FakeBackend();
      addDefaults(backend);
      backend.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true}}, 'plugins': []});
      backend.json('GET', '/api/meals', {
        'status': 'ok', 'error': null,
        'days': [
          for (var i = 0; i < 7; i++)
            {
              'date': _day(monday.add(Duration(days: i))),
              'entries': [
                if (i.isEven)
                  {'id': i + 1, 'title': 'Spaghetti mit Tomatensoße und Parmesan', 'source': 'hub', 'meal_type': 'dinner', 'minutes': 30},
                if (i == 3)
                  {'uid': 'c$i', 'title': 'Linsencurry mit Kokosmilch', 'source': 'cookidoo', 'recipe_id': 'r$i',
                   'minutes': 45, 'description': 'Thermomix TM6, vegetarisch'},
                if (i == 5)
                  {'uid': 'm$i', 'title': 'Kartoffelsuppe', 'source': 'mealie', 'minutes': 25},
              ],
            },
        ],
      });
      await tester.pumpWidget(appWith(backend.api(), const MealsScreen()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      // Scroll through the whole week: every day card is laid out once
      for (final title in ['Linsencurry mit Kokosmilch', 'Kartoffelsuppe']) {
        await tester.scrollUntilVisible(find.text(title), 200, scrollable: find.byType(Scrollable).last);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('calendar week view fits 360 dp at text scale $scale', (tester) async {
      await setScreenSize(tester, const Size(360, 780));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final now = DateTime.now();
      final b = FakeBackend();
      addDefaults(b);
      b.json('GET', '/api/calendar/events', [
        {'title': 'Elternabend in der Grundschule', 'start': '${_day(now)}T19:30:00', 'end': '${_day(now)}T21:00:00',
         'all_day': false, 'source': 'caldav', 'location': 'Aula'},
        {'title': 'Herbstferien', 'start': _day(now), 'end': _day(now.add(const Duration(days: 5))), 'all_day': true,
         'source': 'ics', 'calendar': 'Schulferien'},
      ]);
      await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Woche'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
