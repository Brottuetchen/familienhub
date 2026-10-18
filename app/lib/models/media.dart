import 'common.dart';
import '../l10n/l10n.dart';

/// 'movie' oder 'tv' wie in Seerr.
enum MediaKind {
  movie('movie'),
  tv('tv');

  final String api;
  const MediaKind(this.api);

  String get label => this == movie ? l10n.movie : l10n.tvShow;

  static MediaKind? fromApi(Object? v) => values.where((k) => k.api == v).firstOrNull;
}

/// Suchtreffer aus Seerr (deutscher Titel, Poster von TMDB).
class MediaItem {
  final int tmdbId;
  final MediaKind kind;
  final String title;
  final int? year;
  final String overview;
  final String? poster;
  final String? statusLabel;
  final bool requestable;

  const MediaItem({
    required this.tmdbId,
    required this.kind,
    required this.title,
    this.year,
    this.overview = '',
    this.poster,
    this.statusLabel,
    this.requestable = true,
  });

  factory MediaItem.fromJson(Map<String, dynamic> json) => MediaItem(
        tmdbId: json['tmdb_id'] as int,
        kind: MediaKind.fromApi(json['media_type']) ?? MediaKind.movie,
        title: (json['title'] as String?) ?? '',
        year: parseInt(json['year']),
        overview: (json['overview'] as String?) ?? '',
        poster: json['poster'] as String?,
        statusLabel: json['status_label'] as String?,
        requestable: json['requestable'] != false,
      );
}

/// Eigener Wunsch mit Stand.
class MediaRequestItem {
  final int id;
  final MediaKind kind;
  final int? tmdbId;
  final String title;
  final int? year;
  final String? poster;
  final String statusLabel;
  final int? status;
  final bool available;
  final bool canCancel;

  const MediaRequestItem({
    required this.id,
    required this.kind,
    this.tmdbId,
    required this.title,
    this.year,
    this.poster,
    required this.statusLabel,
    this.status,
    this.available = false,
    this.canCancel = false,
  });

  bool get isProblem => status == 3 || status == 4;

  factory MediaRequestItem.fromJson(Map<String, dynamic> json) => MediaRequestItem(
        id: json['id'] as int,
        kind: MediaKind.fromApi(json['media_type']) ?? MediaKind.movie,
        tmdbId: parseInt(json['tmdb_id']),
        title: (json['title'] as String?) ?? '',
        year: parseInt(json['year']),
        poster: json['poster'] as String?,
        statusLabel: (json['status_label'] as String?) ?? '',
        status: parseInt(json['status']),
        available: json['available'] == true,
        canCancel: json['can_cancel'] == true,
      );
}

/// Antwort mit Status wie bei allen Konnektoren; zusätzlich „no_account“ (kein passender Seerr-Nutzer).
class MediaList<T> {
  final String status;
  final String? error;
  final List<T> items;
  const MediaList({required this.status, this.error, this.items = const []});

  bool get ok => status == 'ok';

  factory MediaList.fromJson(Map<String, dynamic> json, T Function(Map<String, dynamic>) item) => MediaList(
        status: (json['status'] as String?) ?? 'unavailable',
        error: json['error'] as String?,
        items: ((json['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().map(item).toList(),
      );
}
