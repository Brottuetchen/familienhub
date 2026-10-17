import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/common.dart';
import '../services/api_client.dart';
import '../services/api_exceptions.dart';
import '../services/cache.dart';

/// Bindet den vorhandenen Lesecache an Riverpod, ohne Lade-Reset beim Refresh.
class CachedRead<T> extends StateNotifier<AsyncValue<ApiResult<T>>> {
  final ApiClient api;
  final String key;
  final T Function(dynamic) parse;
  final Future<ApiResult<T>> Function(ApiClient) load;
  late final StreamSubscription<CacheUpdate> _subscription;
  late final Future<ApiResult<T>> ready;
  int _generation = 0;
  Timer? _expiry;

  void _show(ApiResult<T> value) {
    state = AsyncData(value);
    _armExpiry().ignore();
  }

  Future<void> _armExpiry() async {
    final generation = _generation;
    final expiresAt = await api.accessExpiresAt();
    if (!mounted || generation != _generation) return;
    _expiry?.cancel();
    if (expiresAt == null) return;
    _expiry = Timer(expiresAt.difference(DateTime.now()), () {
      _generation++;
      state = const AsyncLoading();
      refresh().ignore();
    });
  }

  CachedRead(this.api, this.key, this.parse, this.load)
      : super(const AsyncLoading()) {
    _subscription = api.cacheUpdates.listen(_update);
    ready = _initialize();
    // Der Zustand trägt den Fehler; Widget-Leser müssen kein Future abonnieren.
    ready.ignore();
  }

  Future<ApiResult<T>> _initialize() async {
    final generation = _generation;
    try {
      final value = await api.cached(key, parse);
      if (!mounted || generation != _generation) throw UnauthorizedException();
      if (value == null) return await refresh();
      _show(value);
      refresh().ignore();
      return value;
    } catch (e, s) {
      if (mounted && generation == _generation) _error(e, s);
      rethrow;
    }
  }

  Future<ApiResult<T>> refresh() async {
    final generation = _generation;
    try {
      final result = await load(api);
      if (mounted && generation == _generation) _show(result);
      return result;
    } catch (e, s) {
      if (mounted && generation == _generation) _error(e, s);
      rethrow;
    }
  }

  void _error(Object error, StackTrace stack) {
    if (!mounted) return;
    final previous = state.valueOrNull;
    final denied = error is ApiException &&
        (error.statusCode == 401 || error.statusCode == 403);
    state = previous == null || denied
        ? AsyncError(error, stack)
        : AsyncData(previous.withStatus(
            offline:
                ApiClient.isNetworkError(error) || error is OfflineException,
            error: error));
  }

  void _update(CacheUpdate update) {
    if (update.key == null) {
      _generation++;
      _expiry?.cancel();
      // Absichtlich OHNE vorherige Nutzerdaten, auch ohne übergeordneten Login-Router.
      state = update.invalidated
          ? const AsyncLoading()
          : AsyncError(
              update.error ?? UnauthorizedException(), StackTrace.current);
      if (update.invalidated) {
        _initialize().ignore();
      }
      return;
    }
    if (update.key != key) return;
    if (update.invalidated) {
      _generation++;
      refresh().ignore();
    } else if (update.value case final value? when update.overlay) {
      final previous = state.valueOrNull;
      final data = parse(value.data);
      state = AsyncData(previous == null
          ? ApiResult(data, cachedAt: value.savedAt)
          : ApiResult(data, fromCache: previous.fromCache, cachedAt: previous.cachedAt, refreshing: previous.refreshing,
              offline: previous.offline, refreshError: previous.refreshError));
    } else if (update.value case final value?) {
      _show(ApiResult(parse(value.data), cachedAt: value.savedAt));
    } else if (update.error case final error?) {
      _error(error, StackTrace.current);
    } else if (state.valueOrNull case final value?) {
      state = AsyncData(value.withStatus(refreshing: update.refreshing));
    }
  }

  @override
  void dispose() {
    _generation++;
    _expiry?.cancel();
    _subscription.cancel();
    super.dispose();
  }
}
