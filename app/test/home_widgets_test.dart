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
    expect(t['today_events'], '• 11:15 Zahnarzt\n• morgen 19:30 Elternabend\n• Feiertag');
    expect(t['today_tasks'], '☐ Müll raus');
    expect(t['today_meal'], '🍽 Spaghetti');
    expect(t['today_shopping'], '🛒 4 offen');
    expect(t['today_updated'], 'Stand 09:30');
  });

  test('empty today shows friendly placeholders', () {
    final t = todayTexts(TodayData.fromJson({'date': '2026-10-14', 'tasks': {'status': 'ok', 'items': []}}), now: now);
    expect(t['today_events'], 'Keine Termine');
    expect(t['today_tasks'], 'Nichts fällig');
    expect(t['today_meal'], '');
    expect(t['today_shopping'], '🛒 Liste leer');
  });

  test('shopping widget lists open items and caps at eight', () {
    final items = [
      for (var i = 1; i <= 10; i++) {'uid': 'u$i', 'summary': 'Artikel $i', 'status': i == 2 ? 'completed' : 'needs_action'},
    ];
    final d = ShoppingData.fromJson({
      'status': 'ok',
      'groups': [
        {'key': 'manual', 'items': items},
      ],
    });
    final t = shoppingTexts(d, now: now);
    expect(t['shopping_count'], 'Einkauf · 9');
    expect(t['shopping_items']!.split('\n').first, '• Artikel 1');
    expect(t['shopping_items'], isNot(contains('Artikel 2\n')));
    expect(t['shopping_items'], endsWith('… und 1 weitere'));
  });
}
