import 'common.dart';

/// Dokument aus Paperless (über den Hub, mit dem eigenen Paperless-Zugang).
class PaperlessDoc {
  final int id;
  final String title;
  final DateTime? created;
  final String? correspondent;
  final String? documentType;
  final List<String> tags;
  final String url; // in Paperless öffnen
  final String thumb; // /api/paperless/documents/{id}/thumb
  final DateTime? deadline;
  final String? task;

  const PaperlessDoc({
    required this.id,
    required this.title,
    this.created,
    this.correspondent,
    this.documentType,
    this.tags = const [],
    required this.url,
    required this.thumb,
    this.deadline,
    this.task,
  });

  factory PaperlessDoc.fromJson(Map<String, dynamic> json) => PaperlessDoc(
        id: parseInt(json['id']) ?? 0,
        title: (json['title'] as String?) ?? '',
        created: parseDay(json['created']),
        correspondent: json['correspondent'] as String?,
        documentType: json['document_type'] as String?,
        tags: ((json['tags'] as List?) ?? const []).map((t) => t.toString()).toList(),
        url: (json['url'] as String?) ?? '',
        thumb: (json['thumb'] as String?) ?? '',
        deadline: parseDay(json['deadline']),
        task: json['task'] as String?,
      );
}

/// Antwort einer Paperless-Liste: ok | no_account | auth_failed | unavailable | not_configured.
class PaperlessList {
  final String status;
  final String? error;
  final List<PaperlessDoc> items;
  const PaperlessList({required this.status, this.error, this.items = const []});

  bool get needsAccount => status == 'no_account' || status == 'auth_failed';

  factory PaperlessList.fromJson(Map<String, dynamic> json) => PaperlessList(
        status: (json['status'] as String?) ?? 'unavailable',
        error: json['error'] as String?,
        items: ((json['items'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(PaperlessDoc.fromJson)
            .toList(),
      );
}
