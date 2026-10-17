import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/account.dart';
import '../models/admin.dart';
import '../models/books.dart';
import '../models/calendar_event.dart';
import '../models/common.dart';
import '../models/documents.dart';
import '../models/media.dart';
import '../models/meals.dart';
import '../models/modules.dart';
import '../models/pending.dart';
import '../models/shopping.dart';
import '../models/themes.dart';
import '../models/task.dart';
import '../models/today.dart';
import 'offline_queue.dart';
import 'api_exceptions.dart';
import 'cache.dart';
import 'session_store.dart';

/// Einzige Stelle, die mit dem Familienhub-Backend spricht.
///
/// - Bearer-Token aus dem [SessionStore], bei 401 genau ein Refresh-Versuch.
/// - GETs mit Cache-Schlüssel landen im [ResponseCache] und kommen ohne Netz
///   von dort ([ApiResult.fromCache]).
/// - Schreibende Anfragen ohne Netz werfen [OfflineException].
class ApiClient {
  final http.Client _http;
  final SessionStore store;
  final ResponseCache cache;
  final Duration timeout;
  final _loggedOut = StreamController<void>.broadcast();
  Future<bool>? _refreshing;
  Future<void> _sessionWrites = Future.value();
  final _cacheUpdates = StreamController<CacheUpdate>.broadcast(sync: true);
  final _reads = <String, Future<({CachedJson value, bool offline, Object? error})>>{};
  final _versions = <String, int>{};
  final _nativeTaskLocks = <String, int>{};
  final _nativeTaskUncertain = <String, int>{};
  final _nativeTaskConfirmed = <String, int>{};
  // Laufende Hausaktion je Gerät (Wert = Sitzungs-Epoche): pro Gerät nie zwei gleichzeitig,
  // verschiedene Geräte dürfen parallel schalten wie in Home Assistant.
  final _houseActionEntities = <String, int>{};
  bool _houseActionFailed = false;
  final _houseActionChanges = StreamController<void>.broadcast();
  Stream<void> get houseActionChanges => _houseActionChanges.stream;
  bool get houseActionPending => _houseActionEntities.values.any((e) => e == _epoch);
  bool houseActionPendingFor(String entityId) => _houseActionEntities[entityId] == _epoch;
  bool get houseActionFailed => _houseActionFailed;

  void clearHouseActionFailure() {
    _houseActionFailed = false;
    _houseActionChanges.add(null);
  }
  int _epoch = 0;
  bool _ended = false;

  // ── Offline-Warteschlange (#32) ────────────────────────────────────────────
  // Einkauf und Nextcloud-Aufgaben gehen auch ohne Netz: Die Änderung wird gemerkt, sofort
  // überlagert angezeigt und später in derselben Reihenfolge gesendet (Idempotency-Key = id).
  // Nie für Haus, Habitica, Essen oder Erinnerungen. Abmelden verwirft gemerkte Änderungen.
  List<PendingChange> _pending = const [];
  String? _pendingScope;
  final _pendingChanges = StreamController<List<PendingChange>>.broadcast();
  Future<void>? _flushing;
  Timer? _flushTimer;
  static const retryEvery = Duration(seconds: 30);

  Stream<List<PendingChange>> get pendingChanges => _pendingChanges.stream;
  List<PendingChange> get pending => _pending;

  Future<List<PendingChange>> loadPending() async {
    final epoch = _epoch;
    final scope = await _scope();
    if (epoch != _epoch) return const [];
    if (_pendingScope == scope) return _pending;
    final raw = (await SharedPreferences.getInstance()).getString('${ResponseCache.queuePrefix}$scope');
    var list = const <PendingChange>[];
    if (raw != null) {
      try {
        list = (jsonDecode(raw) as List).map(PendingChange.fromJson).whereType<PendingChange>().toList();
      } catch (_) {}
    }
    if (epoch != _epoch) return const [];
    if (_pendingScope != scope) {
      _pendingScope = scope;
      _pending = List.unmodifiable(list);
      _pendingChanges.add(_pending);
      _scheduleFlush();
    }
    return _pending;
  }

  Future<void> _setPending(List<PendingChange> list) async {
    final scope = _pendingScope;
    if (scope == null) return;
    _pending = List.unmodifiable(list);
    _pendingChanges.add(_pending);
    _scheduleFlush();
    final prefs = await SharedPreferences.getInstance();
    if (scope != _pendingScope) return;
    final key = '${ResponseCache.queuePrefix}$scope';
    if (list.isEmpty) {
      await prefs.remove(key);
    } else {
      await prefs.setString(key, jsonEncode([for (final c in list) c.toJson()]));
    }
    await _republish();
  }

  void _scheduleFlush() {
    _flushTimer?.cancel();
    if (_pending.any((c) => !c.isConflict)) {
      _flushTimer = Timer(retryEvery, () => flushPending().ignore());
    }
  }

  /// Überlagerte Daten neu an alle Ansichten geben (ohne deren Status zu ändern).
  Future<void> _republish() async {
    final scope = _pendingScope;
    if (scope == null) return;
    for (final key in ['shopping', 'today', for (final v in TaskView.values) 'tasks:${v.apiName}']) {
      final value = await cache.get('$scope:$key');
      if (value != null && scope == _pendingScope) {
        _cacheUpdates.add(CacheUpdate(key, value: _overlaid(key, value), overlay: true));
      }
    }
  }

  CachedJson _overlaid(String key, CachedJson value) {
    if (!_pending.any((c) => !c.isConflict)) return value;
    return CachedJson(applyPending(key, value.data, _pending), value.savedAt);
  }

  /// Sofort senden; ohne Netz merken. true = gesendet, false = gemerkt.
  Future<bool> _sendOrQueue(PendingChange change) async => (await _sendOrQueueResult(change)).sent;

  /// Wie [_sendOrQueue], liefert die Serverantwort (null = gemerkt oder erst beim Nachsenden angekommen).
  Future<dynamic> _sendOrQueueJson(PendingChange change) async => (await _sendOrQueueResult(change)).json;

  Future<({bool sent, dynamic json})> _sendOrQueueResult(PendingChange change) async {
    final epoch = _epoch;
    await loadPending();
    if (epoch != _epoch) throw UnauthorizedException();
    if (_pending.any((c) => !c.isConflict)) {
      // Ältere Änderungen warten noch: hinten anstellen, damit die Reihenfolge stimmt
      await _setPending([..._pending, change]);
      await flushPending();
      final sent = !_pending.any((c) => c.id == change.id);
      return (sent: sent, json: null);
    }
    try {
      final json = await _send(change.method, change.path, body: change.body, headers: {'Idempotency-Key': change.id});
      return (sent: true, json: json);
    } on OfflineException {
      if (epoch != _epoch) throw UnauthorizedException();
      await _setPending([..._pending, change]);
      return (sent: false, json: null);
    }
  }

