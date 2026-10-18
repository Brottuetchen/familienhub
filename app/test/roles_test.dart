import 'package:familienhub/models/account.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/screens/more/reminders_screen.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Rollen Kind und Gast (Entscheidung 18.10.): Was der Server ablehnt, zeigt die App gar nicht erst an.
void main() {
  setUp(setUpTestEnv);

  FakeBackend backendAs(String role) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', {'id': 3, 'username': 'kim', 'role': role, 'is_admin': role == 'admin'});
    b.json('GET', '/api/tasks', {
      'status': 'ok', 'error': null,
      'items': [{'uid': 't1', 'title': 'Zimmer aufräumen', 'done': false}],
    });
    b.json('GET', '/api/calendar/events', []);
    b.json('GET', '/api/reminders', []);
    final monday = DateTime(2026, 10, 19);
    b.json('GET', '/api/meals', {
      'status': 'ok', 'error': null,
      'days': [for (var i = 0; i < 7; i++) {'date': monday.add(Duration(days: i)).toIso8601String().substring(0, 10), 'entries': []}],
    });
    return b;
  }

  test('Rolle aus dem Server: Stufen wie im Backend, Altkonten ohne Rolle', () {
    expect(AppUser.fromJson({'id': 1, 'role': 'guest'}).roleLevel, 0);
    expect(AppUser.fromJson({'id': 1, 'role': 'child'}).roleLevel, 1);
    expect(AppUser.fromJson({'id': 1, 'role': 'partner'}).roleLevel, 2);
    expect(AppUser.fromJson({'id': 1, 'role': 'admin'}).isAdmin, isTrue);
    expect(AppUser.fromJson({'id': 1, 'is_admin': true}).roleLevel, 3);
    expect(AppUser.fromJson({'id': 1}).roleLevel, 2);
  });

  Future<void> pump(WidgetTester tester, FakeBackend b, Widget screen) async {
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), screen));
    await tester.pumpAndSettle();
  }

  Checkbox taskBox(WidgetTester tester) => tester.widget<Checkbox>(find.byType(Checkbox).first);

  testWidgets('Gast: Aufgaben nur ansehen, kein Anlegen, kein Abhaken', (tester) async {
    await pump(tester, backendAs('guest'), const TasksScreen());
    expect(find.text('Zimmer aufräumen'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsNothing);
    expect(taskBox(tester).onChanged, isNull);
  });

  testWidgets('Kind: Aufgaben abhaken, aber nicht anlegen', (tester) async {
    await pump(tester, backendAs('child'), const TasksScreen());
    expect(find.byType(FloatingActionButton), findsNothing);
    expect(taskBox(tester).onChanged, isNotNull);
  });

  testWidgets('Partner: Aufgaben anlegen und abhaken', (tester) async {
    await pump(tester, backendAs('partner'), const TasksScreen());
    expect(find.byType(FloatingActionButton), findsOneWidget);
    expect(taskBox(tester).onChanged, isNotNull);
  });

  for (final role in ['guest', 'child']) {
    testWidgets('$role: keine Termine anlegen, Essensplan nur lesen', (tester) async {
      final b = backendAs(role);
      await pump(tester, b, const CalendarScreen());
      expect(find.byType(FloatingActionButton), findsNothing);
      await pump(tester, b, const MealsScreen());
      expect(find.byTooltip('Essen eintragen'), findsNothing);
      expect(find.byTooltip('Zutaten der Woche auf die Einkaufsliste'), findsNothing);
    });
  }

  testWidgets('Partner: Termine und Essen eintragen', (tester) async {
    final b = backendAs('partner');
    await pump(tester, b, const CalendarScreen());
    expect(find.byType(FloatingActionButton), findsOneWidget);
    await pump(tester, b, const MealsScreen());
    expect(find.byTooltip('Essen eintragen'), findsWidgets);
  });

  testWidgets('Gast: Einkauf hinzufügen bleibt erlaubt', (tester) async {
    await pump(tester, backendAs('guest'), const ShoppingScreen());
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  for (final (role, family) in [('child', false), ('partner', true)]) {
    testWidgets('$role: Schalter „Für die ganze Familie“ ${family ? 'sichtbar' : 'ausgeblendet'}', (tester) async {
      await pump(tester, backendAs(role), const RemindersScreen());
      await tester.tap(find.byType(FloatingActionButton));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('reminder-family')), family ? findsOneWidget : findsNothing);
    });
  }
}
