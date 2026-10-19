import 'package:familienhub/l10n/l10n.dart';
import 'package:familienhub/models/timetable.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/timetable/timetable_screen.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

String _iso(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

DateTime _monday() {
  final t = DateTime.now();
  return DateTime(t.year, t.month, t.day).subtract(Duration(days: t.weekday - 1));
}

Map<String, dynamic> _lesson(String title, String start, String end,
        {String status = 'normal', int? period, String kind = 'school', String? note, String? teacher, String? location, DateTime? date}) =>
    {
      'id': 0, 'child_id': 7, 'weekday': 0, 'week': 'all', 'start': start, 'end': end, 'title': title, 'kind': kind,
      'location': location, 'date': _iso(date ?? _monday()), 'status': status, 'note': note, 'teacher': teacher,
      'period': period, 'source': 'plugin',
    };

Map<String, dynamic> _week(DateTime monday, {String status = 'ok'}) => {
      'child': {'id': 7, 'name': 'Mia'},
      'start': _iso(monday),
      'end': _iso(monday.add(const Duration(days: 6))),
      'week': null,
      'plugin': {'id': 'fakeschool', 'name': 'Fake School', 'person': 'Mia Muster', 'status': status},
      'days': [
        for (var i = 0; i < 7; i++)
          {
            'date': _iso(monday.add(Duration(days: i))),
            'weekday': i,
            'source': i == 0 ? 'plugin' : 'manual',
            'holiday': i == 2 ? 'Herbstferien' : null,
            'entries': i == 0
                ? [
                    _lesson('Mathe sehr lange Bezeichnung für den Überlauftest', '08:00', '08:45',
                        status: 'cancelled', period: 1, note: 'Lehrer krank', teacher: 'Frau Mustermann', location: 'Raum 204 im Nebengebäude',
                        date: monday),
                    _lesson('Englisch', '08:50', '09:35', status: 'substitution', period: 2, date: monday),
                    _lesson('Kunst', '09:40', '10:25', period: 3, date: monday),
                  ]
                : [],
          },
      ],
    };

FakeBackend _backend({bool plugin = true, String status = 'ok'}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/timetable/children', [
    {'id': 7, 'name': 'Mia'},
  ]);
  b.json('GET', '/api/timetable', {
    'child': {'id': 7, 'name': 'Mia'},
    'entries': [
      {'id': 4, 'child_id': 7, 'weekday': 5, 'week': 'all', 'start': '10:00', 'end': '11:30', 'title': 'Fußball', 'kind': 'club', 'location': null},
    ],
    'settings': {'ab_reference': null, 'holiday_feed': null, 'feeds': []},
    'current_week': null,
    'holidays': [],
    'can_edit': true,
    'plugin': plugin ? {'id': 'fakeschool', 'name': 'Fake School', 'person': 'Mia Muster', 'status': 'ok'} : null,
  });
  b.on('GET', '/api/timetable/week', (r) {
    final start = DateTime.parse(r.url.queryParameters['start']!);
    return jsonResponse(_week(start.subtract(Duration(days: start.weekday - 1)), status: status));
  });
  b.json('GET', '/api/timetable/sources', {
    'children': [
      {'child_id': 7, 'name': 'Mia', 'plugin_id': null, 'person_id': null, 'person_name': null},
      {'child_id': 8, 'name': 'Ben', 'plugin_id': null, 'person_id': null, 'person_name': null},
    ],
    'plugins': [
      {'id': 'fakeschool', 'name': 'Fake School', 'people_known': true, 'people': [
        {'id': 'p1', 'name': 'Mia Muster'}, {'id': 'p2', 'name': 'Ben Beispiel'},
      ]},
      {'id': 'freeform', 'name': 'Free Form', 'people_known': false, 'people': []},
    ],
  });
  b.json('PUT', '/api/timetable/sources', {'children': [], 'plugins': []});
  return b;
}

