import 'dart:math';

/// Eine ohne Netz gemerkte Änderung (#32). Wird später genau so gesendet; [id] ist zugleich der
/// Idempotency-Key, damit eine Wiederholung nichts doppelt anlegt.
class PendingChange {
  final String id;
  final String kind; // shopping_add | shopping_done | shopping_delete | task_complete | task_create
  final String method;
  final String path;
  final Map<String, dynamic>? body;
  final String label; // für Menschen: „Milch auf die Einkaufsliste“
  final String? target; // uid des betroffenen Eintrags (Abhaken/Löschen)
  final DateTime created;
  final String? conflict; // Server hat abgelehnt: Grund (bleibt sichtbar, bis verworfen)
  /// Nur für die Anzeige, wird nie gesendet (z. B. die vorläufige Aufgabe und in welchen Listen sie erscheint).
  final Map<String, dynamic>? meta;

  const PendingChange({
    required this.id,
    required this.kind,
    required this.method,
    required this.path,
    this.body,
    required this.label,
    this.target,
    required this.created,
    this.conflict,
    this.meta,
  });

  static String newId() {
    final r = Random.secure();
    return 'off-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-'
        '${List.generate(12, (_) => r.nextInt(36).toRadixString(36)).join()}';
  }

  bool get isConflict => conflict != null;

  PendingChange withConflict(String message) => PendingChange(
      id: id, kind: kind, method: method, path: path, body: body, label: label, target: target,
      created: created, conflict: message, meta: meta);

  Map<String, dynamic> toJson() => {
        'id': id, 'kind': kind, 'method': method, 'path': path, 'body': body, 'label': label,
        'target': target, 'created': created.toIso8601String(), 'conflict': conflict, 'meta': meta,
      };

  static PendingChange? fromJson(Object? raw) {
    if (raw is! Map) return null;
    try {
      return PendingChange(
        id: raw['id'] as String,
        kind: raw['kind'] as String,
        method: raw['method'] as String,
        path: raw['path'] as String,
        body: (raw['body'] as Map?)?.cast<String, dynamic>(),
        label: raw['label'] as String,
        target: raw['target'] as String?,
        created: DateTime.parse(raw['created'] as String),
        conflict: raw['conflict'] as String?,
        meta: (raw['meta'] as Map?)?.cast<String, dynamic>(),
      );
    } catch (_) {
      return null;
    }
  }
}
