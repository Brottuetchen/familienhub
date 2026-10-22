import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/account.dart';
import '../models/admin.dart';
import '../models/backup.dart';
import '../models/birthday.dart';
import '../models/books.dart';
import '../models/calendar_event.dart';
import '../models/common.dart';
import '../models/documents.dart';
import '../models/media.dart';
import '../models/meals.dart';
import '../models/modules.dart';
import '../models/plugin_install.dart';
import '../models/store.dart';
import '../models/pending.dart';
import '../models/list_template.dart';
import '../models/shopping.dart';
import '../models/themes.dart';
import '../models/task.dart';
import '../models/today.dart';
import '../models/timetable.dart';
import '../models/today_layout.dart';
import '../models/plugin_card.dart';
import '../models/stars.dart';
import 'offline_queue.dart';
import 'api_exceptions.dart';
import '../l10n/l10n.dart';
import 'app_info.dart';
import 'cache.dart';
import 'session_store.dart';

part 'api_today.dart';
part 'api_timetable.dart';
part 'api_tasks.dart';
part 'api_shopping.dart';
part 'api_lists.dart';
part 'api_meals.dart';
part 'api_calendar.dart';
part 'api_family.dart';
part 'api_notifications.dart';
part 'api_profile.dart';
part 'api_library.dart';
part 'api_admin.dart';

List<Map<String, dynamic>> _maps(dynamic json) =>
    json is List ? json.whereType<Map<String, dynamic>>().toList() : const [];

