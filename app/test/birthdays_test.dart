import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/today_layout.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/more/birthdays_screen.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

Map<String, dynamic> _entry(int id, String name, {int days = 3, int? turns = 80, String kind = 'birthday', bool you = false, int? gifts = 0}) => {
      'id': id, 'name': name, 'kind': kind, 'month': 10, 'day': 22, 'year': turns == null ? null : 1946,
      'user_id': you ? 1 : null, 'remind_days_before': 7, 'is_you': you, 'gift_count': you ? null : gifts,
      'next_date': '2026-10-22', 'days_until': days, 'turns': turns,
    };

FakeBackend _backend(List<Map<String, dynamic>> list) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/birthdays', list);
  b.json('POST', '/api/birthdays', {'id': 9});
  b.json('GET', '/api/birthdays/1/gifts', [
    {'id': 5, 'birthday_id': 1, 'text': 'Buch', 'link': null, 'done': false, 'created_by': 2},
  ]);
  b.json('POST', '/api/birthdays/1/gifts', {'id': 6});
  return b;
}

Widget _app(FakeBackend b, {int role = 2, Widget child = const BirthdaysScreen()}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api()), roleLevelProvider.overrideWithValue(role)],
      child: MaterialApp(locale: const Locale('de', 'DE'), home: child),
    );

void main() {
  setUp(setUpTestEnv);

  testWidgets('list shows age, countdown and gift count; own entry has no gift ideas', (tester) async {
    final b = _backend([
      _entry(1, 'Oma', gifts: 2),
      _entry(2, 'Opa', turns: null, days: 1),
      _entry(3, 'Alex', you: true),
      _entry(4, 'Anna & Tom', kind: 'anniversary', turns: 10, days: 0),
    ]);
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(find.textContaining('Oma wird 80 in 3 Tagen'), findsOneWidget);
    expect(find.textContaining('2 Geschenkideen'), findsOneWidget);
    expect(find.textContaining('Opa hat morgen Geburtstag'), findsOneWidget);
    expect(find.textContaining('Anna & Tom: 10. Jahrestag heute'), findsOneWidget);

    await tester.tap(find.text('Alex'));
    await tester.pumpAndSettle();
    expect(find.text('Geschenkideen: Alex'), findsNothing);
    expect(b.sent('GET', '/api/birthdays/3/gifts'), isEmpty);
  });

  testWidgets('gift ideas: list and add', (tester) async {
    final b = _backend([_entry(1, 'Oma')]);
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Oma'));
    await tester.pumpAndSettle();
    expect(find.text('Buch'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('gift-text')), 'Schal');
    await tester.enterText(find.byKey(const Key('gift-link')), 'ftp://x');
    await tester.tap(find.byKey(const Key('gift-add')));
    await tester.pumpAndSettle();
    expect(find.text('Der Link muss mit http:// oder https:// beginnen.'), findsOneWidget);
    expect(b.sent('POST', '/api/birthdays/1/gifts'), isEmpty);
    await tester.enterText(find.byKey(const Key('gift-link')), 'https://example.org/s');
    await tester.tap(find.byKey(const Key('gift-add')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/birthdays/1/gifts').single), {'text': 'Schal', 'link': 'https://example.org/s'});
  });

  testWidgets('create an entry; invalid 29 February with a common year is refused', (tester) async {
    await setScreenSize(tester, const Size(500, 3000)); // tall: the day menu shows all 31 entries
    final b = _backend([]);
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(find.textContaining('Noch keine Einträge'), findsOneWidget);
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('birthday-name')), 'Lena');
    await tester.enterText(find.byKey(const Key('birthday-year')), '2001');
    await tester.tap(find.byKey(const Key('birthday-day')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('29').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('birthday-month')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Februar').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('birthday-save')));
    await tester.pumpAndSettle();
    expect(find.text('Dieses Datum gibt es nicht.'), findsOneWidget);
    expect(b.sent('POST', '/api/birthdays'), isEmpty);
    await tester.enterText(find.byKey(const Key('birthday-year')), '2000');
    await tester.tap(find.byKey(const Key('birthday-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/birthdays').single);
    expect(body['name'], 'Lena');
    expect([body['month'], body['day'], body['year']], [2, 29, 2000]);
    expect(body['remind_days_before'], 7);
  });

  testWidgets('children can read and collect ideas but not manage entries', (tester) async {
    final b = _backend([_entry(1, 'Oma')]);
    await tester.pumpWidget(_app(b, role: 1));
    await tester.pumpAndSettle();
    expect(find.byType(FloatingActionButton), findsNothing);
    expect(find.byKey(const Key('birthday-edit-1')), findsNothing);
    await tester.tap(find.text('Oma'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('gift-add')), findsOneWidget);
    expect(find.byKey(const Key('gift-delete-5')), findsNothing); // someone else's idea
  });

  testWidgets('Today card shows the countdown and is part of the layout', (tester) async {
    final b = _backend([]);
    b.json('GET', '/api/modules', {
      'modules': {for (final m in ['today', 'meals', 'tasks', 'calendar', 'shopping']) m: {'enabled': true}},
      'plugins': [],
    });
    b.json('GET', '/api/today', {
      'date': '2026-10-19', 'events': [], 'tasks': {'status': 'ok', 'error': null, 'items': []},
      'meals': [], 'shopping_open': 0, 'reminders': [],
      'birthdays': [_entry(1, 'Oma')],
    });
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(locale: const Locale('de', 'DE'), theme: AppTheme.dark, home: const TodayScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-birthdays')), findsOneWidget);
    expect(find.text('Oma wird 80 in 3 Tagen'), findsOneWidget);
    expect(TodayLayout.builtin.cards.map((c) => c.id), contains('birthdays'));
    expect(TodayLayout.fromJson({'cards': []}).cards.map((c) => c.id), contains('birthdays'));
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('screens fit 360 dp (text scale $scale)', (tester) async {
      await setScreenSize(tester, const Size(360, 740));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final b = _backend([_entry(1, 'Oma Elisabeth Charlotte von Hohenlohe-Langenburg', gifts: 3)]);
      await tester.pumpWidget(_app(b));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.tap(find.byKey(const Key('birthday-edit-1')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('birthday-save')), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('gift sheet fits 360 dp (text scale $scale)', (tester) async {
      await setScreenSize(tester, const Size(360, 740));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final b = _backend([_entry(1, 'Oma')]);
      await tester.pumpWidget(_app(b));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Oma'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('gift-add')), findsOneWidget);
    });
  }
}
