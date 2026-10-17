import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  final today = DateTime.now();
  String day(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Map<String, dynamic> todayJson() => {
        'date': day(today),
        'events': [
          {'title': 'Elternabend', 'start': '${day(today)}T19:30:00', 'end': null, 'all_day': false, 'calendar': 'Familie'},
        ],
        'tasks': {
          'status': 'ok',
          'error': null,
          'items': [
            {'uid': 't1', 'title': 'Steuer machen', 'due': day(today.subtract(const Duration(days: 2))), 'done': false},
          ],
        },
        'meals': [
          {'source': 'cookidoo', 'title': 'Linsencurry'},
        ],
        'shopping_open': 3,
        'reminders': [
          {'id': 1, 'title': 'Müll rausstellen', 'due': '${day(today)}T18:00:00'},
        ],
        'weather': null,
      };

  testWidgets('renders sections from today json', (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', todayJson());
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Elternabend'), findsOneWidget);
    expect(find.text('19:30'), findsOneWidget);
    expect(find.text('Steuer machen'), findsOneWidget);
    expect(find.text('überfällig'), findsOneWidget);
    expect(find.text('Linsencurry'), findsOneWidget);
    expect(find.text('Cookidoo'), findsOneWidget);
    expect(find.text('3 Artikel offen'), findsOneWidget);
    expect(find.text('Müll rausstellen'), findsOneWidget);
    expect(find.textContaining('Offline'), findsNothing);
  });

  testWidgets('shows offline banner from cache', (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', todayJson());
    final api = backend.api();
    await api.today(); // füllt den Cache
    backend.offline = true;

    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();

    expect(tester.widget<Tooltip>(find.byKey(const Key('read-status'))).message, startsWith('Offline, Stand '));
    expect(find.text('Elternabend'), findsOneWidget);
  });

  testWidgets('shows hint when tasks source is unavailable', (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', {
      ...todayJson(),
      'tasks': {'status': 'unavailable', 'error': 'CalDAV down', 'items': []},
    });
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Aufgaben gerade nicht verfügbar'), findsOneWidget);
    expect(find.text('Elternabend'), findsOneWidget);
  });
}