  /// Gemerkte Änderungen der Reihe nach senden. Ohne Netz oder bei Serverausfall: später erneut.
  /// Lehnt der Server eine Änderung ab, bleibt sie als Konflikt sichtbar, bis man sie verwirft.
  Future<void> flushPending() => _flushing ??= _flush().whenComplete(() => _flushing = null);

  Future<void> _flush() async {
    final epoch = _epoch;
    await loadPending();
    for (final change in List.of(_pending)) {
      if (epoch != _epoch) return;
      if (change.isConflict || !_pending.any((c) => c.id == change.id)) continue;
      try {
        await _send(change.method, change.path, body: change.body, headers: {'Idempotency-Key': change.id});
        if (epoch != _epoch) return;
        await _setPending([for (final c in _pending) if (c.id != change.id) c]);
      } on OfflineException {
        return;
      } on UnauthorizedException {
        return;
      } on ApiException catch (e) {
        if (epoch != _epoch) return;
        if (e.statusCode == 404 && change.kind == 'shopping_delete') {
          await _setPending([for (final c in _pending) if (c.id != change.id) c]); // schon weg = erledigt
          continue;
        }
        if (e.statusCode == 0 || e.statusCode == 401 || e.statusCode == 429 || e.statusCode >= 500) return;
        final reason = e.statusCode == 404 ? 'Gibt es nicht mehr – wurde woanders gelöscht' : e.message;
        await _setPending([for (final c in _pending) c.id == change.id ? c.withConflict(reason) : c]);
      }
    }
  }

  /// Gemerkte Änderung oder Konflikt verwerfen (wird nicht gesendet).
  Future<void> discardPending(String id) async {
    await loadPending();
    await _setPending([for (final c in _pending) if (c.id != id) c]);
  }

  Stream<CacheUpdate> get cacheUpdates => _cacheUpdates.stream;

