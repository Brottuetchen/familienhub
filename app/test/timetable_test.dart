import 'package:familienhub/models/timetable.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/timetable/timetable_screen.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

Map<String, dynamic> _entry(int id, int weekday, String title, String start, String end,
        {String kind = 'school', String week = 'all', String? location}) =>
    {
      'id': id, 'child_id': 7, 'weekday': weekday, 'week': week, 'start': start, 'end': end,
      'title': title, 'kind': kind, 'location': location,
    };

FakeBackend _backend({bool canEdit = true, bool ab = true}) {
  final b = FakeBackend();
  addDefaults(b);
  final today = DateTime.now();
  final iso = '${today.year}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}';
  b.json('GET', '/api/timetable/children', [
    {'id': 7, 'name': 'Mia'},
    if (canEdit) {'id': 8, 'name': 'Ben'},
  ]);
  b.json('GET', '/api/timetable', {
    'child': {'id': 7, 'name': 'Mia'},
    'entries': [
      _entry(1, 0, 'Mathematik mit sehr langem Titel für den Überlauftest', '08:00', '08:45', location: 'Raum 204 im Nebengebäude'),
      _entry(2, 0, 'Schwimmen', '16:00', '17:00', kind: 'sport', week: 'a'),
      _entry(3, 0, 'Querflöte', '17:00', '17:30', kind: 'music', week: 'b'),
      _entry(4, 5, 'Fußball', '10:00', '11:30', kind: 'club'),
    ],
    'settings': {
      'ab_reference': ab ? iso : null,
      'holiday_feed': 'ics:schule',
      'feeds': [{'id': 'ics:schule', 'name': 'Schule'}],
    },
    'current_week': ab ? 'a' : null,
    'holidays': [
      {'start': iso, 'end': iso, 'title': 'Herbstferien'},
    ],
    'can_edit': canEdit,
  });
  b.json('POST', '/api/timetable', {'id': 99});
  b.json('PATCH', '/api/timetable/1', {'id': 1});
  b.json('DELETE', '/api/timetable/1', {});
  b.json('POST', '/api/timetable/copy-day', {'copied': 3});
  b.json('POST', '/api/timetable/copy-week', {'copied': 4});
  b.json('PUT', '/api/timetable/settings', {});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  test('summary merges lessons into one "until" part', () {
    final child = TodayTimetableChild.fromJson({
      'child_id': 7, 'name': 'Mia', 'holiday': null,
      'entries': [
        _entry(1, 0, 'Mathe', '08:00', '09:00'),
        _entry(2, 0, 'Deutsch', '09:00', '13:15'),
        _entry(3, 0, 'Schwimmen', '16:00', '17:00', kind: 'sport'),
      ],
    });
    expect(child.summary, 'Schule bis 13:15, Schwimmen 16:00');
    final holiday = TodayTimetableChild.fromJson({
      'child_id': 7, 'name': 'Mia', 'holiday': 'Herbstferien',
      'entries': [_entry(3, 0, 'Schwimmen', '16:00', '17:00', kind: 'sport')],
    });
    expect(holiday.summary, 'Schulferien, Schwimmen 16:00');
  });

  testWidgets('Today shows the timetable card with every child of the parent', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    b.json('GET', '/api/today', {
      'date': '2026-10-19',
      'events': [],
      'tasks': {'status': 'ok', 'error': null, 'items': []},
      'meals': [],
      'shopping_open': 0,
      'reminders': [],
      'timetable': {
        'status': 'ok',
        'children': [
          {'child_id': 7, 'name': 'Mia', 'holiday': null, 'entries': [
            _entry(1, 0, 'Mathe', '08:00', '13:15'),
            _entry(2, 0, 'Schwimmen', '16:00', '17:00', kind: 'sport'),
          ]},
          {'child_id': 8, 'name': 'Ben', 'holiday': null, 'entries': [_entry(3, 0, 'Fußball', '15:00', '16:00', kind: 'club')]},
        ],
      },
    });
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-timetable')), findsOneWidget);
    expect(find.textContaining('Mia: Schule bis 13:15, Schwimmen 16:00', findRichText: true), findsOneWidget);
    expect(find.textContaining('Ben: Fußball 15:00', findRichText: true), findsOneWidget);
  });

  testWidgets('Today has no timetable card without entries', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-timetable')), findsNothing);
  });

  testWidgets('parents add an entry and copy a day', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-holiday')), findsOneWidget);
    // Week A is shown: Mathe + Schwimmen, but not the B-week flute
    expect(find.text('Schwimmen'), findsOneWidget);
    expect(find.text('Querflöte'), findsNothing);
    await tester.tap(find.byKey(const Key('timetable-week-b')));
    await tester.pumpAndSettle();
    expect(find.text('Querflöte'), findsOneWidget);
    expect(find.text('Schwimmen'), findsNothing);

    await tester.tap(find.byKey(const Key('timetable-add-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('timetable-title')), 'Englisch');
    await tester.tap(find.byKey(const Key('timetable-save')));
    await tester.pumpAndSettle();
    final posted = bodyOf(b.sent('POST', '/api/timetable').single);
    expect(posted, containsPair('title', 'Englisch'));
    expect(posted, containsPair('weekday', 1));
    expect(posted, containsPair('week', 'b'));
    expect(posted, containsPair('child_id', 7));

    await tester.tap(find.byKey(const Key('timetable-copy-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-copy-to-2')));
    await tester.tap(find.byKey(const Key('timetable-copy-to-3')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('timetable-copy-confirm')));
    await tester.pumpAndSettle();
    final copied = bodyOf(b.sent('POST', '/api/timetable/copy-day').single);
    expect(copied, containsPair('from_weekday', 0));
    expect(copied['to_weekdays'], [2, 3]);
    expect(copied, containsPair('week', 'b'));
  });

  testWidgets('children only view: no add, copy or edit controls', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend(canEdit: false);
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-menu')), findsNothing);
    expect(find.byKey(const Key('timetable-add-0')), findsNothing);
    expect(find.byKey(const Key('timetable-copy-0')), findsNothing);
    await tester.tap(find.byKey(const Key('timetable-entry-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-title')), findsNothing);
    // Weekend days without entries are hidden for viewers
    expect(find.byKey(const Key('timetable-day-6')), findsNothing);
    expect(find.byKey(const Key('timetable-day-5')), findsOneWidget);
  });

  testWidgets('week copy and settings are sent', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('A-Woche nach B-Woche kopieren'));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/timetable/copy-week').single), containsPair('to_week', 'b'));

    await tester.tap(find.byKey(const Key('timetable-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Einstellungen'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-ab-switch')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-settings-save')));
    await tester.pumpAndSettle();
    final saved = bodyOf(b.sent('PUT', '/api/timetable/settings').single);
    expect(saved['ab_reference'], isNull);
    expect(saved['holiday_feed'], 'ics:schule');
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('timetable fits 360 dp at text scale $scale', (tester) async {
      await setScreenSize(tester, const Size(360, 780));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final b = _backend();
      await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(find.byKey(const Key('timetable-day-6')), 200, scrollable: find.byType(Scrollable).last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      // Editor sheet
      await tester.tap(find.byKey(const Key('timetable-add-6')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('timetable-title')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
