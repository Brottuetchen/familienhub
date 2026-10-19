import 'package:familienhub/screens/admin/sources_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Sources per area (administration and setup wizard).
void main() {
  setUp(setUpTestEnv);

  Map<String, dynamic> src(String id, String name, {bool selected = false, bool fallback = false, bool configured = true}) =>
      {'id': id, 'name': name, 'description': '', 'fallback': fallback, 'configured': configured, 'active': configured, 'selected': selected};

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/admin/sources', {'areas': [
      {'area': 'tasks', 'multiple': true, 'sources': [
        src('hub_tasks', 'Aufgaben im Hub', selected: true, fallback: true),
        src('nextcloud', 'CalDAV (Nextcloud, iCloud, Radicale …)', selected: true),
        src('habitica', 'Habitica', configured: false),
      ]},
      {'area': 'shopping', 'multiple': false, 'sources': [
        src('hub_shopping', 'Einkaufsliste im Hub', selected: true, fallback: true),
        src('homeassistant', 'Home Assistant'),
      ]},
      {'area': 'calendar', 'multiple': true, 'sources': [
        src('hub_calendar', 'Familienkalender im Hub', selected: true, fallback: true),
      ]},
    ]});
    b.json('PUT', '/api/admin/sources', {'areas': []});
    return b;
  }

  Future<void> pump(WidgetTester tester, FakeBackend b) async {
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const SourcesScreen()));
    await tester.pumpAndSettle();
  }

  testWidgets('shows the three areas, services not set up are disabled', (tester) async {
    await pump(tester, backend());
    expect(find.text('Woher kommen die Daten?'), findsOneWidget);
    expect(find.text('Aufgaben (mehrere möglich)'), findsOneWidget);
    expect(find.text('Einkaufsliste (eine Quelle)'), findsOneWidget);
    expect(find.text('Noch nicht eingerichtet'), findsOneWidget);
    expect(tester.widget<CheckboxListTile>(find.byKey(const Key('source-tasks-habitica'))).onChanged, isNull);
  });

  testWidgets('choosing Home Assistant for shopping saves exactly that source', (tester) async {
    final b = backend();
    await pump(tester, b);
    await tester.tap(find.byKey(const Key('source-shopping-homeassistant')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('PUT', '/api/admin/sources').single);
    expect(body, {'area': 'shopping', 'selected': ['homeassistant']});
  });

  testWidgets('task sources: deselecting one saves the rest, the last one stays', (tester) async {
    final b = backend();
    await pump(tester, b);
    await tester.tap(find.byKey(const Key('source-tasks-nextcloud')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/sources').single), {'area': 'tasks', 'selected': ['hub_tasks']});

    await tester.tap(find.byKey(const Key('source-calendar-hub_calendar')));
    await tester.pumpAndSettle();
    expect(b.sent('PUT', '/api/admin/sources'), hasLength(1)); // last calendar source cannot be removed
    expect(find.text('Mindestens eine Quelle muss bleiben'), findsOneWidget);
  });

  testWidgets('recipe ingredients: no option without the server field', (tester) async {
    await pump(tester, backend());
    expect(find.byKey(const Key('recipe-ingredients-merge')), findsNothing);
  });

  testWidgets('recipe ingredients: shows the mode and saves the other one', (tester) async {
    final b = backend();
    b.json('GET', '/api/admin/sources', {'areas': [
      {'area': 'shopping', 'multiple': false, 'recipe_ingredients': 'merge', 'sources': [
        src('homeassistant', 'Home Assistant', selected: true),
      ]},
    ]});
    b.json('PUT', '/api/admin/recipe-ingredients', {'areas': []});
    await pump(tester, b);
    expect(find.text('Rezeptzutaten'), findsOneWidget);
    expect(tester.widget<RadioGroup<String>>(find.ancestor(
        of: find.byKey(const Key('recipe-ingredients-merge')), matching: find.byType(RadioGroup<String>)).first).groupValue, 'merge');
    await tester.tap(find.byKey(const Key('recipe-ingredients-source')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/recipe-ingredients').single), {'mode': 'source'});
  });
}
