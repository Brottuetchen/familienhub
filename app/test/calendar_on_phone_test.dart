import 'package:familienhub/screens/more/notification_settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Event reminders: "calendar is set up on my phone" turns the hub's event notifications off for this person.
void main() {
  setUp(setUpTestEnv);

  testWidgets('shows the setting and saves the change', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    var value = false;
    b.on('GET', '/api/calendar/me/reminders', (_) => jsonResponse({'calendar_on_phone': value}));
    b.on('PUT', '/api/calendar/me/reminders', (req) {
      value = bodyOf(req)['calendar_on_phone'] == true;
      return jsonResponse({'calendar_on_phone': value});
    });
    await tester.pumpWidget(appWith(b.api(), const Scaffold(body: CalendarOnPhoneTile())));
    await tester.pumpAndSettle();
    expect(find.text('Kalender ist am Handy eingerichtet'), findsOneWidget);
    expect(tester.widget<SwitchListTile>(find.byKey(const Key('calendar-on-phone'))).value, isFalse);
    await tester.tap(find.byKey(const Key('calendar-on-phone')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/calendar/me/reminders').single), {'calendar_on_phone': true});
    expect(tester.widget<SwitchListTile>(find.byKey(const Key('calendar-on-phone'))).value, isTrue);
  });
}
