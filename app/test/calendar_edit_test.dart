import 'package:familienhub/models/calendar_event.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Event details: what is shown, edit and delete only where allowed.
void main() {
  setUp(setUpTestEnv);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/calendar/calendars', [
      {'id': 'hub', 'name': 'Familie', 'source': 'hub', 'writable': true, 'family': true},
      {'id': 'caldav:fam', 'name': 'Familie (Nextcloud)', 'source': 'caldav', 'writable': true, 'family': true},
      {'id': 'ics:ferien', 'name': 'Schulferien', 'source': 'ics', 'writable': false},
    ]);
    b.json('PUT', '/api/calendar/events/7', {'id': 7});
    b.json('DELETE', '/api/calendar/caldav/caldav:fam/u9', null, status: 204);
    return b;
  }

  CalendarEvent ev(Map<String, dynamic> j) => CalendarEvent.fromJson(j);

  Future<void> pump(WidgetTester tester, FakeBackend b, CalendarEvent e) async {
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), Scaffold(body: EventDetailsSheet(event: e))));
    await tester.pumpAndSettle();
  }

  testWidgets('hub event: details shown, edit sends the changes', (tester) async {
    final b = backend();
    await pump(tester, b, ev({'id': 7, 'source': 'hub', 'calendar_id': 'hub', 'calendar': 'Familie', 'title': 'Schwimmkurs',
      'start': '2099-04-06T16:00:00', 'end': '2099-04-06T17:00:00', 'location': 'Hallenbad', 'notes': 'Badekappe', 'recurrence': 'weekly'}));
    expect(find.text('Hallenbad'), findsOneWidget);
    expect(find.text('Badekappe'), findsOneWidget);
    expect(find.text('Wöchentlich'), findsOneWidget);
    await tester.tap(find.byKey(const Key('event-edit')));
    await tester.pumpAndSettle();
    expect(find.text('Termin bearbeiten'), findsWidgets);
    expect(find.byKey(const Key('event-calendar')), findsNothing); // calendar stays fixed
    await tester.enterText(find.byKey(const Key('event-title')), 'Schwimmkurs Mia');
    await tester.ensureVisible(find.byKey(const Key('event-save')));
    await tester.tap(find.byKey(const Key('event-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('PUT', '/api/calendar/events/7').single);
    expect(body['title'], 'Schwimmkurs Mia');
    expect(body['location'], 'Hallenbad');
    expect(body['recurrence'], 'weekly');
    expect(body['start'] as String, startsWith('2099-04-06T16:00:00')); // with the device's offset
  });

  testWidgets('CalDAV series: delete warns about the whole series', (tester) async {
    final b = backend();
    final e = ev({'source': 'caldav', 'calendar_id': 'caldav:fam', 'uid': 'u9', 'calendar': 'Familie (Nextcloud)', 'title': 'Training',
      'start': '2099-04-07T17:00:00', 'end': '2099-04-07T18:00:00', 'recurring': true});
    await pump(tester, b, e);
    expect(find.text('Teil einer Serie'), findsOneWidget);
    await tester.tap(find.byKey(const Key('event-details-delete')));
    await tester.pumpAndSettle();
    expect(find.textContaining('ganze Serie'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Löschen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/calendar/caldav/caldav:fam/u9'), hasLength(1));
  });

  testWidgets('CalDAV series: editing locks the times and offers no repeat', (tester) async {
    final b = backend();
    final e = ev({'source': 'caldav', 'calendar_id': 'caldav:fam', 'uid': 'u9', 'title': 'Training',
      'start': '2099-04-07T17:00:00', 'end': '2099-04-07T18:00:00', 'recurring': true});
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), Scaffold(body: EventCreateSheet(initial: e))));
    await tester.pumpAndSettle();
    expect(find.textContaining('Zeiten einer Serie'), findsOneWidget);
    expect(find.byKey(const Key('event-start')), findsNothing);
    expect(find.byKey(const Key('event-repeat')), findsNothing);
  });

  testWidgets('subscription events and children: no edit, no delete', (tester) async {
    final b = backend();
    await pump(tester, b, ev({'source': 'ics', 'calendar_id': 'ics:ferien', 'calendar': 'Schulferien', 'title': 'Herbstferien',
      'start': '2099-10-26', 'end': '2099-10-31', 'all_day': true}));
    expect(find.textContaining('ganztägig'), findsOneWidget);
    expect(find.byKey(const Key('event-edit')), findsNothing);

    final kid = backend()..json('GET', '/api/auth/me', {'id': 3, 'username': 'kim', 'role': 'child', 'is_admin': false});
    await pump(tester, kid, ev({'id': 7, 'source': 'hub', 'calendar_id': 'hub', 'title': 'Probe', 'start': '2099-04-06T16:00:00',
      'end': '2099-04-06T17:00:00'}));
    expect(find.byKey(const Key('event-edit')), findsNothing);
    expect(find.byKey(const Key('event-details-delete')), findsNothing);
  });
}