void main() {
  setUp(setUpTestEnv);
  tearDown(() => setAppLanguage('de'));

  group('Today summary', () {
    TodayTimetableChild kid(List<Map<String, dynamic>> entries) =>
        TodayTimetableChild.fromJson({'child_id': 7, 'name': 'Mia', 'holiday': null, 'entries': entries});

    test('cancelled periods are named, they do not count for "until"', () {
      final c = kid([
        _lesson('Mathe', '08:00', '08:45', status: 'cancelled', period: 1),
        _lesson('Deutsch', '08:50', '09:35', status: 'cancelled', period: 2),
        _lesson('Kunst', '09:40', '13:15', period: 3),
      ]);
      expect(c.summary, 'Schule bis 13:15, 1.–2. Stunde ausgefallen');
      setAppLanguage('en');
      expect(c.summary, 'School until 13:15, 1st–2nd period cancelled');
    });

    test('lessons without period numbers are counted, everything cancelled says so', () {
      expect(kid([_lesson('A', '08:00', '09:00', status: 'cancelled'), _lesson('B', '09:00', '10:00', status: 'cancelled'), _lesson('C', '10:00', '11:00')]).summary,
          'Schule bis 11:00, 2 Stunden ausgefallen');
      expect(kid([_lesson('A', '08:00', '09:00', status: 'cancelled', period: 1)]).summary, 'Schule fällt aus');
    });

    test('substitutions and cancelled non-school entries', () {
      final c = kid([
        _lesson('Mathe', '08:00', '09:00', status: 'substitution'),
        _lesson('Bio', '09:00', '10:00', status: 'changed'),
        _lesson('Schwimmen', '16:00', '17:00', kind: 'sport', status: 'cancelled'),
      ]);
      expect(c.summary, 'Schule bis 10:00, 2 Vertretungen, Schwimmen fällt aus');
    });

    test('period ranges and ordinals', () {
      expect(periodRanges([1, 2, 4, 5, 6, 9]), '1.–2., 4.–6., 9.');
      setAppLanguage('en');
      expect(periodRanges([1, 2, 3, 11, 12, 21]), '1st–3rd, 11th–12th, 21st');
    });
  });

  testWidgets('Today card tells which periods are cancelled', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    b.json('GET', '/api/today', {
      'date': '2026-10-19', 'events': [], 'tasks': {'status': 'ok', 'error': null, 'items': []}, 'meals': [],
      'shopping_open': 0, 'reminders': [],
      'timetable': {
        'status': 'ok',
        'children': [
          {'child_id': 7, 'name': 'Mia', 'holiday': null, 'source': 'plugin', 'entries': [
            _lesson('Mathe', '08:00', '08:45', status: 'cancelled', period: 1),
            _lesson('Deutsch', '08:50', '09:35', status: 'cancelled', period: 2),
          ]},
        ],
      },
    });
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('Mia: Schule fällt aus', findRichText: true), findsOneWidget);
  });

  testWidgets('week view: cancelled struck through, substitution marked, note and teacher shown', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-plugin-week')), findsOneWidget);
    expect(find.text('Stundenplan von Fake School'), findsOneWidget);

    final cancelled = tester.widget<Text>(find.textContaining('Mathe sehr lange'));
    expect(cancelled.style?.decoration, TextDecoration.lineThrough);
    expect(find.textContaining('Ausgefallen · Lehrer krank'), findsOneWidget);
    expect(find.textContaining('Frau Mustermann'), findsOneWidget);
    expect(tester.widget<Text>(find.text('Englisch')).style?.decoration, isNot(TextDecoration.lineThrough));
    expect(find.text('Vertretung'), findsOneWidget);
    expect(find.text('Kunst'), findsOneWidget);
    expect(find.textContaining('Herbstferien'), findsOneWidget);
    final requested = b.sent('GET', '/api/timetable/week').single.url.queryParameters;
    expect(requested['child_id'], '7');
    expect(requested['start'], _iso(_monday()));
  });

  testWidgets('week navigation and switching to the weekly plan', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-next-week')));
    await tester.pumpAndSettle();
    final starts = b.sent('GET', '/api/timetable/week').map((r) => r.url.queryParameters['start']).toList();
    expect(starts.last, _iso(_monday().add(const Duration(days: 7))));
    await tester.tap(find.byKey(const Key('timetable-view-plan')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-plugin-week')), findsNothing);
    expect(find.byKey(const Key('timetable-day-0')), findsOneWidget);
    expect(find.text('Fußball'), findsOneWidget);
  });

  testWidgets('plugin down: the banner says so', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend(status: 'unavailable');
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-plugin-unavailable')), findsOneWidget);
    expect(find.textContaining('Fake School ist nicht erreichbar'), findsOneWidget);
  });

  testWidgets('children without a plugin keep the weekly plan', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend(plugin: false);
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('timetable-plugin-week')), findsNothing);
    expect(find.byKey(const Key('timetable-view-week')), findsNothing);
    expect(find.byKey(const Key('timetable-day-0')), findsOneWidget);
  });

  testWidgets('parents map children to plugin people', (tester) async {
    await setScreenSize(tester, const Size(360, 900));
    final b = _backend(plugin: false);
    await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-sources-menu')));
    await tester.pumpAndSettle();
    // Mia: a plugin that lists people -> dropdown
    await tester.tap(find.byKey(const Key('timetable-source-plugin-7')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fake School').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('timetable-source-person-7-fakeschool')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mia Muster').last);
    await tester.pumpAndSettle();
    // Ben: a plugin without a people list -> free identifier
    await tester.tap(find.byKey(const Key('timetable-source-plugin-8')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Free Form').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('timetable-source-id-8')), ' student-42 ');
    await tester.tap(find.byKey(const Key('timetable-sources-save')));
    await tester.pumpAndSettle();
    final sent = bodyOf(b.sent('PUT', '/api/timetable/sources').single)['sources'] as List;
    expect(sent, [
      {'child_id': 7, 'plugin_id': 'fakeschool', 'person_id': 'p1'},
      {'child_id': 8, 'plugin_id': 'freeform', 'person_id': 'student-42'},
    ]);
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('plugin week and mapping sheet fit 360 dp at text scale $scale', (tester) async {
      await setScreenSize(tester, const Size(360, 780));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final b = _backend();
      await tester.pumpWidget(appWith(b.api(), const TimetableScreen()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(find.text('Kunst'), 200, scrollable: find.byType(Scrollable).last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('timetable-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('timetable-sources-menu')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.byKey(const Key('timetable-source-plugin-7')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('timetable-source-plugin-7')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fake School').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('timetable-source-person-7-fakeschool')), findsOneWidget);
      expect(l10n.timetable, isNotEmpty);
    });
  }
}
