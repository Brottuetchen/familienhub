import 'package:familienhub/models/shopping.dart';
import 'package:familienhub/models/today.dart';
import 'package:familienhub/services/home_widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);
  final now = DateTime(2026, 10, 14, 9, 30);

  test('today widget texts show events, tasks, meal and shopping', () {
    final d = TodayData.fromJson({
      'date': '2026-10-14',
      'events': [
        {'title': 'Zahnarzt', 'start': '2026-10-14T11:15:00', 'all_day': false},
        {'title': 'Elternabend', 'start': '2026-10-15T19:30:00', 'all_day': false},
        {'title': 'Feiertag', 'start': '2026-10-15', 'all_day': true},
      ],
      'tasks': {
        'status': 'ok',
        'items': [
          {'uid': 'a', 'title': 'Müll raus', 'done': false},
        ],
      },
      'meals': [
        {'source': 'hub', 'title': 'Spaghetti'},
      ],
      'shopping_open': 4,
      'reminders': [],
    });
    final t = todayTexts(d, now: now);
    expect(t['today_title'], 'Mittwoch, 14. Oktober');
    expect(t['events_items'], '11:15\tZahnarzt\nmorgen 19:30\tElternabend\n\tFeiertag');
    expect(t['tasks_items'], 'Müll raus');
    expect(t['events_label'], 'Termine');
    expect(t['tasks_label'], 'Aufgaben');
    expect(t['today_meal'], '🍽 Spaghetti');
    expect(t['today_updated'], 'Stand 09:30');
  });

  test('empty today shows friendly placeholders', () {
    final t = todayTexts(TodayData.fromJson({'date': '2026-10-14', 'tasks': {'status': 'ok', 'items': []}}), now: now);
    expect(t['events_items'], '');
    expect(t['events_empty'], 'Keine Termine');
    expect(t['tasks_items'], '');
    expect(t['tasks_empty'], 'Nichts fällig');
    expect(t['today_meal'], '');
  });

  test('shopping widget lists open items and caps at the row limit', () {
    final items = [
      for (var i = 1; i <= 25; i++) {'uid': 'u$i', 'summary': 'Artikel $i', 'status': i == 2 ? 'completed' : 'needs_action'},
    ];
    final d = ShoppingData.fromJson({
      'status': 'ok',
      'groups': [
        {'key': 'manual', 'items': items},
      ],
    });
    final t = shoppingTexts(d, now: now);
    expect(t['shopping_label'], 'Einkauf · 24');
    final rows = t['shopping_items']!.split('\n');
    expect(rows.length, widgetMaxRows);
    expect(rows.first, 'Artikel 1');
    expect(rows, isNot(contains('Artikel 2')));
    expect(t['shopping_empty'], 'Nichts auf der Liste');
  });

  test('empty shopping list has no rows and a plain label', () {
    final t = shoppingTexts(ShoppingData.fromJson({'status': 'ok', 'groups': []}), now: now);
    expect(t['shopping_items'], '');
    expect(t['shopping_label'], 'Einkauf');
  });

  test('multi-line titles are flattened to one row', () {
    final d = TodayData.fromJson({
      'date': '2026-10-14',
      'events': [
        {'title': 'Zwei\n  Zeilen', 'start': '2026-10-14T11:15:00', 'all_day': false},
      ],
      'tasks': {'status': 'ok', 'items': []},
    });
    expect(todayTexts(d, now: now)['events_items'], '11:15\tZwei Zeilen');
  });
}