String _two(int v) => v.toString().padLeft(2, '0');
String _dateOnly(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

/// Lokale Zeit mit Offset, damit der Server die Zeitzone kennt.
String _localIso(DateTime d) {
  final local = d.toLocal();
  final offset = local.timeZoneOffset;
  final sign = offset.isNegative ? '-' : '+';
  final h = _two(offset.inHours.abs());
  final m = _two(offset.inMinutes.abs() % 60);
  return '${_dateOnly(local)}T${_two(local.hour)}:${_two(local.minute)}:00$sign$h:$m';
}


/// Einzige Stelle, die mit dem Familienhub-Backend spricht.
///
/// Domain methods live in the part files next to this one, one mixin per area,
/// applied by [ApiClient]. Transport, the session and sign-in stay on [ApiClientBase].
///
/// - Bearer-Token aus dem [SessionStore], bei 401 genau ein Refresh-Versuch.
/// - GETs mit Cache-Schlüssel landen im [ResponseCache] und kommen ohne Netz
///   von dort ([ApiResult.fromCache]).
/// - Schreibende Anfragen ohne Netz werfen [OfflineException].
class ApiClientBase {
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
  /// Session cache for hub images (profile and plugin photos). See [ProfileApi].
  final _imageCache = <String, Uint8List>{};
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

  /// How long a change waits for the queue ahead of it before the UI moves on.
  static const flushGrace = Duration(milliseconds: 400);

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
      // Older changes are still waiting: send them, but never keep the screen waiting for a slow server
      // longer than `flushGrace`; the rest drains in the background and the change shows as saved meanwhile.
      final settled = flushPending().then((_) {}, onError: (Object _) {});
      await Future.any([settled, Future<void>.delayed(flushGrace)]);
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
        final reason = e.statusCode == 404 ? l10n.goneElsewhere : e.message;
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

  ApiClientBase({
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
      throw ApiException(0, l10n.noServer);
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
    Duration? timeout,
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
    request.headers['Accept-Language'] = appLanguage; // Server-Meldungen in der Sprache der App
    request.headers['X-App-Language'] = appLanguage; // wins over the browser's Accept-Language (web app)
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    if (auth) {
      final token = accessToken ?? await store.accessToken();
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
    }
    if (sessionEpoch != null && sessionEpoch != _epoch) throw UnauthorizedException();
    final streamed = await _http.send(request).timeout(timeout ?? this.timeout);
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
    Duration? timeout,
  }) async {
    final epoch = _epoch;
    final base = baseUrl ?? await store.baseUrl();
    final token = auth ? await store.accessToken() : null;
    if (epoch != _epoch || (auth && (_ended || token == null))) throw UnauthorizedException();
    http.Response res;
    try {
      res = await _raw(method, path, body: body, auth: auth, baseUrl: base, accessToken: token, sessionEpoch: epoch,
          headers: headers, timeout: timeout);
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
            throw ApiException(401, l10n.sessionRenewed);
          }
          if (epoch != _epoch) throw UnauthorizedException();
          res = await _raw(method, path, body: body, auth: auth, baseUrl: base, sessionEpoch: epoch, headers: headers,
              timeout: timeout);
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
    if (path.startsWith('/api/stars')) {
      prefixes.addAll(['stars', 'tasks:']);
    } else if (path.startsWith('/api/tasks')) {
      prefixes.addAll(['tasks:', 'today', 'stars']);
      if (path.endsWith('/caldav')) prefixes.add('events:');
    } else if (path.startsWith('/api/habitica')) {
      prefixes.addAll(['tasks:', 'today']);
    } else if (path.startsWith('/api/calendar/')) {
      prefixes.addAll(['events:', 'today']);
    } else if (path.startsWith('/api/shopping')) {
      prefixes.addAll(['shopping', 'today']);
    } else if (path.startsWith('/api/templates/') && path.contains('/apply/')) {
      prefixes.addAll(path.endsWith('/shopping') ? ['shopping', 'today'] : ['tasks:', 'today']);
    } else if (path.startsWith('/api/meals') || path.startsWith('/api/cookidoo/')) {
      prefixes.addAll(['meals:', 'today']);
      if (path.contains('shopping')) prefixes.add('shopping');
    } else if (path.startsWith('/api/birthdays')) {
      prefixes.addAll(['events:', 'today']);
    } else if (path.startsWith('/api/me/today-layout') || path.startsWith('/api/admin/today-layout')) {
      prefixes.add('layout:today');
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
        : (code is String ? code : l10n.serverError(res.statusCode));
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


  // ── Server & Anmeldung ─────────────────────────────────────────────────────

  Future<HealthInfo> health({String? baseUrl}) async {
    final json = await _send('GET', '/api/health', auth: false, baseUrl: baseUrl);
    return HealthInfo.fromJson(json as Map<String, dynamic>);
  }

  Future<AppUser> login(String username, String password) => _authenticate(
      '/api/auth/login',
      {'username': username, 'password': password, 'client': 'app'});

  /// URL für Authentik. `client`: `app` (Rücksprung per familienhub://) oder `pwa` (Web-App, Rücksprung auf die Seite).
  ///
  /// PKCE-Bindung: Die App merkt sich ein zufälliges Geheimnis und schickt nur dessen SHA-256 mit. Den
  /// Rücksprung-Code kann danach nur einlösen, wer das Geheimnis kennt – eine fremde App, die
  /// `familienhub://` abfängt, nicht.
  Future<String> oidcStartUrl({String client = 'app'}) async {
    final epoch = _epoch;
    await _sessionWrites;
    if (epoch != _epoch) throw UnauthorizedException();
    final verifier = _newVerifier();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_oidcVerifierKey, verifier); // übersteht, dass die App im Browser beendet wird
    final challenge = base64Url.encode(sha256.convert(utf8.encode(verifier)).bytes).replaceAll('=', '');
    final json = await _send('GET', '/api/auth/oidc/start?client=$client&challenge=$challenge', auth: false);
    return (json as Map<String, dynamic>)['url'] as String;
  }

  static const _oidcVerifierKey = 'oidc_verifier';

  static String _newVerifier() {
    final r = Random.secure();
    return base64Url.encode(List<int>.generate(48, (_) => r.nextInt(256))).replaceAll('=', '');
  }

  Future<AppUser> exchangeOidcCode(String code) async {
    final prefs = await SharedPreferences.getInstance();
    final verifier = prefs.getString(_oidcVerifierKey);
    await prefs.remove(_oidcVerifierKey); // nur einmal verwendbar
    return _authenticate('/api/auth/oidc/exchange', {'code': code, if (verifier != null) 'verifier': verifier});
  }

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

}

/// What the app talks to. [ApiClientBase] plus one mixin per area.
class ApiClient extends ApiClientBase
    with
        TodayApi,
        TimetableApi,
        TasksApi,
        ShoppingApi,
        ListsApi,
        MealsApi,
        CalendarApi,
        FamilyApi,
        NotificationsApi,
        ProfileApi,
        LibraryApi,
        AdminApi {
  ApiClient({
    super.httpClient,
    required super.store,
    super.cache,
    super.timeout,
  });

  static const flushGrace = ApiClientBase.flushGrace;
  static bool isNetworkError(Object e) => ApiClientBase.isNetworkError(e);
}
