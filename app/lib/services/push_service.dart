import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../models/account.dart';
import 'api_client.dart';
import 'notification_actions.dart';
import 'web_platform.dart' as webp;
import '../l10n/l10n.dart';

/// Push: Android über Firebase Cloud Messaging, Web (Safari/iOS, Browser) über Web Push.
///
/// Firebase ist optional: Ohne `google-services.json` schlägt
/// `Firebase.initializeApp()` fehl, [available] bleibt false und die App läuft
/// normal weiter. Im Web muss der Nutzer Push einmal per Tipp erlauben ([enableWebPush]).
class PushService {
  PushService(this.api);

  final ApiClient api;
  final _local = FlutterLocalNotificationsPlugin();
  final _routes = StreamController<String>.broadcast();
  bool available = false;
  String? lastError;
  bool _started = false;

  /// Ziele aus angetippten Mitteilungen (`data.route`).
  Stream<String> get routes => _routes.stream;

  Future<void> start() async {
    if (_started) return;
    _started = true;
    if (kIsWeb) {
      webp.serviceWorkerRoutes().listen(_routes.add);
      // Schon erlaubt (früherer Besuch): Abo still erneuern
      if (webp.webPushPermission() == 'granted') await _subscribeWeb(prompt: false);
      if (!available) lastError = webPushHint();
      return;
    }
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      // Selbst installierte iPhone-App (Sideload, kostenlose Apple-ID): Apple erlaubt dort keine Push-Mitteilungen.
      lastError = l10n.iosPushHint;
      return;
    }
    try {
      await Firebase.initializeApp();
    } catch (e) {
      lastError = l10n.firebaseMissing;
      debugPrint('[push] Firebase nicht verfügbar: $e');
      return;
    }
    try {
      await _setupLocalNotifications();
      final messaging = FirebaseMessaging.instance;
      // Android 13+: fragt POST_NOTIFICATIONS ab
      final settings = await messaging.requestPermission();
      if (settings.authorizationStatus == AuthorizationStatus.denied) {
        lastError = l10n.androidNotificationsOff;
        return;
      }
      final token = await messaging.getToken();
      if (token != null) await _register(token);
      messaging.onTokenRefresh.listen(_register);

      FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
      FirebaseMessaging.onMessage.listen(_showForeground);
      FirebaseMessaging.onMessageOpenedApp.listen(_openFromMessage);
      final initial = await messaging.getInitialMessage();
      if (initial != null) _openFromMessage(initial);
      available = true;
    } catch (e) {
      lastError = l10n.pushSetupFailed(e);
      debugPrint('[push] $e');
    }
  }

  /// Hinweis, warum Web Push (noch) nicht geht, sonst null.
  String? webPushHint() {
    if (!kIsWeb) return null;
    if (!webp.webPushSupported) {
      return webp.isStandalone()
          ? l10n.browserNoNotifications
          : l10n.iosAddToHomeFirst;
    }
    if (webp.webPushPermission() == 'denied') return l10n.notificationsBlocked;
    return null;
  }

  /// Web: Erlaubnis abfragen und Gerät anmelden. Direkt aus einem Tipp aufrufen.
  /// [vapidKey] vorher laden, damit zwischen Tipp und Abfrage nichts wartet (iOS).
  Future<bool> enableWebPush(String vapidKey) => _subscribeWeb(prompt: true, vapidKey: vapidKey);

  Future<bool> _subscribeWeb({required bool prompt, String? vapidKey}) async {
    try {
      final key = vapidKey ?? await api.vapidPublicKey();
      if (key == null) {
        lastError = l10n.webPushNotOnServer;
        return false;
      }
      final sub = await webp.subscribeWebPush(key, prompt: prompt);
      if (sub == null) {
        lastError = webPushHint() ?? l10n.notificationsNotAllowed;
        return false;
      }
      await api.registerWebPush(subscription: sub, deviceName: _deviceName());
      available = true;
      lastError = null;
      return true;
    } catch (e) {
      lastError = l10n.webPushFailed(e);
      debugPrint('[push] $e');
      return false;
    }
  }

  Future<void> _register(String token) async {
    try {
      await api.registerDevice(token: token, deviceName: _deviceName());
    } catch (e) {
      debugPrint('[push] Gerät nicht registriert: $e');
    }
  }

  String _deviceName() {
    if (kIsWeb) return webp.isStandalone() ? l10n.webAppHome : 'Browser';
    return l10n.familienhubApp(defaultTargetPlatform.name);
  }

  Future<void> _setupLocalNotifications() async {
    await _local.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
      onDidReceiveNotificationResponse: (response) async {
        final action = response.actionId;
        if (action != null && action.isNotEmpty) {
          await performReminderAction(response.payload, action);
          return;
        }
        final route = routeFromPayload(response.payload);
        if (route != null && route.isNotEmpty) _routes.add(route);
      },
      onDidReceiveBackgroundNotificationResponse: notificationActionInBackground,
    );
    final android = _local.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    for (final entry in notificationCategories.entries) {
      await android?.createNotificationChannel(AndroidNotificationChannel(
        entry.key,
        entry.value,
        importance: entry.key == 'system' ? Importance.defaultImportance : Importance.high,
      ));
    }
  }

  /// FCM zeigt im Vordergrund nichts an, das übernehmen wir (inkl. Datennachrichten mit Knöpfen).
  Future<void> _showForeground(RemoteMessage message) async {
    if (message.data['type'] == 'refresh') {
      _refreshes.add(null); // stiller Push: Daten neu laden, keine Mitteilung
      return;
    }
    await showHubNotification(_local, message);
  }

  final _refreshes = StreamController<void>.broadcast();

  /// Stille Aktualisierungs-Pushes im Vordergrund (Heute/Einkauf neu laden).
  Stream<void> get refreshes => _refreshes.stream;

  void _openFromMessage(RemoteMessage message) {
    final route = message.data['route'];
    if (route != null && route.isNotEmpty) _routes.add(route);
  }
}
