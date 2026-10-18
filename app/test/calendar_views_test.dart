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
    await tester.tap(find.byTooltip('Woche'));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/calendar/events').last.url.queryParameters['days'], '7');
    expect(find.textContaining('KW '), findsOneWidget);
    expect((await SharedPreferences.getInstance()).getString('calendar_view'), 'week');
  });

  testWidgets('calendar chips: colour per calendar, switching one off hides its events and is remembered', (tester) async {
    final b = backend();
    b.json('GET', '/api/calendar/calendars', [
      {'id': 'hub', 'name': 'Familie', 'source': 'hub', 'writable': true, 'family': true},
      {'id': 'ics:ferien', 'name': 'Schulferien', 'source': 'ics', 'color': '#81B29A'},
    ]);
    final now = DateTime.now();
    b.json('GET', '/api/calendar/events', [
      {'title': 'Kinderfest', 'start': '${d(now)}T15:00:00', 'end': '${d(now)}T16:00:00', 'calendar_id': 'hub'},
      {'title': 'Herbstferien', 'start': d(now), 'end': d(now.add(const Duration(days: 3))), 'all_day': true, 'calendar_id': 'ics:ferien'},
    ]);
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Herbstferien'), findsOneWidget);
    final avatar = tester.widget<FilterChip>(find.byKey(const Key('cal-filter-ics:ferien'))).avatar as CircleAvatar;
    expect(avatar.backgroundColor, const Color(0xFF81B29A));

    await tester.tap(find.byKey(const Key('cal-filter-ics:ferien')));
    await tester.pumpAndSettle();
    expect(find.text('Herbstferien'), findsNothing);
    expect(find.text('Kinderfest'), findsOneWidget);
    expect((await SharedPreferences.getInstance()).getStringList('calendar_hidden'), ['ics:ferien']);
  });

  group('calendar colours and filters (server data as the app really gets it)', () {
    // Persönlich has no colour of its own; the server used to stamp every such event with the same purple.
    FakeBackend colourBackend() {
      final b = FakeBackend();
      addDefaults(b);
      b.json('GET', '/api/calendar/calendars', [
        {'id': 'hub', 'name': 'Familie', 'source': 'hub', 'writable': true, 'family': true},
        {'id': 'caldav:priv', 'name': 'Persönlich', 'source': 'caldav', 'color': null},
        {'id': 'ics:ferien', 'name': 'Feiertage', 'source': 'ics', 'color': '#81B29A'},
      ]);
      final now = DateTime.now();
      b.json('GET', '/api/calendar/events', [
        {'title': 'Kinderfest', 'start': '${d(now)}T15:00:00', 'end': '${d(now)}T16:00:00', 'calendar_id': 'hub', 'calendar': 'Familie'},
        {'title': 'Arzt', 'start': '${d(now)}T09:00:00', 'end': '${d(now)}T10:00:00', 'calendar_id': 'caldav:priv',
         'calendar': 'Persönlich', 'color': '#4f46e5', 'source': 'caldav'},
        {'title': 'Feiertag', 'start': '${d(now)}T00:00:00', 'end': '${d(now)}T01:00:00', 'calendar_id': 'ics:ferien',
         'color': '#4f46e5', 'source': 'ics'},
      ]);
      return b;
    }

    Color chipColor(WidgetTester tester, String id) =>
        ((tester.widget<FilterChip>(find.byKey(Key('cal-filter-$id'))).avatar as CircleAvatar).backgroundColor)!;

    Iterable<Color> dotColours(WidgetTester tester) {
      final now = DateTime.now();
      final cell = find.byKey(ValueKey('cal-day-${now.month}-${now.day}')).first;
      return tester
          .widgetList<Container>(find.descendant(of: cell, matching: find.byType(Container)))
          .map((c) => c.decoration)
          .whereType<BoxDecoration>()
          .where((x) => x.shape == BoxShape.circle)
          .map((x) => x.color!);
    }

    testWidgets('month dots use the chip colour of their calendar, not the server colour', (tester) async {
      SharedPreferences.setMockInitialValues({'calendar_view': 'month'});
      await setScreenSize(tester, const Size(420, 1400));
      await tester.pumpWidget(appWith(colourBackend().api(), const CalendarScreen()));
      await tester.pumpAndSettle();
      final dots = dotColours(tester).toList();
      expect(dots, containsAll([chipColor(tester, 'hub'), chipColor(tester, 'caldav:priv'), chipColor(tester, 'ics:ferien')]));
      expect(dots, isNot(contains(const Color(0xFF4F46E5))));
      expect(dots.toSet().length, 3);
    });

    testWidgets('a chip hides its calendar in month grid, day list, week and list view; stays hidden after a restart', (tester) async {
      SharedPreferences.setMockInitialValues({'calendar_view': 'month'});
      await setScreenSize(tester, const Size(420, 1400));
      final b = colourBackend();
      await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsOneWidget);
      expect(dotColours(tester), hasLength(3));

      await tester.tap(find.byKey(const Key('cal-filter-caldav:priv')));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsNothing); // day list below the grid
      expect(find.text('Kinderfest'), findsOneWidget);
      expect(dotColours(tester), hasLength(2)); // grid dot gone
      expect((await SharedPreferences.getInstance()).getStringList('calendar_hidden'), ['caldav:priv']);

      await tester.tap(find.byTooltip('Woche'));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsNothing);
      expect(find.text('Kinderfest'), findsOneWidget);
      await tester.tap(find.byTooltip('Liste'));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsNothing);
      expect(find.text('Kinderfest'), findsOneWidget);

      // New screen instance reads the persisted choice.
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsNothing);
      await tester.tap(find.byKey(const Key('cal-filter-caldav:priv')));
      await tester.pumpAndSettle();
      expect(find.text('Arzt'), findsOneWidget);
    });
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('view switch sits in the app bar and fits 360 dp (text scale $scale)', (tester) async {
      await setScreenSize(tester, const Size(360, 740));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(appWith(backend().api(), const CalendarScreen()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final bar = tester.getRect(find.byType(AppBar));
      expect(bar.contains(tester.getCenter(find.byKey(const Key('calendar-view')))), isTrue);
      final switchRect = tester.getRect(find.byKey(const Key('calendar-view')));
      expect(switchRect.right, lessThanOrEqualTo(360));
      expect(switchRect.left, greaterThan(tester.getRect(find.text('Termine')).right - 1));
      expect(tester.getCenter(find.byKey(const Key('read-status'))).dy, closeTo(switchRect.center.dy, 1.5));
    });
  }
}
