import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/today/house_controls.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

String _d(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

FakeBackend _backend() {
  final now = DateTime.now();
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/auth/people', [
    {'id': 1, 'username': 'alex', 'display_name': 'Alex'},
    {'id': 2, 'username': 'sam', 'display_name': 'Sam'},
  ]);
  b.json('GET', '/api/modules', {
    'modules': {for (final m in ['today', 'meals', 'tasks', 'calendar', 'shopping']) m: {'enabled': true}},
    'plugins': [],
  });
  b.json('GET', '/api/today', {
    'date': _d(now),
    'events': [
      {'title': 'Kita-Fest', 'start': '${_d(now)}T15:00:00'},
    ],
    'tasks': {
      'status': 'ok', 'error': null,
      'items': [
        {'uid': 't1', 'title': 'Müll rausbringen', 'done': false},
        {'uid': 't2', 'title': 'Wasserkasten holen', 'done': false, 'assignee': 2},
      ],
    },
    'meals': [],
    'shopping_open': 2,
    'reminders': [],
    'notifications_unread': 3,
  });
  b.json('GET', '/api/shopping', {
    'status': 'ok', 'error': null,
    'groups': [
      {'key': 'manual', 'items': [
        {'uid': 's1', 'summary': 'Milch', 'status': 'needs_action'},
        {'uid': 's2', 'summary': 'Brot', 'status': 'needs_action'},
      ]},
    ],
  });
  b.json('GET', '/api/tasks', {
    'status': 'ok', 'error': null,
    'items': [
      {'uid': 'f1', 'title': 'Fenster putzen', 'done': false, 'list': {'name': 'Familie', 'kind': 'family'}},
      {'uid': 'f2', 'title': 'Schon erledigt', 'done': true},
    ],
  });
  b.json('POST', '/api/tasks/t1/complete', {'uid': 't1', 'done': true});
  b.json('PATCH', '/api/shopping/s1', {'uid': 's1'});
  b.json('POST', '/api/shopping', {'uid': 's3'});
  return b;
}

Widget _app(FakeBackend b, {ThemeSpec? spec}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        theme: spec == null ? AppTheme.dark : AppTheme.fromSpec(spec),
        home: const TodayScreen(),
      ),
    );

