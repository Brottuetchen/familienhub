import 'dart:convert';
import 'dart:ui' show DartPluginRegistrant;

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';
import 'package:workmanager/workmanager.dart';

import '../models/shopping.dart';
import '../models/today.dart';
import 'home_widgets.dart';
import 'session_store.dart';
import 'widget_access.dart';

const _refreshTask = 'familienhub.widget-refresh';

/// Widgets im Hintergrund aktualisieren (stiller Push oder alle 15 Minuten).
///
/// Sitzungsgebunden: geschrieben wird nur, wenn dieselbe Widget-Sitzung vor dem Abruf, vor dem
/// Schreiben und danach gilt (HomeWidgets.publishFor). Abgerufen wird mit dem eigenen Widget-Zugang,
/// nie mit den Login-Tokens. Ein widerrufener Zugang (401) leert die Widgets.
@pragma('vm:entry-point')
Future<void> backgroundWidgetRefresh({http.Client? client}) async {
  if (!HomeWidgets.supported) return;
  // Ohne eigenen Widget-Zugang nichts anfassen (weder Netz noch Widget-Speicher)
  final token = await WidgetAccess.token();
  if (token == null) return;
  final store = SecureSessionStore();
  final base = await store.baseUrl();
  final session = await HomeWidgets.session();
  if (base == null || session == null) return;
  // Gleiche Sitzung = gleiche Widget-Kennung, gleicher Server, gleicher Widget-Zugang
  Future<bool> same() async =>
      await HomeWidgets.session() == session && await store.baseUrl() == base && await WidgetAccess.token() == token;
  Intl.defaultLocale = 'de_DE';
  await initializeDateFormatting('de_DE');
  final c = client ?? http.Client();
  try {
    Future<Map<String, dynamic>?> get(String path) async {
      final r = await c
          .get(Uri.parse('$base$path'), headers: {'Authorization': 'Bearer $token', 'Accept': 'application/json'})
          .timeout(const Duration(seconds: 15));
      if (r.statusCode == 401) throw const _Revoked();
      if (r.statusCode != 200) return null;
      return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    }

    final today = await get('/api/today');
    final shopping = await get('/api/shopping');
    if (!await same()) return; // Abmelden/Wechsel während des Abrufs
    await HomeWidgets.publishFor(
      session,
      today: today == null ? null : TodayData.fromJson(today),
      shopping: shopping == null ? null : ShoppingData.fromJson(shopping),
    );
    if (!await same()) await HomeWidgets.endSession(); // Wechsel während des Schreibens: sofort leeren
  } on _Revoked {
    // Zugang widerrufen – aber nur aufräumen, wenn sich die Sitzung nicht inzwischen geändert hat
    if (await same()) await WidgetAccess.forget();
  } catch (e) {
    debugPrint('[widgets] Hintergrund-Aktualisierung fehlgeschlagen: $e');
  } finally {
    if (client == null) c.close();
  }
}

class _Revoked implements Exception {
  const _Revoked();
}

@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, input) async {
    DartPluginRegistrant.ensureInitialized();
    await backgroundWidgetRefresh();
    return true;
  });
}

/// Regelmäßige Aktualisierung (Android-Minimum 15 Minuten), zusätzlich zu den stillen Pushes.
Future<void> startWidgetRefresh() async {
  if (!HomeWidgets.supported) return;
  try {
    await Workmanager().initialize(callbackDispatcher);
    await Workmanager().registerPeriodicTask(
      _refreshTask,
      _refreshTask,
      frequency: const Duration(minutes: 15),
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
    );
  } catch (e) {
    debugPrint('[widgets] WorkManager nicht verfügbar: $e');
  }
}
