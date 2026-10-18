import 'package:familienhub/models/calendar_event.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// Calendar month/week views and which days an event shows on.
void main() {
  setUp(setUpTestEnv);

  group('occursOn', () {
    CalendarEvent ev(String s, String? e, {bool allDay = false}) =>
        CalendarEvent.fromJson({'title': 'x', 'start': s, 'end': e, 'all_day': allDay});

    test('all-day end is exclusive (ICS)', () {
      final ferien = ev('2026-10-26', '2026-10-31', allDay: true);
      expect(ferien.occursOn(DateTime(2026, 10, 26)), isTrue);
      expect(ferien.occursOn(DateTime(2026, 10, 30)), isTrue);
      expect(ferien.occursOn(DateTime(2026, 10, 31)), isFalse);
      expect(ferien.isMultiDay, isTrue);
      final single = ev('2026-10-26', '2026-10-27', allDay: true);
      expect(single.occursOn(DateTime(2026, 10, 27)), isFalse);
      expect(single.isMultiDay, isFalse);
    });

    test('timed events count on every touched day, ending at midnight does not', () {
      final party = ev('2026-10-24T20:00:00', '2026-10-25T02:00:00');
      expect(party.occursOn(DateTime(2026, 10, 24)), isTrue);
      expect(party.occursOn(DateTime(2026, 10, 25)), isTrue);
      final evening = ev('2026-10-24T20:00:00', '2026-10-25T00:00:00');
      expect(evening.occursOn(DateTime(2026, 10, 25)), isFalse);
      expect(evening.isMultiDay, isFalse);
      expect(ev('2026-10-24T09:00:00', null).occursOn(DateTime(2026, 10, 24)), isTrue);
    });
  });

  String d(DateTime x) => '${x.year}-${x.month.toString().padLeft(2, '0')}-${x.day.toString().padLeft(2, '0')}';

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    final now = DateTime.now();
    final in2 = now.add(const Duration(days: 2));
    b.json('GET', '/api/calendar/events', [
      {'title': 'Zahnarzt', 'start': '${d(in2)}T10:00:00', 'end': '${d(in2)}T11:00:00', 'all_day': false, 'source': 'caldav'},
      {'title': 'Herbstferien', 'start': d(now), 'end': d(now.add(const Duration(days: 5))), 'all_day': true, 'source': 'ics',
       'calendar': 'Schulferien'},
    ]);
    return b;
  }

  testWidgets('month view: grid, tap a day shows its events, multi-day events on every day', (tester) async {
    SharedPreferences.setMockInitialValues({'calendar_view': 'month'});
    final b = backend();
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
    await tester.pumpAndSettle();
    final req = b.sent('GET', '/api/calendar/events').last.url.queryParameters;
    expect(req['days'], '42');
    expect(DateTime.parse(req['start']!).weekday, DateTime.monday);
    expect(find.text('Herbstferien'), findsOneWidget); // today is selected

    final in2 = DateTime.now().add(const Duration(days: 2));
    await tester.ensureVisible(find.byKey(ValueKey('cal-day-${in2.month}-${in2.day}')).first);
    await tester.tap(find.byKey(ValueKey('cal-day-${in2.month}-${in2.day}')).first);
    await tester.pumpAndSettle();
    expect(find.text('Zahnarzt'), findsOneWidget);
    expect(find.text('Herbstferien'), findsOneWidget); // still on holiday

    await tester.tap(find.byKey(const Key('calendar-next')));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/calendar/events').map((r) => r.url.queryParameters['start']).toSet().length, greaterThan(1));
  });

  testWidgets('week view lists seven days; the choice is remembered', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Woche'));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/calendar/events').last.url.queryParameters['days'], '7');
    expect(find.textContaining('KW '), findsOneWidget);
    expect((await SharedPreferences.getInstance()).getString('calendar_view'), 'week');
  });
}
