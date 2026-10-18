import 'package:familienhub/models/meals.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// #67: switching the server (or the user) must not leave anything of the previous one behind.
String _day(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

const _a = 'https://hub-a.test';
const _b = 'https://hub-b.test';

/// Two servers behind one fake: A offers meal planning (Cookidoo), B does not; their meal plans differ.
FakeBackend _twoServers({bool bMealsFail = false}) {
  final monday = mondayOf(DateTime.now());
  final b = FakeBackend();
  addDefaults(b);
  bool isA(Uri u) => u.host == 'hub-a.test';
  b.on('GET', '/api/modules', (r) => jsonResponse({
        'modules': {
          'today': {'enabled': true}, 'meals': {'enabled': true},
          'meal_planning': {'enabled': isA(r.url), 'plugin': isA(r.url) ? 'cookidoo' : null},
        },
        'plugins': [],
      }));
  b.on('GET', '/api/meals', (r) {
    if (!isA(r.url) && bMealsFail) return jsonResponse({'detail': 'down'}, status: 500);
    return jsonResponse({
      'status': 'ok', 'error': null,
      'days': [
        for (var i = 0; i < 7; i++)
          {
            'date': _day(monday.add(Duration(days: i))),
            'entries': [
              if (i == 0)
                {'title': isA(r.url) ? 'Eintrag von A' : 'Eintrag von B', 'source': 'cookidoo', 'cookidoo_id': 'r1',
                 'minutes': 20, 'image': null, 'url': 'https://cookidoo.test/r1'},
            ],
          },
      ],
    });
  });
  b.json('POST', '/api/auth/login', {
    'access_token': 'token-2', 'refresh_token': 'refresh-2', 'user': meJson,
  });
  b.json('POST', '/api/shopping', {'status': 'ok'});
  b.json('GET', '/api/shopping', {'status': 'ok', 'error': null, 'groups': []});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  Future<ProviderContainer> pumpApp(WidgetTester tester, FakeBackend b, MemorySessionStore store) async {
    await setScreenSize(tester, const Size(420, 1600));
    final api = b.api(store: store);
    final container = ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        home: Consumer(builder: (context, ref, _) =>
            ref.watch(sessionProvider).phase == SessionPhase.loggedIn ? const MealsScreen() : const Scaffold()),
      ),
    ));
    await tester.pumpAndSettle();
    return container;
  }

  Future<void> switchTo(WidgetTester tester, ProviderContainer c, String url) async {
    await c.read(sessionProvider.notifier).setServer(url);
    await tester.pumpAndSettle();
    await c.read(sessionProvider.notifier).login('alex', 'pw');
    await tester.pumpAndSettle();
  }

  testWidgets('A to B to A: modules and meal plan follow the server', (tester) async {
    final b = _twoServers();
    final c = await pumpApp(tester, b, MemorySessionStore(url: _a, access: 'token-1', refresh: 'refresh-1'));
    expect(find.text('Eintrag von A'), findsOneWidget);
    expect(find.byTooltip('Rezept-Aktionen'), findsOneWidget); // planning on A: the menu

    await switchTo(tester, c, _b);
    expect(find.text('Eintrag von A'), findsNothing);
    expect(find.text('Eintrag von B'), findsOneWidget);
    expect(find.byTooltip('Rezept-Aktionen'), findsNothing); // no planning on B: lock chip
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);

    await switchTo(tester, c, _a);
    expect(find.text('Eintrag von B'), findsNothing);
    expect(find.text('Eintrag von A'), findsOneWidget);
    expect(find.byTooltip('Rezept-Aktionen'), findsOneWidget); // back on A: the menu again
    expect(find.byIcon(Icons.lock_outline), findsNothing);
  });

  testWidgets('cached lists of A are not shown for B', (tester) async {
    final b = _twoServers(bMealsFail: true);
    final c = await pumpApp(tester, b, MemorySessionStore(url: _a, access: 'token-1', refresh: 'refresh-1'));
    expect(find.text('Eintrag von A'), findsOneWidget);

    await switchTo(tester, c, _b);
    expect(find.text('Eintrag von A'), findsNothing); // neither from memory nor from the disk cache
    expect(find.text('Eintrag von B'), findsNothing);
  });

  testWidgets('local server-bound preferences are cleared with the server', (tester) async {
    SharedPreferences.setMockInitialValues({
      'shopping_recent': ['Milch'], 'calendar_hidden': ['cal-a'], 'calendar_last_target': 'cal-a', 'books_kind': 'ebook'});
    final b = _twoServers();
    final c = await pumpApp(tester, b, MemorySessionStore(url: _a, access: 'token-1', refresh: 'refresh-1'));
    await switchTo(tester, c, _b);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('shopping_recent'), isNull);
    expect(prefs.getStringList('calendar_hidden'), isNull);
    expect(prefs.getString('calendar_last_target'), isNull);
    expect(prefs.getString('books_kind'), 'ebook'); // a display preference, not server content
  });

  test('offline queue entries of A are never sent to B', () async {
    final b = _twoServers()..offline = true;
    final store = MemorySessionStore(url: _a, access: 'token-1', refresh: 'refresh-1');
    final api = b.api(store: store);
    expect(await api.addShoppingItem('Eier'), isFalse);
    expect(api.pending, hasLength(1));

    b.offline = false;
    await api.setServer(_b);
    await api.login('alex', 'pw');
    expect(await api.loadPending(), isEmpty);
    await api.flushPending();
    expect(b.sent('POST', '/api/shopping'), isEmpty);
    expect(b.requests.where((r) => r.url.host == 'hub-b.test' && r.method == 'POST' && r.url.path == '/api/shopping'), isEmpty);
  });
}
