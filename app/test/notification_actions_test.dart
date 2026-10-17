import 'dart:convert';

import 'package:familienhub/services/notification_actions.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('payload keeps route and action data, old payloads still open routes', () {
    final p = notificationPayload({'route': '/reminders', 'reminder_id': '7', 'action_token': 'tok', 'title': 'x'});
    expect(jsonDecode(p), {'route': '/reminders', 'reminder_id': '7', 'action_token': 'tok'});
    expect(routeFromPayload(p), '/reminders');
    expect(routeFromPayload('/shopping'), '/shopping'); // altes Format: nur Route
    expect(routeFromPayload(null), isNull);
  });

  test('details contain only known actions', () {
    final d = detailsFor({'category': 'reminder', 'actions': 'done,löschen,snooze_1h'});
    final ids = d.android!.actions!.map((AndroidNotificationAction a) => a.id).toList();
    expect(ids, ['done', 'snooze_1h']);
    expect(d.android!.channelId, 'reminder');
  });

  test('action button posts token to the server without login', () async {
    SharedPreferences.setMockInitialValues({'server_base_url': 'https://hub.test'});
    final calls = <http.Request>[];
    final client = MockClient((r) async {
      calls.add(r);
      return http.Response('{}', 200);
    });
    final payload = notificationPayload({'route': '/reminders', 'reminder_id': '7', 'action_token': 'tok-7'});

    expect(await performReminderAction(payload, 'snooze_1h', client: client), isTrue);
    expect(calls.single.url.toString(), 'https://hub.test/api/reminders/7/action');
    expect(calls.single.headers.containsKey('Authorization'), isFalse);
    expect(jsonDecode(calls.single.body), {'action': 'snooze_1h', 'token': 'tok-7'});

    expect(await performReminderAction(payload, 'löschen', client: client), isFalse);
    expect(await performReminderAction(notificationPayload({'route': '/'}), 'done', client: client), isFalse);
    expect(calls, hasLength(1));
  });
}
