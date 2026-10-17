import 'common.dart';

class ShoppingItem {
  final String uid;
  final String summary;
  final bool done;
  final String? description;
  final bool pending; // ohne Netz gemerkt, noch nicht gesendet (#32)

  const ShoppingItem({
    required this.uid,
    required this.summary,
    this.done = false,
    this.description,
    this.pending = false,
  });

  /// Offline hinzugefügt: gibt es auf dem Server noch nicht, also weder abhaken noch löschen.
  bool get localOnly => uid.startsWith('pending:');

  factory ShoppingItem.fromJson(Map<String, dynamic> json) => ShoppingItem(
        uid: json['uid'] as String,
        summary: (json['summary'] as String?) ?? '',
        done: json['status'] == 'completed',
        description: json['description'] as String?,
        pending: json['pending'] == true,
      );
}

/// `manual` = freie Artikel (löschbar), `recipes` = Zutaten aus Cookidoo (nur abhaken).
class ShoppingGroup {
  final String key;
  final List<ShoppingItem> items;

  const ShoppingGroup({required this.key, this.items = const []});

  bool get isRecipes => key == 'recipes';
  String get title => isRecipes ? 'Aus Rezepten' : 'Freie Artikel';

  factory ShoppingGroup.fromJson(Map<String, dynamic> json) => ShoppingGroup(
        key: json['key'] as String,
        items: ((json['items'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ShoppingItem.fromJson)
            .toList(),
      );
}

class ShoppingData {
  final SourceStatus status;
  final String? error;
  final List<ShoppingGroup> groups;

  const ShoppingData({required this.status, this.error, this.groups = const []});

  factory ShoppingData.fromJson(Map<String, dynamic> json) {
    final r = SourceResult.fromJson(json, ShoppingGroup.fromJson, key: 'groups');
    return ShoppingData(status: r.status, error: r.error, groups: r.items);
  }

  int get openCount =>
      groups.fold(0, (sum, g) => sum + g.items.where((i) => !i.done).length);
}
