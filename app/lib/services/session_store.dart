import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Speicher für Server-Adresse und Tokens.
abstract class SessionStore {
  Future<String?> baseUrl();
  Future<void> saveBaseUrl(String url);
  Future<String?> accessToken();
  Future<String?> refreshToken();
  Future<void> saveTokens({required String access, String? refresh});
  Future<void> clearTokens();
}

/// Tokens im Android-Keystore (flutter_secure_storage), Server-Adresse in den Prefs.
class SecureSessionStore implements SessionStore {
  static const _kAccess = 'access_token';
  static const _kRefresh = 'refresh_token';
  static const _kBaseUrl = 'server_base_url';

  final _secure = const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> baseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final url = prefs.getString(_kBaseUrl);
    return (url == null || url.isEmpty) ? null : url;
  }

  @override
  Future<void> saveBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kBaseUrl, normalizeBaseUrl(url));
  }

  @override
  Future<String?> accessToken() => _secure.read(key: _kAccess);

  @override
  Future<String?> refreshToken() => _secure.read(key: _kRefresh);

  @override
  Future<void> saveTokens({required String access, String? refresh}) async {
    await _secure.write(key: _kAccess, value: access);
    if (refresh != null) await _secure.write(key: _kRefresh, value: refresh);
  }

  @override
  Future<void> clearTokens() async {
    await _secure.delete(key: _kAccess);
    await _secure.delete(key: _kRefresh);
  }
}

/// Für Tests.
class MemorySessionStore implements SessionStore {
  String? url;
  String? access;
  String? refresh;

  MemorySessionStore({this.url, this.access, this.refresh});

  @override
  Future<String?> baseUrl() async => url;
  @override
  Future<void> saveBaseUrl(String value) async => url = normalizeBaseUrl(value);
  @override
  Future<String?> accessToken() async => access;
  @override
  Future<String?> refreshToken() async => refresh;
  @override
  Future<void> saveTokens({required String access, String? refresh}) async {
    this.access = access;
    if (refresh != null) this.refresh = refresh;
  }

  @override
  Future<void> clearTokens() async {
    access = null;
    refresh = null;
  }
}

/// „hub.example.org/“ → „https://hub.example.org“
String normalizeBaseUrl(String input) {
  var url = input.trim();
  while (url.endsWith('/')) {
    url = url.substring(0, url.length - 1);
  }
  if (url.isNotEmpty && !url.contains('://')) url = 'https://$url';
  return url;
}
