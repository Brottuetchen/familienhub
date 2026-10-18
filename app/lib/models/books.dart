import 'common.dart';
import '../l10n/l10n.dart';

/// 'ebook' oder 'audiobook' wie in Shelfarr.
enum BookKind {
  ebook('ebook'),
  audiobook('audiobook');

  final String api;
  const BookKind(this.api);

  String get label => this == ebook ? l10n.ebook : l10n.audiobook;

  static BookKind? fromApi(String? v) => values.where((k) => k.api == v).firstOrNull;
}

class BookResult {
  final String workId;
  final String title;
  final String? author;
  final int? year;
  final String? coverUrl;
  final String? series;
  final List<BookKind> kinds;

  const BookResult({
    required this.workId,
    required this.title,
    this.author,
    this.year,
    this.coverUrl,
    this.series,
    this.kinds = const [],
  });

  factory BookResult.fromJson(Map<String, dynamic> json) => BookResult(
        workId: json['work_id'] as String,
        title: (json['title'] as String?) ?? '',
        author: json['author'] as String?,
        year: parseInt(json['year']),
        coverUrl: json['cover_url'] as String?,
        series: json['series'] as String?,
        kinds: ((json['book_types'] as List?) ?? const [])
            .map((e) => BookKind.fromApi(e as String?))
            .whereType<BookKind>()
            .toList(),
      );
}

class BookRequest {
  final int id;
  final String status;
  final String statusLabel;
  final String title;
  final String? author;
  final BookKind? kind;
  final bool attentionNeeded;
  final String? issue;

  const BookRequest({
    required this.id,
    required this.status,
    required this.statusLabel,
    required this.title,
    this.author,
    this.kind,
    this.attentionNeeded = false,
    this.issue,
  });

  bool get isDone => status == 'completed';
  bool get isProblem => const ['failed', 'not_found'].contains(status) || attentionNeeded;
  bool get canCancel => const ['pending', 'searching', 'not_found', 'awaiting_purchase'].contains(status);

  factory BookRequest.fromJson(Map<String, dynamic> json) => BookRequest(
        id: parseInt(json['id']) ?? 0,
        status: (json['status'] as String?) ?? '',
        statusLabel: (json['status_label'] as String?) ?? (json['status'] as String? ?? ''),
        title: (json['title'] as String?) ?? '',
        author: json['author'] as String?,
        kind: BookKind.fromApi(json['book_type'] as String?),
        attentionNeeded: json['attention_needed'] == true,
        issue: json['issue'] as String?,
      );
}
