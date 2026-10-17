import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'home_widgets.dart';

/// Eigener Geräte-Zugang (persönliches API-Token) nur für Widget-Aktualisierungen im Hintergrund.
///
/// Der Hintergrund fasst die Login-Tokens nie an: der Hub rotiert Refresh-Tokens, gleichzeitiges
/// Erneuern aus zwei Isolates würde die Anmeldung beenden. Das Token liegt verschlüsselt auf dem
/// Gerät, wird beim Abmelden widerrufen und steht unter „Zugänge für Assistenten“ (selbst widerrufbar).
class WidgetAccess {
  static const _storage = FlutterSecureStorage(aOptions: AndroidOptions(encryptedSharedPreferences: true));
  static const _kToken = 'widget_api_token';
  static const _kId = 'widget_api_token_id';
  static const tokenName = 'Widget (Android-Gerät)';

  static Future<String?> token() async {
    try {
      return await _storage.read(key: _kToken);
    } catch (_) {
      return null;
    }
  }

  /// Angemeldet im Vordergrund: Sitzungs-Kennung setzen, Zugang anlegen, falls noch keiner da ist.
  static Future<void> ensure(ApiClient api) async {
    if (!HomeWidgets.supported) return;
    try {
      await HomeWidgets.startSession();
      if (await token() != null) return;
      final created = await api.createApiToken(tokenName);
      if (created.token == null) return;
      await _storage.write(key: _kToken, value: created.token);
      await _storage.write(key: _kId, value: created.id.toString());
    } catch (e) {
      debugPrint('[widgets] Zugang nicht angelegt: $e');
    }
  }

  /// Abmelden (noch mit gültiger Anmeldung): Zugang beim Hub widerrufen, lokal löschen, Widgets leeren.
  static Future<void> revoke(ApiClient api) async {
    if (!HomeWidgets.supported) return;
    try {
      final id = int.tryParse(await _storage.read(key: _kId) ?? '');
      if (id != null) await api.revokeApiToken(id);
    } catch (e) {
      debugPrint('[widgets] Zugang nicht widerrufen (bleibt unter „Zugänge für Assistenten“): $e');
    }
    await forget();
  }

  /// Sitzung serverseitig beendet: nur lokal löschen und Widgets leeren.
  static Future<void> forget() async {
    if (!HomeWidgets.supported) return;
    try {
      await _storage.delete(key: _kToken);
      await _storage.delete(key: _kId);
    } catch (_) {}
    await HomeWidgets.endSession();
  }
}