void main() {
  setUp(setUpTestEnv);

  testWidgets('Kopf: Gruß, Glocke mit Zähler, Avatare', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(_app(_backend()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-greeting')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('today-bell')), matching: find.text('3')), findsOneWidget);
    expect(find.byTooltip('Alex'), findsWidgets);
    expect(find.byTooltip('Sam'), findsWidgets); // auch an der zugewiesenen Aufgabe
  });

  testWidgets('Kopf: Wolke, Glocke und Avatare liegen auf einer Mittellinie', (tester) async {
    await setScreenSize(tester, const Size(360, 1800));
    await tester.pumpWidget(_app(_backend()));
    await tester.pumpAndSettle();
    final cloud = tester.getCenter(find.byKey(const Key('read-status'))).dy;
    final bell = tester.getCenter(find.byKey(const Key('today-bell'))).dy;
    final avatar = tester.getCenter(find.byTooltip('Alex').first).dy;
    expect(cloud, closeTo(bell, 0.5));
    expect(avatar, closeTo(bell, 0.5));
  });

  testWidgets('Aufgabe direkt auf Heute abhaken', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    final row = find.ancestor(of: find.text('Müll rausbringen'), matching: find.byType(Row)).first;
    await tester.tap(find.descendant(of: row, matching: find.byType(Checkbox)));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/tasks/t1/complete'), hasLength(1));
  });

  testWidgets('Abhaken lädt im Hintergrund: kein Lade-Bildschirm, Haus-Karte bleibt stehen', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['turn_on', 'turn_off']},
    ]});
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    final house = tester.state(find.byType(HouseCard));
    final todayReads = b.sent('GET', '/api/today').length;
    final row = find.ancestor(of: find.text('Müll rausbringen'), matching: find.byType(Row)).first;
    await tester.tap(find.descendant(of: row, matching: find.byType(Checkbox)));
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.byType(HubLoader), findsNothing, reason: 'kein Lade-Bildschirm nach dem Abhaken');
      expect(find.byKey(const Key('light.lamp-turn_off')), findsOneWidget, reason: 'Haus-Kacheln bleiben stehen');
    }
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/tasks/t1/complete'), hasLength(1));
    expect(b.sent('GET', '/api/today').length, greaterThan(todayReads), reason: 'Heute wurde nachgeladen');
    expect(tester.state(find.byType(HouseCard)), same(house), reason: 'nichts wurde neu aufgebaut');
    expect(find.text('Müll rausbringen'), findsOneWidget);
  });

  testWidgets('Filter „Familie“ zeigt die offenen Familienaufgaben', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('today-filter-family'))); // Leiste scrollt waagerecht
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-filter-family')));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/tasks').last.url.queryParameters['view'], 'family');
    expect(find.text('Fenster putzen'), findsOneWidget);
    expect(find.text('Schon erledigt'), findsNothing);
    expect(find.text('Müll rausbringen'), findsNothing);
  });

  testWidgets('Einkauf: abhaken und hinzufügen', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(find.text('2 Artikel offen'), findsOneWidget);
    final row = find.byKey(const ValueKey('shop-s1'));
    await tester.tap(find.descendant(of: row, matching: find.byType(Checkbox)));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/shopping/s1').single), {'done': true});

    await tester.enterText(find.byKey(const Key('today-shopping-add')), 'Eier');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/shopping').single), {'item': 'Eier'});
  });

  testWidgets('Kachel-Layout: Einkauf und Termine nebeneinander', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    const spec = ThemeSpec(id: 'builtin:clean-cards', name: 'Clean Cards', colors: {
      'primary': '#2563EB', 'secondary': '#10B981', 'background': '#EEF2F8', 'surface': '#FFFFFF',
      'surfaceHigh': '#F1F5F9', 'border': '#E2E8F0',
    }, style: {'layout': 'bento', 'card': {'radius': 24, 'border': 0, 'shadow': 'soft'}});
    await tester.pumpWidget(_app(_backend(), spec: spec));
    await tester.pumpAndSettle();
    final shop = tester.getTopLeft(find.byKey(const Key('today-shopping')));
    final events = tester.getTopLeft(find.byKey(const Key('today-events')));
    expect(shop.dy, events.dy); // gleiche Zeile
    expect(events.dx, greaterThan(shop.dx));
    expect(find.text('Termin'), findsOneWidget); // kompakte Kachel „1 Termin“
  });

  testWidgets('Erledigte Aufgaben verschwinden, offene haben einen leeren Kreis', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    final now = DateTime.now();
    b.json('GET', '/api/today', {
      'date': _d(now), 'events': [], 'meals': [], 'shopping_open': 0, 'reminders': [],
      'tasks': {'status': 'ok', 'error': null, 'items': [
        {'uid': 'h1', 'title': '2 Liter Wasser', 'provider': 'habitica', 'account': 'own', 'actions': ['up'],
         'native': {'type': 'daily'}, 'done': false},
        {'uid': 'h2', 'title': 'Schon erledigt', 'provider': 'habitica', 'account': 'own', 'actions': ['down'],
         'native': {'type': 'daily'}, 'done': true},
        {'uid': 'n1', 'title': 'Nextcloud erledigt', 'done': true},
      ]},
    });
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(find.text('2 Liter Wasser'), findsOneWidget);
    expect(find.text('Schon erledigt'), findsNothing);
    expect(find.text('Nextcloud erledigt'), findsNothing);
    final box = tester.widget<Checkbox>(find.descendant(
        of: find.ancestor(of: find.text('2 Liter Wasser'), matching: find.byType(Row)).first,
        matching: find.byType(Checkbox)));
    expect(box.value, isFalse);
    expect(box.shape, const CircleBorder());
    expect(find.byIcon(Icons.undo), findsNothing);
  });
}