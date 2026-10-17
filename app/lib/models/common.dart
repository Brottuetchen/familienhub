/// Status einer Quelle nach Backend-Regel B2: `{status, error, items}`.
enum SourceStatus { ok, unavailable, notConfigured }

SourceStatus parseSourceStatus(Object? raw) => switch (raw) {
      'ok' => SourceStatus.ok,
      'not_configured' => SourceStatus.notConfigured,
      _ => SourceStatus.unavailable,
    };

/// Eine Liste aus einer Quelle, die ausfallen darf, ohne die App zu stören.
class SourceResult<T> {
  final SourceStatus status;
  final String? error;
  final List<T> items;

  const SourceResult({required this.status, this.error, this.items = const []});

  bool get isOk => status == SourceStatus.ok;

  factory SourceResult.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) item, {
    String key = 'items',
  }) {
    final raw = json[key];
    return SourceResult(
      status: parseSourceStatus(json['status']),
      error: json['error'] as String?,
      items: raw is List
          ? raw.whereType<Map<String, dynamic>>().map(item).toList()
          : <T>[],
    );
  }
}

/// Antwort mit Herkunft: frisch vom Server oder aus dem Offline-Cache.
class ApiResult<T> {
  final T data;
  final bool fromCache;
  final DateTime? cachedAt;
  final bool refreshing;
  final bool offline;
  final Object? refreshError;

  const ApiResult(this.data, {this.fromCache = false, this.cachedAt,
    this.refreshing = false, this.offline = false, this.refreshError});

  ApiResult<T> withStatus({bool refreshing = false, bool offline = false, Object? error}) =>
      ApiResult(data, fromCache: fromCache, cachedAt: cachedAt,
        refreshing: refreshing, offline: offline, refreshError: error);
}

DateTime? parseDate(Object? raw) =>
    raw is String && raw.isNotEmpty ? DateTime.tryParse(raw)?.toLocal() : null;

/// Ganztägige Werte wie „2026-10-14“ ohne Zeitzonenverschiebung.
DateTime? parseDay(Object? raw) {
  if (raw is! String || raw.length < 10) return null;
  return DateTime.tryParse(raw.substring(0, 10));
}

int? parseInt(Object? raw) => switch (raw) {
      int v => v,
      String v => int.tryParse(v),
      _ => null,
    };
