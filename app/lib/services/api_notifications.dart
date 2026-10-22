part of 'api_client.dart';

/// Notification inbox, push devices and ntfy.
mixin NotificationsApi on ApiClientBase {
  // ── Mitteilungen ───────────────────────────────────────────────────────────

  Future<NotificationInbox> notifications({int limit = 100}) async => NotificationInbox.fromJson(
      await _send('GET', '/api/me/notifications?limit=$limit') as Map<String, dynamic>);

  /// Ohne [ids]: alle als gelesen markieren.
  Future<void> markNotificationsRead([List<int>? ids]) =>
      _send('POST', '/api/me/notifications/read', body: {if (ids != null) 'ids': ids});

  // ── Push & Einstellungen ───────────────────────────────────────────────────

  Future<void> registerDevice({required String token, required String deviceName}) =>
      _send('POST', '/api/push/devices',
          body: {'kind': 'fcm', 'token': token, 'device_name': deviceName});

  /// Web Push (Safari/iOS, Browser): Subscription-JSON aus dem PushManager.
  Future<void> registerWebPush({required Map<String, dynamic> subscription, required String deviceName}) =>
      _send('POST', '/api/push/devices',
          body: {'kind': 'webpush', 'subscription': subscription, 'device_name': deviceName});

  /// Öffentlicher VAPID-Schlüssel des Servers, null wenn Web Push dort nicht eingerichtet ist.
  Future<String?> vapidPublicKey() async {
    try {
      final json = await _send('GET', '/api/push/vapid-public-key', auth: false);
      return (json as Map<String, dynamic>)['publicKey'] as String?;
    } on ApiException catch (e) {
      if (e.statusCode == 501) return null;
      rethrow;
    }
  }

  Future<List<Device>> devices() async =>
      _maps(await _send('GET', '/api/push/devices')).map(Device.fromJson).toList();

  Future<void> deleteDevice(int id) => _send('DELETE', '/api/push/devices/$id');

  Future<NtfySettings> ntfySettings() async =>
      NtfySettings.fromJson(await _send('GET', '/api/me/ntfy') as Map<String, dynamic>);

  Future<NtfySettings> setNtfy({required bool enabled, String? topic}) async => NtfySettings.fromJson(
      await _send('PUT', '/api/me/ntfy', body: {'enabled': enabled, if (topic != null) 'topic': topic}) as Map<String, dynamic>);

  Future<NtfySettings> newNtfyTopic() async =>
      NtfySettings.fromJson(await _send('POST', '/api/me/ntfy/new-topic') as Map<String, dynamic>);

  /// Schickt eine Testnachricht an alle eigenen Geräte; liefert die Zahl erreichter Geräte.
  Future<int> testPush() async {
    final json = await _send('POST', '/api/push/test');
    return parseInt(json) ?? 0;
  }

  Future<List<NotificationPref>> notificationPrefs() async =>
      _maps(await _send('GET', '/api/push/me/notification-prefs'))
          .map(NotificationPref.fromJson)
          .toList();

  Future<void> saveNotificationPrefs(List<NotificationPref> prefs) =>
      _send('PUT', '/api/push/me/notification-prefs',
          body: prefs.map((p) => p.toJson()).toList());
}
