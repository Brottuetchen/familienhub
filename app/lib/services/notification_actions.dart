import 'dart:convert';
import 'dart:ui' show DartPluginRegistrant;

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/account.dart';
import 'background.dart';
import '../l10n/l10n.dart';

/// Knöpfe in Erinnerungs-Mitteilungen (Android). Kommt als FCM-Datennachricht mit
/// `actions` und `action_token`; die App stellt sie selbst dar – auch im Hintergrund.
Map<String, String> get reminderActions => <String, String>{
  'done': l10n.done,
  'snooze_1h': l10n.in1HourShort,
  'tomorrow': l10n.tomorrow,
};

/// Payload, die an der lokalen Mitteilung hängt (Ziel + Aktionsdaten).
String notificationPayload(Map<String, dynamic> data) => jsonEncode({
      'route': data['route'],
      'reminder_id': data['reminder_id'],
      'action_token': data['action_token'],
    });

/// Route aus der Payload (auch alte Payloads, die nur die Route enthielten).
String? routeFromPayload(String? payload) {
  if (payload == null || payload.isEmpty) return null;
  try {
    final p = jsonDecode(payload);
    return p is Map ? p['route'] as String? : payload;
  } catch (_) {
    return payload;
  }
}

NotificationDetails detailsFor(Map<String, dynamic> data) {
  final category = (data['category'] as String?) ?? 'system';
  final wanted = ((data['actions'] as String?) ?? '').split(',').where(reminderActions.containsKey).toList();
  return NotificationDetails(
    android: AndroidNotificationDetails(
      category,
      notificationCategories[category] ?? category,
      importance: Importance.high,
      priority: Priority.high,
      actions: [
        for (final a in wanted) AndroidNotificationAction(a, reminderActions[a]!, cancelNotification: true),
      ],
    ),
  );
}

/// Zeigt eine Hub-Mitteilung lokal an (Vorder- und Hintergrund).
Future<void> showHubNotification(FlutterLocalNotificationsPlugin plugin, RemoteMessage message) async {
  final data = message.data;
  final title = message.notification?.title ?? data['title'] as String?;
  if (title == null) return;
  final body = message.notification?.body ?? data['body'] as String? ?? '';
  await plugin.show(message.messageId.hashCode, title, body, detailsFor(data), payload: notificationPayload(data));
}

/// Knopf gedrückt: Aktion mit dem Aktions-Token an den Server (kein Login nötig).
Future<bool> performReminderAction(String? payload, String action, {http.Client? client}) async {
  if (payload == null || !reminderActions.containsKey(action)) return false;
  final p = jsonDecode(payload) as Map<String, dynamic>;
  final id = p['reminder_id'];
  final token = p['action_token'];
  if (id == null || token == null) return false;
  final prefs = await SharedPreferences.getInstance();
  final base = prefs.getString('server_base_url');
  if (base == null || base.isEmpty) return false;
  final c = client ?? http.Client();
  try {
    final res = await c.post(
      Uri.parse('$base/api/reminders/$id/action'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'action': action, 'token': token}),
    );
    return res.statusCode == 200;
  } catch (e) {
    debugPrint('[push] Aktion fehlgeschlagen: $e');
    return false;
  } finally {
    if (client == null) c.close();
  }
}

/// Hintergrund-Einstieg: Knopf gedrückt, während die App geschlossen ist.
@pragma('vm:entry-point')
void notificationActionInBackground(NotificationResponse response) {
  DartPluginRegistrant.ensureInitialized();
  final action = response.actionId;
  if (action != null) performReminderAction(response.payload, action);
}

/// Hintergrund-Einstieg: FCM-Datennachricht (Erinnerung mit Knöpfen) bei geschlossener App.
@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  if (message.data['type'] == 'refresh') {
    // stiller Push: Widgets sitzungsgebunden aktualisieren, keine Mitteilung
    DartPluginRegistrant.ensureInitialized();
    await backgroundWidgetRefresh();
    return;
  }
  if (message.notification != null) return; // zeigt Android selbst an
  DartPluginRegistrant.ensureInitialized();
  await loadAppLanguage(); // Knopf-Beschriftungen in der Sprache der App
  final plugin = FlutterLocalNotificationsPlugin();
  await plugin.initialize(
    const InitializationSettings(android: AndroidInitializationSettings('@mipmap/ic_launcher')),
    onDidReceiveBackgroundNotificationResponse: notificationActionInBackground,
  );
  await showHubNotification(plugin, message);
}
