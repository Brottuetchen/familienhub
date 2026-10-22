part of 'api_client.dart';

/// Shopping list and template lists.
mixin ShoppingApi on ApiClientBase {
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
      body: {'item': item}, label: l10n.addedToList(item), created: DateTime.now()));

  Future<bool> setShoppingDone(String uid, bool done, {String? name}) => _sendOrQueue(PendingChange(
      id: PendingChange.newId(), kind: 'shopping_done', method: 'PATCH',
      path: '/api/shopping/${Uri.encodeComponent(uid)}', body: {'done': done}, target: uid,
      label: '„${name ?? 'Artikel'}“ ${done ? 'abgehakt' : 'wieder offen'}', created: DateTime.now()));

  Future<bool> deleteShoppingItem(String uid, {String? name}) => _sendOrQueue(PendingChange(
      id: PendingChange.newId(), kind: 'shopping_delete', method: 'DELETE',
      path: '/api/shopping/${Uri.encodeComponent(uid)}', target: uid,
      label: l10n.deletedTitle(name ?? l10n.item), created: DateTime.now()));

  // ── Vorlagen (template lists) ──────────────────────────────────────────────

  Future<List<ListTemplate>> templates() async {
    final json = await _send('GET', '/api/templates') as Map<String, dynamic>;
    return ((json['items'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(ListTemplate.fromJson)
        .toList();
  }

  /// Creates ([id] null) or replaces a template.
  Future<void> saveTemplate(int? id, String name, List<TemplateItem> items) => _send(
      id == null ? 'POST' : 'PUT', id == null ? '/api/templates' : '/api/templates/$id',
      body: {'name': name, 'items': [for (final i in items) i.toJson()]});

  Future<void> deleteTemplate(int id) => _send('DELETE', '/api/templates/$id');

  Future<void> templateFromShopping(String name) => _send('POST', '/api/templates/from-shopping', body: {'name': name});

  /// [itemIds] null = all items.
  Future<TemplateApplied> applyTemplateToShopping(int id, {List<int>? itemIds}) async => TemplateApplied.fromJson(
      await _send('POST', '/api/templates/$id/apply/shopping', body: {'item_ids': itemIds}) as Map<String, dynamic>);

  Future<TemplateApplied> applyTemplateToTasks(int id, {List<int>? itemIds, bool family = false}) async =>
      TemplateApplied.fromJson(await _send('POST', '/api/templates/$id/apply/tasks',
          body: {'item_ids': itemIds, if (family) 'list': 'family'}) as Map<String, dynamic>);

  /// Own list. Does not add the items to the main shopping or task list.
  Future<Map<String, dynamic>> applyTemplateAsList(int id,
          {required String name, required String kind, List<int>? itemIds, int? assigneeId}) async =>
      await _send('POST', '/api/templates/$id/apply/list', body: {
        'name': name,
        'kind': kind,
        if (itemIds != null) 'item_ids': itemIds,
        if (assigneeId != null) 'assignee_id': assigneeId,
      }) as Map<String, dynamic>;
}
