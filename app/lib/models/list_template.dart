/// One entry of a template list: a name and an optional quantity / note.
class TemplateItem {
  final int? id;
  final String name;
  final String note;

  const TemplateItem({this.id, required this.name, this.note = ''});

  factory TemplateItem.fromJson(Map<String, dynamic> json) => TemplateItem(
        id: json['id'] as int?,
        name: (json['name'] as String?) ?? '',
        note: (json['note'] as String?) ?? '',
      );

  Map<String, dynamic> toJson() => {'name': name, 'note': note};
}

/// Reusable list (packing list, weekly shopping, ...), shared within the family.
class ListTemplate {
  final int id;
  final String name;
  final List<TemplateItem> items;

  const ListTemplate({required this.id, required this.name, this.items = const []});

  factory ListTemplate.fromJson(Map<String, dynamic> json) => ListTemplate(
        id: json['id'] as int,
        name: (json['name'] as String?) ?? '',
        items: ((json['items'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(TemplateItem.fromJson)
            .toList(),
      );
}

/// Result of applying a template to the shopping list or the tasks.
class TemplateApplied {
  final String status;
  final int added; // shopping: new entries, tasks: created tasks
  final int skipped;
  final int failed;

  const TemplateApplied({this.status = 'ok', this.added = 0, this.skipped = 0, this.failed = 0});

  factory TemplateApplied.fromJson(Map<String, dynamic> json) => TemplateApplied(
        status: (json['status'] as String?) ?? 'ok',
        added: ((json['added'] ?? json['created']) as num?)?.toInt() ?? 0,
        skipped: (json['skipped'] as num?)?.toInt() ?? 0,
        failed: (json['failed'] as num?)?.toInt() ?? 0,
      );
}
