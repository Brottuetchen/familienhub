import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// New event: the family calendar is suggested, the chosen target and details are sent, the choice is remembered.
void main() {
  setUp(setUpTestEnv);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/calendar/calendars', [
      {'id': 'hub', 'name': 'Familie', 'source': 'hub', 'writable': true, 'family': true},
      {'id': 'caldav:privat', 'name': 'Persönlich', 'source': 'caldav', 'writable': true, 'family': false},
      {'id': 'ics:ferien', 'name': 'Schulferien', 'source': 'ics', 'writable': false, 'family': true},
    ]);
    b.json('POST', '/api/calendar/events', {'id': 1});
    return b;
  }

  Future<void> open(WidgetTester tester, FakeBackend b) async {
    await setScreenSize(tester, const Size(420, 1400));
    await tester.pumpWidget(appWith(b.api(), const Scaffold(body: EventCreateSheet())));
    await tester.pumpAndSettle();
  }

  testWidgets('family calendar suggested, only writable calendars offered, details sent', (tester) async {
    final b = backend();
    await open(tester, b);
    expect(find.text('Familie'), findsOneWidget); // selected value
    await tester.tap(find.byKey(const Key('event-calendar')));
    await tester.pumpAndSettle();
    expect(find.text('Schulferien'), findsNothing); // read-only subscription is not a target
    await tester.tap(find.text('Familie').last);
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('event-title')), 'Elternabend');
    await tester.enterText(find.byKey(const Key('event-location')), 'Aula');
    await tester.tap(find.byKey(const Key('event-repeat')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Monatlich').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('event-save')));
    await tester.tap(find.byKey(const Key('event-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/calendar/events').single);
    expect(body['calendar_id'], 'hub');
    expect(body['location'], 'Aula');
    expect(body['recurrence'], 'monthly');
    expect((await SharedPreferences.getInstance()).getString('calendar_last_target'), 'hub');
  });

  testWidgets('the last chosen calendar is suggested next time; all-day over several days', (tester) async {
    SharedPreferences.setMockInitialValues({'calendar_last_target': 'caldav:privat'});
    final b = backend();
    await open(tester, b);
    expect(find.text('Persönlich'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('event-title')), 'Urlaub');
    await tester.tap(find.text('Ganztägig'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('event-end-day')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('event-save')));
    await tester.tap(find.byKey(const Key('event-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/calendar/events').single);
    expect(body['calendar_id'], 'caldav:privat');
    expect(body['all_day'], true);
    expect(DateTime.parse(body['end'] as String).difference(DateTime.parse(body['start'] as String)).inDays, 1);
  });
}
