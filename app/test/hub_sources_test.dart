import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Built-in sources: events of the hub's family calendar can be deleted in the app, CalDAV events cannot.
void main() {
  setUp(setUpTestEnv);

  String day(int add) {
    final d = DateTime.now().add(Duration(days: add));
    return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  testWidgets('hub event has a delete button that asks first, CalDAV event has none', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    var events = [
      {'id': 7, 'source': 'hub', 'title': 'Kinderarzt', 'start': '${day(1)}T10:00:00', 'end': '${day(1)}T11:00:00', 'all_day': false},
      {'source': 'caldav', 'title': 'Dienstreise', 'start': '${day(2)}T08:00:00', 'end': '${day(2)}T18:00:00', 'all_day': false},
    ];
    b.on('GET', '/api/calendar/events', (_) => jsonResponse(events));
    b.on('DELETE', '/api/calendar/events/7', (_) {
      events = events.where((e) => e['id'] != 7).toList();
      return jsonResponse(null, status: 204);
    });
    await tester.pumpWidget(appWith(b.api(), const CalendarScreen()));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('event-delete-7')), findsOneWidget);
    expect(find.byTooltip('Termin löschen'), findsOneWidget); // only the hub event

    await tester.tap(find.byKey(const ValueKey('event-delete-7')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Abbrechen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/calendar/events/7'), isEmpty);

    await tester.tap(find.byKey(const ValueKey('event-delete-7')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Löschen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/calendar/events/7'), hasLength(1));
    expect(find.text('Kinderarzt'), findsNothing);
    expect(find.text('Dienstreise'), findsOneWidget);
  });
}