  static Map<String, dynamic>? _claims(String token) {
    try {
      final parts = token.split('.');
      if (parts.length != 3) return null;
      return jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(parts[1])))) as Map<String, dynamic>;
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  Future<DateTime?> accessExpiresAt() async {
    final token = await store.accessToken();
    final exp = token == null ? null : _claims(token)?['exp'];
    return exp is num ? DateTime.fromMillisecondsSinceEpoch((exp * 1000).toInt()) : null;
  }

  Future<bool> _cacheAllowed() async {
    if (_ended) return false;
    final token = await store.accessToken();
    if (token == null) return false;
    final exp = _claims(token)?['exp'];
    return exp is! num || DateTime.now().millisecondsSinceEpoch < exp * 1000;
  }

  Future<String> _scope() async {
    final base = await store.baseUrl();
    final token = await store.accessToken();
    final identity = token == null ? null : _claims(token)?['sub'] ?? await store.refreshToken() ?? token;
    // Kein Token im Preference-Schlüssel; JWT-Payload dient nur der Trennung,
    // niemals als Berechtigungsnachweis. Abgelaufene Tokens sperren den Cache.
    return sha256.convert(utf8.encode('$base|$identity')).toString();
  }

  Future<ApiResult<T>?> cached<T>(String key, T Function(dynamic) parse) async {
    final epoch = _epoch;
    if (!await _cacheAllowed()) return null;
    await loadPending();
    final value = await cache.get('${await _scope()}:$key');
    if (epoch != _epoch || value == null) return null;
    return ApiResult(parse(_overlaid(key, value).data), fromCache: true,
      cachedAt: value.savedAt, refreshing: true);
  }

  ApiClient({
    http.Client? httpClient,
    required this.store,
    ResponseCache? cache,
    this.timeout = const Duration(seconds: 15),
  })  : _http = httpClient ?? http.Client(),
        cache = cache ?? ResponseCache();

  /// Meldet, wenn die Sitzung serverseitig endet (Refresh abgelehnt).
  Stream<void> get loggedOut => _loggedOut.stream;

  // ── Transport ──────────────────────────────────────────────────────────────

  Future<Uri> _uri(String path, {String? baseUrl}) async {
    final base = baseUrl ?? await store.baseUrl();
    if (base == null || base.isEmpty) {
      throw ApiException(0, 'Kein Server eingerichtet');
    }
    return Uri.parse('$base$path');
  }

  Future<http.Response> _raw(
    String method,
    String path, {
    Object? body,
    bool auth = true,
    String? baseUrl,
    String? accessToken,
    int? sessionEpoch,
    Map<String, String>? headers,
  }) async {
    final uri = await _uri(path, baseUrl: baseUrl);
    final request = http.Request(method, uri);
    if (headers != null) request.headers.addAll(headers);
    // Auch 307/308 dürfen eine Geräteaktion nicht erneut senden.
    if ((method == 'POST' && path == '/api/house/actions') ||
        (method != 'GET' && (path.startsWith('/api/tasks') || path.startsWith('/api/habitica')))) {
      request.followRedirects = false;
    }
    request.headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    if (auth) {
      final token = accessToken ?? await store.accessToken();
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
    }
    if (sessionEpoch != null && sessionEpoch != _epoch) throw UnauthorizedException();
    final streamed = await _http.send(request).timeout(timeout);
    return http.Response.fromStream(streamed);
  }

  /// http wandelt SocketException (Android) und Fetch-Fehler (Web) in ClientException um.
  static bool isNetworkError(Object e) => e is http.ClientException || e is TimeoutException;

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    bool auth = true,
    String? baseUrl,
    bool replayOn401 = true,
    Map<String, String>? headers,
  }) async {
    final epoch = _epoch;
    final base = baseUrl ?? await store.baseUrl();
    final token = auth ? await store.accessToken() : null;
    if (epoch != _epoch || (auth && (_ended || token == null))) throw UnauthorizedException();
    http.Response res;
    try {
      res = await _raw(method, path, body: body, auth: auth, baseUrl: base, accessToken: token, sessionEpoch: epoch,
          headers: headers);
      if (epoch != _epoch) throw UnauthorizedException();
      if (res.statusCode == 401 && auth) {
        bool refreshed;
        try {
          refreshed = await _refresh();
        } catch (e) {
          if (epoch != _epoch) throw UnauthorizedException();
          if (!isNetworkError(e)) rethrow;
          // Eine bereits bestätigte 401 ist kein Offline-Fallback.
          await _endSession();
          throw UnauthorizedException();
        }
        if (epoch != _epoch) throw UnauthorizedException();
        if (refreshed) {
          if (!replayOn401) {
            throw ApiException(401, 'Sitzung erneuert; Aktion nicht wiederholt. Zustand aktualisieren.');
          }
          if (epoch != _epoch) throw UnauthorizedException();
          res = await _raw(method, path, body: body, auth: auth, baseUrl: base, sessionEpoch: epoch, headers: headers);
          if (epoch != _epoch) throw UnauthorizedException();
        }
        if (res.statusCode == 401) {
          await _endSession();
          throw UnauthorizedException();
        }
      }
      if (res.statusCode == 403 && path == '/api/auth/me') await _endSession();
    } catch (e) {
      if (isNetworkError(e)) {
        if (method == 'GET') rethrow;
        throw OfflineException();
      }
      rethrow;
    }
    final json = _decode(res);
    if (auth && method != 'GET') await _invalidateMutation(path);
    return json;
  }

  Future<void> _invalidateMutation(String path) async {
    final prefixes = <String>[];
    if (path.startsWith('/api/tasks')) {
      prefixes.addAll(['tasks:', 'today']);
      if (path.endsWith('/caldav')) prefixes.add('events:');
    } else if (path.startsWith('/api/habitica')) {
      prefixes.addAll(['tasks:', 'today']);
    } else if (path.startsWith('/api/calendar/')) {
      prefixes.addAll(['events:', 'today']);
    } else if (path.startsWith('/api/shopping')) {
      prefixes.addAll(['shopping', 'today']);
    } else if (path.startsWith('/api/meals') || path.startsWith('/api/cookidoo/')) {
      prefixes.addAll(['meals:', 'today']);
      if (path.contains('shopping')) prefixes.add('shopping');
    } else if (path.startsWith('/api/house/')) {
      prefixes.add('today');
    } else if (path.startsWith('/api/reminders') || path.startsWith('/api/paperless/deadlines') ||
        path == '/api/me/notifications/read') {
      prefixes.add('today');
    }
    if (prefixes.isEmpty) return;
    final scope = await _scope();
    final keys = _versions.keys.where((key) => prefixes.any(key.startsWith)).toList();
    for (final key in keys) { _versions[key] = (_versions[key] ?? 0) + 1; }
    await cache.removeWhere((key) => key.startsWith('$scope:') &&
      prefixes.any(key.substring(scope.length + 1).startsWith));
    for (final key in keys) { _cacheUpdates.add(CacheUpdate(key, invalidated: true)); }
  }

  /// Gleichzeitige 401er teilen sich einen Refresh.
  Future<bool> _refresh() {
    return _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _doRefresh() async {
    final epoch = _epoch;
    final base = await store.baseUrl();
    final refresh = await store.refreshToken();
    if (epoch != _epoch || _ended) throw UnauthorizedException();
    if (refresh == null) return false;
    try {
      final res = await _raw('POST', '/api/auth/refresh',
          body: {'refresh_token': refresh}, auth: false, baseUrl: base, sessionEpoch: epoch);
      if (epoch != _epoch) throw UnauthorizedException();
      if (res.statusCode != 200) return false;
      final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      await _persistSession(() async {
        if (epoch != _epoch || _ended) throw UnauthorizedException();
        await store.saveTokens(
          access: data['access_token'] as String,
          refresh: data['refresh_token'] as String?,
        );
      });
      if (epoch != _epoch) throw UnauthorizedException();
      return true;
    } catch (e) {
      if (isNetworkError(e)) rethrow;
      return false;
    }
  }

  // Alle Token-Schreiber laufen hier durch, einschließlich geteilter Plattform-Writes.
  Future<void> _persistSession(Future<void> Function() write) {
    final result = _sessionWrites.then((_) => write());
    // Nur die Warteschlange erholt sich; der Aufrufer erhält den Speicherfehler.
    _sessionWrites = result.then((_) {}, onError: (Object error, StackTrace stack) {});
    return result;
  }

  int _invalidateSession() {
    _epoch++;
    _ended = true;
    _houseActionEntities.clear();
    _pending = const [];
    _pendingScope = null;
    _flushTimer?.cancel();
    _pendingChanges.add(const []);
    _nativeTaskLocks.clear();
    _nativeTaskUncertain.clear();
    _nativeTaskConfirmed.clear();
    clearHouseActionFailure();
    _reads.clear();
    _refreshing = null;
    _versions.clear();
    _cacheUpdates.add(CacheUpdate(null, error: UnauthorizedException()));
    _loggedOut.add(null);
    return _epoch;
  }

  Future<void> _endSession() {
    _invalidateSession();
    return _persistSession(() async {
      await store.clearTokens();
      await cache.clear();
    });
  }

  Future<void> setServer(String url) {
    _invalidateSession();
    return _persistSession(() async {
      await store.clearTokens();
      await cache.clear();
      await store.saveBaseUrl(url);
    });
  }

  static dynamic _decode(http.Response res) {
    final text = utf8.decode(res.bodyBytes);
    dynamic json;
    if (text.isNotEmpty) {
      try {
        json = jsonDecode(text);
      } catch (_) {
        json = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return json;

    // FastAPI: {"detail": "…"} oder {"detail": {"error": "…"}}; B2: {"error": "…"}
    final detail = json is Map ? json['detail'] : null;
    final errorMap = detail is Map ? detail : (json is Map ? json : const {});
    final code = errorMap['error'];
    if (res.statusCode == 409 && code == 'no_write_access') {
      throw WriteAccessException((errorMap['list'] as String?) ?? 'unbekannt');
    }
    if (res.statusCode == 409 && code == 'no_caldav_account') {
      throw NoCalDavAccountException();
    }
    final message = detail is String
        ? detail
        : (code is String ? code : 'Serverfehler (${res.statusCode})');
    throw ApiException(res.statusCode, message);
  }

  /// Explizite Aktualisierung: immer HTTP, gleichzeitige Leser teilen die Anfrage.
  Future<ApiResult<T>> _cachedGet<T>(
    String path,
    String cacheKey,
    T Function(dynamic json) parse,
  ) async {
    final epoch = _epoch;
    final scope = await _scope();
    if (epoch != _epoch || _ended) throw UnauthorizedException();
    final version = _versions.putIfAbsent(cacheKey, () => 0);
    final requestKey = '$epoch:$scope:$cacheKey:$version';
    final json = await (_reads[requestKey] ??= _fetchCached(path, cacheKey, scope, epoch, version)
        .whenComplete(() { _reads.remove(requestKey); }));
    await loadPending();
    return ApiResult(parse(_overlaid(cacheKey, json.value).data), fromCache: json.offline,
      cachedAt: json.value.savedAt, offline: json.offline, refreshError: json.error);
  }

  Future<({CachedJson value, bool offline, Object? error})> _fetchCached(
      String path, String key, String scope, int epoch, int version) async {
    bool valid() => epoch == _epoch && !_ended && version == _versions[key];
    final scopedKey = '$scope:$key';
    _cacheUpdates.add(CacheUpdate(key, refreshing: true));
    try {
      final json = await _send('GET', path);
      if (!valid()) throw UnauthorizedException();
      await cache.put(scopedKey, json, isCurrent: valid);
      if (!valid()) throw UnauthorizedException();
      final value = (await cache.get(scopedKey))!;
      if (!valid()) throw UnauthorizedException();
      await loadPending();
      _cacheUpdates.add(CacheUpdate(key, value: _overlaid(key, value)));
      // Wieder Netz: gemerkte Änderungen jetzt senden
      if (_pending.any((c) => !c.isConflict)) unawaited(flushPending());
      return (value: value, offline: false, error: null);
    } catch (e) {
      if (!valid()) rethrow;
      if (e is ApiException && (e.statusCode == 401 || e.statusCode == 403)) {
        await cache.removeWhere((k) => k == scopedKey);
        if (!valid()) rethrow;
      }
      _cacheUpdates.add(CacheUpdate(key, error: e));
      if (!isNetworkError(e)) rethrow;
      if (!await _cacheAllowed()) throw UnauthorizedException();
      final value = await cache.get(scopedKey);
      if (!valid()) throw UnauthorizedException();
      if (value == null) throw OfflineException();
      return (value: value, offline: true, error: e);
    }
  }

  static List<Map<String, dynamic>> _maps(dynamic json) =>
      json is List ? json.whereType<Map<String, dynamic>>().toList() : const [];

  // ── Server & Anmeldung ─────────────────────────────────────────────────────

  Future<HealthInfo> health({String? baseUrl}) async {
    final json = await _send('GET', '/api/health', auth: false, baseUrl: baseUrl);
    return HealthInfo.fromJson(json as Map<String, dynamic>);
  }

  Future<AppUser> login(String username, String password) => _authenticate(
      '/api/auth/login',
      {'username': username, 'password': password, 'client': 'app'});

  /// URL für Authentik. `client`: `app` (Rücksprung per familienhub://) oder `pwa` (Web-App, Rücksprung auf die Seite).
  Future<String> oidcStartUrl({String client = 'app'}) async {
    final epoch = _epoch;
    await _sessionWrites;
    if (epoch != _epoch) throw UnauthorizedException();
    final json = await _send('GET', '/api/auth/oidc/start?client=$client', auth: false);
    return (json as Map<String, dynamic>)['url'] as String;
  }

  Future<AppUser> exchangeOidcCode(String code) =>
      _authenticate('/api/auth/oidc/exchange', {'code': code});

  Future<AppUser> _authenticate(String path, Object body) async {
    // Anmeldung gehört ab ihrem Beginn zu genau einer Sitzung. Bereits
    // eingereihte Server-/Token-Writes müssen vor dem HTTP-Ziel fertig sein.
    final epoch = _invalidateSession();
    await _sessionWrites;
    if (epoch != _epoch) throw UnauthorizedException();
    final json = await _send('POST', path, body: body, auth: false)
        as Map<String, dynamic>;
    await _storeTokenResponse(json, epoch);
    return AppUser.fromJson(json['user'] as Map<String, dynamic>);
  }

  Future<void> _storeTokenResponse(Map<String, dynamic> json, int epoch) async {
    if (epoch != _epoch) throw UnauthorizedException();
    await _persistSession(() async {
      if (epoch != _epoch) throw UnauthorizedException();
      await store.clearTokens();
      await cache.clear();
      await store.saveTokens(
        access: json['access_token'] as String,
        refresh: json['refresh_token'] as String?,
      );
    });
    if (epoch != _epoch) throw UnauthorizedException();
    _ended = false;
    _cacheUpdates.add(const CacheUpdate(null, invalidated: true));
  }

  Future<AppUser> me() async =>
      AppUser.fromJson(await _send('GET', '/api/auth/me') as Map<String, dynamic>);

  Future<void> logout() async {
    final initiatingEpoch = _epoch;
    final base = await store.baseUrl();
    final token = await store.accessToken();
    if (initiatingEpoch != _epoch) return;
    final ending = _endSession();
    final logoutEpoch = _epoch;
    await ending;
    if (token == null || logoutEpoch != _epoch) return;
    try {
      await _raw('POST', '/api/auth/logout', baseUrl: base,
          accessToken: token, sessionEpoch: logoutEpoch);
    } catch (e) {
      if (!isNetworkError(e)) rethrow;
      // Lokale Abmeldung ist bereits wirksam; keine Wiederholung der Aktion.
    }
  }

  Future<List<Person>> people() async =>
      _maps(await _send('GET', '/api/auth/people')).map(Person.fromJson).toList();

  // ── Module (welche Bereiche der Server anbietet) ───────────────────────────

  Future<ApiResult<AppModules>> modules() => _cachedGet(
      '/api/modules', 'modules', (j) => AppModules.fromJson(j as Map<String, dynamic>));

  // ── Heute ──────────────────────────────────────────────────────────────────

  Future<ApiResult<TodayData>> today() => _cachedGet(
      '/api/today', 'today', (j) => TodayData.fromJson(j as Map<String, dynamic>));

  // Steuerfreigaben niemals im ResponseCache speichern oder daraus lesen.
  Future<SourceResult<HouseControl>> houseControls() async {
    try {
      return SourceResult.fromJson(await _send('GET', '/api/house/controls')
        as Map<String, dynamic>, HouseControl.fromJson);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return const SourceResult(status: SourceStatus.notConfigured);
      rethrow;
    }
  }

  /// Schaltet genau einmal. Liefert den von HA bestätigten neuen Zustand, falls HA ihn sofort meldet.
  Future<HouseControl?> houseAction(String entityId, String action, {int? brightness}) async {
    if (houseActionPendingFor(entityId)) throw ApiException(409, 'Diese Hausaktion läuft bereits.');
    final epoch = _epoch;
    _houseActionEntities[entityId] = epoch;
    _houseActionFailed = false;
    _houseActionChanges.add(null);
    try {
      final result = await _send('POST', '/api/house/actions', replayOn401: false, body: {
        'entity_id': entityId, 'action': action,
        if (brightness != null) 'brightness': brightness,
      });
      final control = result is Map<String, dynamic> ? result['control'] : null;
      if (control is! Map<String, dynamic>) return null;
      try {
        final confirmed = HouseControl.fromJson(control);
        return confirmed.entityId == entityId ? confirmed : null;
      } catch (_) {
        return null; // unlesbare Bestätigung: App liest den Zustand nach
      }
    } catch (_) {
      // Nur ein sicheres Ergebnisflag, keine privaten Fehlertexte über Remounts.
      if (epoch == _epoch) _houseActionFailed = true;
      rethrow;
    } finally {
      // Alte Sitzungsantworten dürfen eine neuere Aktionssperre nicht lösen.
      if (_houseActionEntities[entityId] == epoch) {
        _houseActionEntities.remove(entityId);
        _houseActionChanges.add(null);
      }
    }
  }

  // ── Aufgaben ───────────────────────────────────────────────────────────────

  Future<ApiResult<SourceResult<Task>>> tasks(TaskView view) => _cachedGet(
        '/api/tasks?provider=all&include_done=true&view=${view.apiName}',
        'tasks:${view.apiName}',
        (j) => SourceResult.fromJson(j as Map<String, dynamic>, Task.fromJson),
      );

  /// Liefert die angelegte Aufgabe, oder null, wenn sie ohne Netz gemerkt wurde.
  Future<Task?> createTask({
    required String title,
    String provider = 'nextcloud',
    String? account,
    int? assigneeId,
    DateTime? due,
    bool family = false,
    String? notes,
    String recurrence = 'none',
    List<int> rotation = const [],
    int? meId,
  }) async {
    final path = _taskPath('', provider, account);
    final body = {
      'title': title,
      if (notes != null && notes.isNotEmpty) 'notes': notes,
      if (due != null) 'due': _dateOnly(due),
      if (assigneeId != null) 'assignee_id': assigneeId,
      if (family) 'list': 'family',
      if (rotation.isNotEmpty) ...{
        'recurrence': recurrence,
        'rotation': rotation,
        'habitica': false,
      },
    };
    // Einfache Nextcloud-Aufgaben gehen auch offline; Haushaltsrotation und Habitica nicht.
    if (provider == 'habitica' || rotation.isNotEmpty) {
      final json = await _send('POST', path, replayOn401: false, body: body);
      return Task.fromJson(json as Map<String, dynamic>);
    }
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final mine = !family && (assigneeId == null || assigneeId == meId);
    final views = family ? ['family'] : mine ? ['mine'] : ['from_me'];
    if (mine && due != null && !DateTime(due.year, due.month, due.day).isAfter(today)) views.add('today');
    final change = PendingChange(
      id: PendingChange.newId(), kind: 'task_create', method: 'POST', path: path, body: body,
      label: '„$title“ angelegt', created: now,
      meta: {
        'views': views,
        'task': {
          'title': title, 'provider': provider, 'account': account ?? '', 'done': false,
          if (due != null) 'due': _dateOnly(due),
          if (assigneeId != null) 'assignee': assigneeId,
          if (family) 'list': {'name': 'Familie', 'kind': 'family'},
        },
      },
    );
    final result = await _sendOrQueueJson(change);
    return result == null ? null : Task.fromJson(result as Map<String, dynamic>);
  }


  static String _taskPath(String suffix, String provider, String? account) {
    final query = Uri(queryParameters: {
      'provider': provider, if (account != null && account.isNotEmpty) 'account': account,
    }).query;
    return '/api/tasks$suffix?$query';
  }

  Future<List<TaskProviderInfo>> taskProviders() async =>
    _maps((await _send('GET', '/api/tasks/providers'))['items']).map(TaskProviderInfo.fromJson).toList();

  Future<void> updateTask(Task task, {required String title, required String notes, DateTime? due, int? priority}) =>
    _send('PATCH', _taskPath('/${Uri.encodeComponent(task.uid)}', task.provider, task.account), replayOn401: false, body: {
      if (title != task.title) 'title': title,
      if (notes != task.notes) 'notes': notes,
      if (due != task.due) 'due': due == null ? null : _dateOnly(due),
      if (priority != task.priority) 'priority': priority,
    });

  /// true = erledigt gesendet, false = ohne Netz gemerkt. Habitica nie gemerkt (Punkte würden doppelt zählen).
  Future<bool> completeTask(String uid, {String provider = 'nextcloud', String? account, String? title}) async {
    if (provider == 'habitica') {
      await nativeTaskActionAndRefresh(Task(uid: uid, title: '', provider: provider, account: account ?? ''), 'up');
      return true;
    }
    return _sendOrQueue(PendingChange(
        id: PendingChange.newId(), kind: 'task_complete', method: 'POST',
        path: _taskPath('/${Uri.encodeComponent(uid)}/complete', provider, account), target: uid,
        label: '„${title ?? 'Aufgabe'}“ erledigt', created: DateTime.now()));
  }

  Future<void> deleteTask(String uid, {String provider = 'nextcloud', String? account}) async {
    final path = _taskPath('/${Uri.encodeComponent(uid)}', provider, account);
    if (provider == 'habitica') {
      await _nativeTaskOperation(account ?? '', () async {
        await _nativeTaskMutation('DELETE', path, {});
        await _nativeReadAfterWrite(account ?? '', targetIdentity: _nativeIdentity(uid, account ?? ''), expectedPresent: false);
      });
    } else {
      await _send('DELETE', path, replayOn401: false);
    }
  }

  bool nativeTaskBlocked(String account) =>
    _nativeTaskLocks[account] == _epoch || _nativeTaskUncertain[account] == _epoch || _nativeTaskConfirmed[account] == _epoch;

  String newNativeId() => _operationId();

  static String _operationId() {
    final random = Random.secure();
    final bytes = List.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final h = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  Future<T> _nativeTaskOperation<T>(String account, Future<T> Function() operation) async {
    if (account.isEmpty) throw ApiException(403, 'Kein eigenes Aufgabenkonto gewählt');
    if (nativeTaskBlocked(account)) throw ApiException(409, 'Aktion läuft oder Ergebnis unklar. Fachsystem prüfen; nicht wiederholen.');
    final epoch = _epoch;
    // ponytail: pro Konto serialisiert; per-account locks keep unrelated accounts independent.
    _nativeTaskLocks[account] = epoch;
    try {
      return await operation();
    } catch (e) {
      if (epoch == _epoch && (e is OfflineException || e is! ApiException || e.statusCode >= 500 || e.statusCode < 400)) {
        _nativeTaskUncertain[account] = epoch;
      }
      rethrow;
    } finally {
      if (_nativeTaskLocks[account] == epoch) _nativeTaskLocks.remove(account);
    }
  }

  Future<dynamic> _nativeTaskMutation(String method, String path, Map<String, dynamic> body) async {
    final operation = _operationId();
    return _send(method, method == 'DELETE' ? '$path&operation_id=$operation' : path, replayOn401: false,
      body: method == 'DELETE' ? null : {...body, 'operation_id': operation});
  }

  Future<Map<String, dynamic>> habiticaOptions() async =>
    await _send('GET', '/api/habitica/options') as Map<String, dynamic>;

  Future<Map<String, dynamic>> habiticaAccount() async =>
    await _send('GET', '/api/habitica/account') as Map<String, dynamic>;

  Future<void> saveHabiticaAccount(String userId, String key) =>
    _send('PUT', '/api/habitica/account', replayOn401: false, body: {'remote_user_id': userId, 'api_key': key});

  Future<SourceResult<Task>> habiticaTasks() async => SourceResult.fromJson(
    await _send('GET', '/api/habitica/tasks') as Map<String, dynamic>, Task.fromJson);

  Future<void> selectHabiticaTask(Task task, bool selected) => _send(
    'PUT', _taskPath('/${Uri.encodeComponent(task.uid)}/selection', task.provider, task.account), replayOn401: false,
    body: {'selected': selected});

  static String _nativeIdentity(String uid, String account) =>
      Task(uid: uid, title: '', provider: 'habitica', account: account).identity;

  Future<void> saveNativeTask(String account, Map<String, dynamic> native, {String? uid, String? expectedVersion}) async {
    await _nativeTaskOperation(account, () async {
      final response = await _nativeTaskMutation(
        uid == null ? 'POST' : 'PATCH', _taskPath(uid == null ? '' : '/${Uri.encodeComponent(uid)}', 'habitica', account),
        {'native': native, if (uid == null) 'title': native['text'] ?? '', if (uid != null) 'expected_version': expectedVersion});
      final targetUid = uid ?? (response is Map<String, dynamic> ? response['uid'] as String? : null);
      if (targetUid == null || targetUid.isEmpty) throw NativeTaskConfirmedReadException();
      await _nativeReadAfterWrite(account, targetIdentity: _nativeIdentity(targetUid, account), expectedPresent: true);
    });
  }

  Future<void> nativeTaskAction(Task task, String action, {String? itemId, Map<String, dynamic> fields = const {}}) =>
      _nativeTaskOperation(task.account, () async {
        await _nativeTaskMutation(
          'POST', _taskPath('/${Uri.encodeComponent(task.uid)}/actions', task.provider, task.account),
          {'action': action, if (itemId != null) 'item_id': itemId, 'fields': fields});
        await _nativeReadAfterWrite(task.account, targetIdentity: task.identity, expectedPresent: true);
      });

  Future<SourceResult<Task>> _nativeReadAfterWrite(String account, {String? targetIdentity, bool? expectedPresent}) async {
    final epoch = _epoch;
    try {
      final result = await habiticaTasks();
      final present = targetIdentity == null || result.items.any((task) => task.identity == targetIdentity);
      if (epoch != _epoch || !result.isOk || (expectedPresent != null && present != expectedPresent)) {
        throw NativeTaskConfirmedReadException();
      }
      return result;
    } catch (error) {
      if (epoch == _epoch) _nativeTaskConfirmed[account] = epoch;
      if (error is NativeTaskConfirmedReadException) rethrow;
      throw NativeTaskConfirmedReadException();
    }
  }

  Future<Task> nativeTaskActionAndRefresh(Task task, String action, {String? itemId, Map<String, dynamic> fields = const {}}) =>
      _nativeTaskOperation(task.account, () async {
        await _nativeTaskMutation(
          'POST', _taskPath('/${Uri.encodeComponent(task.uid)}/actions', task.provider, task.account),
          {'action': action, if (itemId != null) 'item_id': itemId, 'fields': fields});
        final result = await _nativeReadAfterWrite(task.account, targetIdentity: task.identity, expectedPresent: true);
        return result.items.firstWhere((current) => current.identity == task.identity);
      });

  Future<SourceResult<Task>> reconcileHabiticaTasks(String account) async {
    if (account.isEmpty) throw ApiException(403, 'Kein eigenes Aufgabenkonto gewählt');
    final epoch = _epoch;
    if (_nativeTaskLocks[account] == epoch) throw ApiException(409, 'Aktion läuft. Fachsystem prüfen; nicht wiederholen.');
    _nativeTaskLocks[account] = epoch;
    try {
      final result = await habiticaTasks();
      if (epoch == _epoch && result.isOk) {
        _nativeTaskConfirmed.remove(account);
        _nativeTaskUncertain.remove(account);
      }
      return result;
    } finally {
      if (_nativeTaskLocks[account] == epoch) _nativeTaskLocks.remove(account);
    }
  }

  Future<CalDavAccountInfo?> caldavAccount() async {
    try {
      return CalDavAccountInfo.fromJson(
          await _send('GET', '/api/tasks/me/caldav') as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  Future<void> saveCaldavAccount(String url, String username, String password) =>
      _send('PUT', '/api/tasks/me/caldav',
          body: {'url': url, 'username': username, 'password': password});

  /// Alle VTODO-Listen des Kontos, ergänzt um die gespeicherte Zuordnung.
  Future<SourceResult<TaskListInfo>> taskLists() async {
    final available = SourceResult.fromJson(
        await _send('GET', '/api/tasks/lists') as Map<String, dynamic>,
        TaskListInfo.fromJson,
        key: 'lists');
    final config = {
      for (final c in _maps(await _send('GET', '/api/tasks/me/task-lists')).map(TaskListInfo.fromJson))
        c.caldavUrl: c
    };
    return SourceResult(
      status: available.status,
      error: available.error,
      items: [
        for (final l in available.items)
          TaskListInfo(
            caldavUrl: l.caldavUrl,
            displayName: l.displayName,
            kind: config[l.caldavUrl]?.kind,
            ownerUserId: config[l.caldavUrl]?.ownerUserId,
          ),
      ],
    );
  }

  Future<void> saveTaskLists(List<TaskListInfo> lists) => _send('PUT', '/api/tasks/me/task-lists',
      body: [
        for (final l in lists.where((l) => l.kind != null))
          {'caldav_url': l.caldavUrl, 'kind': l.kind, 'owner_user_id': l.ownerUserId},
      ]);

  // ── Einkauf ────────────────────────────────────────────────────────────────

  Future<ApiResult<ShoppingData>> shopping() => _cachedGet('/api/shopping', 'shopping',
      (j) => ShoppingData.fromJson(j as Map<String, dynamic>));

  /// Zuletzt abgehakte Artikel (Vorschläge); leer, wenn HA nicht erreichbar.
  Future<List<String>> shoppingRecent() async {
    final json = await _send('GET', '/api/shopping/recent');
    return json is List ? json.whereType<String>().toList() : const [];
  }

  // Einkauf geht auch ohne Netz: true = gesendet, false = gemerkt (wird später gesendet).

  Future<bool> addShoppingItem(String item) => _sendOrQueue(PendingChange(
      id: PendingChange.newId(), kind: 'shopping_add', method: 'POST', path: '/api/shopping',
      body: {'item': item}, label: '„$item“ auf die Einkaufsliste', created: DateTime.now()));

  Future<bool> setShoppingDone(String uid, bool done, {String? name}) => _sendOrQueue(PendingChange(
      id: PendingChange.newId(), kind: 'shopping_done', method: 'PATCH',
      path: '/api/shopping/${Uri.encodeComponent(uid)}', body: {'done': done}, target: uid,
      label: '„${name ?? 'Artikel'}“ ${done ? 'abgehakt' : 'wieder offen'}', created: DateTime.now()));

  Future<bool> deleteShoppingItem(String uid, {String? name}) => _sendOrQueue(PendingChange(
      id: PendingChange.newId(), kind: 'shopping_delete', method: 'DELETE',
      path: '/api/shopping/${Uri.encodeComponent(uid)}', target: uid,
      label: '„${name ?? 'Artikel'}“ gelöscht', created: DateTime.now()));

  // ── Essen ──────────────────────────────────────────────────────────────────

  Future<ApiResult<MealWeek>> meals(String isoWeek) => _cachedGet(
      '/api/meals?week=$isoWeek', 'meals:$isoWeek', (j) => MealWeek.fromJson(j as Map<String, dynamic>));

  Future<void> addMeal(DateTime day, String title) => _send('POST', '/api/meals/plan',
      body: {'date': _dateOnly(day), 'custom_title': title, 'meal_type': 'dinner'});

  /// Nur Hub-Einträge; Cookidoo lehnt der Server mit 403 ab.
  Future<void> deleteMeal(int id) => _send('DELETE', '/api/meals/$id');

  /// Zutaten der geplanten Hub-Rezepte auf die Einkaufsliste. Liefert die Meldung des Servers.
  Future<String> mealsToShoppingList() async {
    final json = await _send('POST', '/api/meals/shopping-list') as Map<String, dynamic>;
    return (json['message'] as String?) ?? '${json['added'] ?? 0} Zutaten hinzugefügt';
  }

  // ── Termine ────────────────────────────────────────────────────────────────

  Future<ApiResult<List<CalendarEvent>>> events({int days = 14}) => _cachedGet(
      '/api/calendar/events?days=$days', 'events:$days', (j) => _maps(j).map(CalendarEvent.fromJson).toList());

  Future<void> createEvent({
    required String title,
    required DateTime start,
    required DateTime end,
    required bool allDay,
  }) =>
      _send('POST', '/api/calendar/events', body: {
        'title': title,
        'start': allDay ? _dateOnly(start) : _localIso(start),
        'end': allDay ? _dateOnly(end) : _localIso(end),
        'all_day': allDay,
      });

  // ── Erinnerungen ───────────────────────────────────────────────────────────

  Future<List<Reminder>> reminders() async =>
      _maps(await _send('GET', '/api/reminders')).map(Reminder.fromJson).toList();

  Future<void> createReminder(String title, DateTime? dueAt,
          {bool forFamily = false, String recurrence = 'none', bool onArrival = false}) =>
      _send('POST', '/api/reminders', body: {
        'title': title,
        if (dueAt != null && !onArrival) 'due_at': _localIso(dueAt),
        'for_family': forFamily,
        'recurrence': recurrence,
        'fire_on': onArrival ? 'arrival' : 'time',
      });

  Future<void> snoozeReminder(int id, int minutes) =>
      _send('POST', '/api/reminders/$id/snooze', body: {'minutes': minutes});

  // ── Mitteilungen ───────────────────────────────────────────────────────────

  Future<NotificationInbox> notifications({int limit = 100}) async => NotificationInbox.fromJson(
      await _send('GET', '/api/me/notifications?limit=$limit') as Map<String, dynamic>);

  /// Ohne [ids]: alle als gelesen markieren.
  Future<void> markNotificationsRead([List<int>? ids]) =>
      _send('POST', '/api/me/notifications/read', body: {if (ids != null) 'ids': ids});

  Future<List<ServiceKeyInfo>> serviceKeys() async =>
      _maps(await _send('GET', '/api/admin/service-keys')).map(ServiceKeyInfo.fromJson).toList();

  Future<ServiceKeyInfo> createServiceKey(String name) async => ServiceKeyInfo.fromJson(
      await _send('POST', '/api/admin/service-keys', body: {'name': name}) as Map<String, dynamic>);

  Future<void> revokeServiceKey(int id) => _send('DELETE', '/api/admin/service-keys/$id');

  Future<void> completeReminder(int id) =>
      _send('PATCH', '/api/reminders/$id', body: {'completed': true});

  // ── Zugänge für Assistenten ────────────────────────────────────────────────

  Future<List<ApiTokenInfo>> apiTokens() async =>
      _maps(await _send('GET', '/api/auth/api-tokens')).map(ApiTokenInfo.fromJson).toList();

  /// Liefert den Schlüssel inklusive Klartext (nur dieses eine Mal).
  Future<ApiTokenInfo> createApiToken(String name) async => ApiTokenInfo.fromJson(
      await _send('POST', '/api/auth/api-tokens', body: {'name': name}) as Map<String, dynamic>);

  Future<void> revokeApiToken(int id) => _send('DELETE', '/api/auth/api-tokens/$id');

  // ── Bücher (Shelfarr) ──────────────────────────────────────────────────────

  // ── Profil ─────────────────────────────────────────────────────────────────

  /// Anzeigename (leer = zurück auf den vollen Namen) und Avatar-Farbe (#RRGGBB oder null).
  Future<AppUser> updateProfile({String? displayName, String? avatarColor, bool clearColor = false}) async =>
      AppUser.fromJson(await _send('PATCH', '/api/me/profile', body: {
        if (displayName != null) 'display_name': displayName,
        if (avatarColor != null || clearColor) 'avatar_color': avatarColor,
      }) as Map<String, dynamic>);

  /// Profilbild (JPEG/PNG/WebP, höchstens 512 KB; vorher in der App verkleinern).
  Future<AppUser> uploadAvatar(Uint8List bytes) async =>
      AppUser.fromJson(await _send('PUT', '/api/me/avatar', body: {'image': base64Encode(bytes)}) as Map<String, dynamic>);

  Future<AppUser> deleteAvatar() async => AppUser.fromJson(await _send('DELETE', '/api/me/avatar') as Map<String, dynamic>);

  static final _avatarCache = <String, Uint8List>{};

  /// Profilbild laden (angemeldet). Die Version steckt in der URL, daher genügt ein Speicher-Cache.
  Future<Uint8List?> avatarBytes(String url) async {
    final cached = _avatarCache[url];
    if (cached != null) return cached;
    try {
      final res = await _raw('GET', url);
      if (res.statusCode != 200 || !(res.headers['content-type'] ?? '').startsWith('image/')) return null;
      return _avatarCache[url] = res.bodyBytes;
    } catch (_) {
      return null; // offline: Initialen statt Bild
    }
  }

  // ── Dokumente (Paperless-Plugin) ───────────────────────────────────────────

  Future<Map<String, dynamic>> paperlessAccount() async =>
      await _send('GET', '/api/paperless/account') as Map<String, dynamic>;

  /// Eigenes Paperless-API-Token hinterlegen (der Hub prüft es bei Paperless).
  Future<Map<String, dynamic>> connectPaperless(String token) async =>
      await _send('PUT', '/api/paperless/account', body: {'token': token}) as Map<String, dynamic>;

  Future<void> disconnectPaperless() => _send('DELETE', '/api/paperless/account');

  Future<PaperlessList> paperlessRecent() async =>
      PaperlessList.fromJson(await _send('GET', '/api/paperless/recent') as Map<String, dynamic>);

  Future<PaperlessList> paperlessSearch(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return PaperlessList.fromJson(await _send('GET', '/api/paperless/search?$q') as Map<String, dynamic>);
  }

  Future<PaperlessList> paperlessDeadlines() async =>
      PaperlessList.fromJson(await _send('GET', '/api/paperless/deadlines') as Map<String, dynamic>);

  /// Frist als eigene Erinnerung (am Fristtag 9 Uhr). true = neu angelegt, false = gab es schon.
  Future<bool> paperlessRemind(int id) async =>
      ((await _send('POST', '/api/paperless/deadlines/$id/remind')) as Map<String, dynamic>)['created'] == true;

  /// Vorschaubild über den Hub (angemeldet), zwischengespeichert wie Profilbilder.
  Future<Uint8List?> paperlessThumb(String path) => avatarBytes(path);

  // ── Verwaltung (nur Admins) ────────────────────────────────────────────────

  Future<AdminOverview> adminOverview() async =>
      AdminOverview.fromJson(await _send('GET', '/api/admin/overview') as Map<String, dynamic>);

  Future<List<AdminUser>> adminUsers() async => ((await _send('GET', '/api/admin/users')) as List)
      .whereType<Map<String, dynamic>>()
      .map(AdminUser.fromJson)
      .toList();

  Future<void> updateAdminUser(int id, {String? role, bool? active}) => _send('PATCH', '/api/auth/users/$id', body: {
        if (role != null) 'role': role,
        if (active != null) 'is_active': active,
      });

  Future<void> createAdminUser({
    required String username,
    required String email,
    required String password,
    String? fullName,
    String role = 'partner',
  }) =>
      _send('POST', '/api/auth/users', body: {
        'username': username,
        'email': email,
        'password': password,
        if (fullName != null && fullName.isNotEmpty) 'full_name': fullName,
        'role': role,
      });

  Future<HouseChoices> houseChoices() async =>
      HouseChoices.fromJson(await _send('GET', '/api/admin/house/entities') as Map<String, dynamic>);

  Future<void> saveHouseSelection({required List<String> display, required List<String> control}) =>
      saveAdminSettings({'HA_HOUSE_ENTITIES': display.join(','), 'HA_HOUSE_WRITE_ENTITIES': control.join(',')});

  Future<List<LogEntry>> adminLog() async => (((await _send('GET', '/api/admin/log')) as Map)['items'] as List)
      .whereType<Map<String, dynamic>>()
      .map(LogEntry.fromJson)
      .toList();

  // ── Filme & Serien (Seerr) ─────────────────────────────────────────────────

  Future<MediaList<MediaItem>> searchMedia(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return MediaList.fromJson(await _send('GET', '/api/media/search?$q') as Map<String, dynamic>, MediaItem.fromJson);
  }

  Future<MediaList<MediaRequestItem>> mediaRequests() async =>
      MediaList.fromJson(await _send('GET', '/api/media/requests') as Map<String, dynamic>, MediaRequestItem.fromJson);

  /// Wunsch anlegen; liefert den Stand als Text (z. B. „Wartet auf Freigabe“).
  Future<String> requestMedia(MediaItem item) async {
    final json = await _send('POST', '/api/media/requests',
        body: {'media_type': item.kind.api, 'tmdb_id': item.tmdbId}) as Map<String, dynamic>;
    return (json['status_label'] as String?) ?? 'Gewünscht';
  }

  Future<void> cancelMediaRequest(int id) => _send('DELETE', '/api/media/requests/$id');

  // ── Darstellung ────────────────────────────────────────────────────────────

  Future<List<ThemeSpec>> themes() async {
    final json = await _send('GET', '/api/themes') as Map<String, dynamic>;
    return _maps(json['items']).map(ThemeSpec.fromJson).toList();
  }

  /// Nur Admins: Theme aus GitHub installieren.
  Future<ThemeSpec> installTheme(String url) async =>
      ThemeSpec.fromJson(await _send('POST', '/api/themes', body: {'url': url}) as Map<String, dynamic>);

  Future<void> deleteTheme(String id) => _send('DELETE', '/api/themes/${Uri.encodeComponent(id)}');

  // ── Admin: Plugins & Zugänge ───────────────────────────────────────────────

  Future<List<AdminPlugin>> adminPlugins() async =>
      _maps(await _send('GET', '/api/admin/settings')).map(AdminPlugin.fromJson).toList();

  /// Leere Geheimnisse lässt das Backend unverändert.
  Future<void> saveAdminSettings(Map<String, String> values) =>
      _send('PUT', '/api/admin/settings', body: {'values': values});

  Future<AdminPlugin> setPluginEnabled(String id, bool enabled) async => AdminPlugin.fromJson(
      await _send('PUT', '/api/admin/plugins/${Uri.encodeComponent(id)}', body: {'enabled': enabled})
          as Map<String, dynamic>);

  // ── Cookidoo (Plugin) ──────────────────────────────────────────────────────

  Future<SourceResult<CookidooRecipe>> searchCookidoo(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return SourceResult.fromJson(
        await _send('GET', '/api/cookidoo/search?$q') as Map<String, dynamic>, CookidooRecipe.fromJson);
  }

  Future<void> planCookidoo(DateTime day, String recipeId) =>
      _send('POST', '/api/cookidoo/plan', body: {'date': _dateOnly(day), 'recipe_id': recipeId});

  Future<void> unplanCookidoo(DateTime day, String recipeId) =>
      _send('DELETE', '/api/cookidoo/plan/${_dateOnly(day)}/${Uri.encodeComponent(recipeId)}');

  /// Zutaten auf die Cookidoo-Einkaufsliste; liefert die Anzahl.
  Future<int> cookidooToShopping(List<String> recipeIds) async {
    final json = await _send('POST', '/api/cookidoo/shopping', body: {'recipe_ids': recipeIds}) as Map<String, dynamic>;
    return parseInt(json['added']) ?? 0;
  }

  Future<SourceResult<BookResult>> searchBooks(String query, {BookKind? kind}) async {
    final q = Uri(queryParameters: {'q': query, if (kind != null) 'book_type': kind.api}).query;
    return SourceResult.fromJson(
        await _send('GET', '/api/books/search?$q') as Map<String, dynamic>, BookResult.fromJson);
  }

  Future<ApiResult<SourceResult<BookRequest>>> bookRequests() => _cachedGet('/api/books/requests', 'books',
      (j) => SourceResult.fromJson(j as Map<String, dynamic>, BookRequest.fromJson));

  /// Wunsch anlegen; liefert Hinweise von Shelfarr (z. B. „wird im Hintergrund angelegt“).
  Future<List<String>> requestBook(BookResult book, BookKind kind) async {
    final json = await _send('POST', '/api/books/requests', body: {
      'work_id': book.workId,
      'book_type': kind.api,
      'title': book.title,
      if (book.author != null) 'author': book.author,
      if (book.coverUrl != null) 'cover_url': book.coverUrl,
      if (book.year != null) 'year': book.year,
    }) as Map<String, dynamic>;
    return [
      if (json['queued'] == true) 'Wird im Hintergrund angelegt',
      ...((json['warnings'] as List?) ?? const []).map((w) => '$w'),
    ];
  }

  Future<void> cancelBookRequest(int id) => _send('DELETE', '/api/books/requests/$id');

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

  // ── Hilfen ─────────────────────────────────────────────────────────────────

  static String _two(int v) => v.toString().padLeft(2, '0');
  static String _dateOnly(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

  /// Lokale Zeit mit Offset, damit der Server die Zeitzone kennt.
  static String _localIso(DateTime d) {
    final local = d.toLocal();
    final offset = local.timeZoneOffset;
    final sign = offset.isNegative ? '-' : '+';
    final h = _two(offset.inHours.abs());
    final m = _two(offset.inMinutes.abs() % 60);
    return '${_dateOnly(local)}T${_two(local.hour)}:${_two(local.minute)}:00$sign$h:$m';
  }
}
