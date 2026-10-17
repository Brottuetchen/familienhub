import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class CachedJson {
  final dynamic data;
  final DateTime savedAt;
  const CachedJson(this.data, this.savedAt);
}

/// Letzte Antwort je Endpunkt, damit die App ohne Netz etwas zeigt.
class CacheUpdate {
  final String? key;
  final CachedJson? value;
  final Object? error;
  final bool refreshing;
  final bool invalidated;
  /// Nur gemerkte Offline-Änderungen neu überlagert: Daten tauschen, Status (offline, Stand) behalten.
  final bool overlay;
  const CacheUpdate(this.key, {this.value, this.error, this.refreshing = false, this.invalidated = false,
      this.overlay = false});
}

class ResponseCache {
  static const _prefix = 'cache:';

  Future<void> put(String key, dynamic json, {bool Function()? isCurrent}) async {
    final prefs = await SharedPreferences.getInstance();
    if (isCurrent != null && !isCurrent()) return;
    await prefs.setString(
      '$_prefix$key',
      jsonEncode({'saved_at': DateTime.now().toIso8601String(), 'data': json}),
    );
  }

  Future<CachedJson?> get(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('$_prefix$key');
    if (raw == null) return null;
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      return CachedJson(map['data'], DateTime.parse(map['saved_at'] as String));
    } catch (_) {
      return null;
    }
  }

  Future<void> removeWhere(bool Function(String) matches) async {
    final prefs = await SharedPreferences.getInstance();
    for (final key in prefs.getKeys().where((k) => k.startsWith(_prefix)).toList()) {
      if (matches(key.substring(_prefix.length))) await prefs.remove(key);
    }
  }

  /// Beim Abmelden: keine Daten des vorherigen Nutzers liegen lassen – auch keine gemerkten Änderungen.
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    for (final key in prefs.getKeys().where((k) => k.startsWith(_prefix) || k.startsWith(queuePrefix)).toList()) {
      await prefs.remove(key);
    }
  }

  /// Offline-Warteschlange (#32), je Server und Identität getrennt wie der Cache.
  static const queuePrefix = 'offline_queue:';
}
