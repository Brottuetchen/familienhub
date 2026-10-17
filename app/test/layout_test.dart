import 'package:familienhub/screens/main_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  Future<void> pumpShell(WidgetTester tester, double width) async {
    await setScreenSize(tester, Size(width, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    await tester.pumpWidget(appWith(backend.api(), const MainShell(startPush: false)));
    await tester.pumpAndSettle();
  }

  testWidgets('uses navigation rail at 700dp', (tester) async {
    await pumpShell(tester, 700);
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    final rail = tester.widget<NavigationRail>(find.byType(NavigationRail));
    expect(rail.destinations, hasLength(6));
  });

  testWidgets('uses bottom bar at 400dp', (tester) async {
    await pumpShell(tester, 400);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
    for (final label in ['Heute', 'Termine', 'Aufgaben', 'Einkauf', 'Essen', 'Mehr']) {
      expect(find.descendant(of: find.byType(NavigationBar), matching: find.text(label)), findsOneWidget);
    }
  });

  testWidgets('tapping a destination switches the screen', (tester) async {
    await pumpShell(tester, 400);
    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Einkauf')));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(AppBar, 'Einkauf'), findsOneWidget);
  });

  testWidgets('hides areas the server does not offer', (tester) async {
    await setScreenSize(tester, const Size(400, 900));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/modules', {
      'modules': {
        'today': {'enabled': true}, 'meals': {'enabled': true}, 'reminders': {'enabled': true},
        'tasks': {'enabled': true, 'plugin': 'nextcloud'}, 'calendar': {'enabled': true, 'plugin': 'nextcloud'},
        'shopping': {'enabled': false}, 'books': {'enabled': false},
      },
      'plugins': [],
    });
    await tester.pumpWidget(appWith(backend.api(), const MainShell(startPush: false)));
    await tester.pumpAndSettle();
    final bar = find.byType(NavigationBar);
    expect(find.descendant(of: bar, matching: find.text('Einkauf')), findsNothing);
    expect(find.descendant(of: bar, matching: find.text('Aufgaben')), findsOneWidget);
    expect(tester.widget<NavigationBar>(bar).destinations, hasLength(5));
    expect(find.byKey(const Key('today-shopping')), findsNothing);
  });
}
