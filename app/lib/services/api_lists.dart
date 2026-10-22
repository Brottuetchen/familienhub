part of 'api_client.dart';

/// Named shopping and task lists. Items here are not on the main lists.
mixin ListsApi on ApiClientBase {
  Future<List<Map<String, dynamic>>> namedLists(String kind, {int? assigneeId}) async {
    final query = assigneeId == null ? 'kind=$kind' : 'kind=$kind&assignee_id=$assigneeId';
    final json = await _send('GET', '/api/lists?$query') as Map<String, dynamic>;
    return ((json['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>> namedList(int id) async =>
      await _send('GET', '/api/lists/$id') as Map<String, dynamic>;

  Future<Map<String, dynamic>> createNamedList(String kind, String name, {int? assigneeId}) async =>
      await _send('POST', '/api/lists', body: {
        'kind': kind,
        'name': name,
        if (assigneeId != null) 'assignee_id': assigneeId,
      }) as Map<String, dynamic>;

  Future<Map<String, dynamic>> patchNamedList(int id, {String? name, Object? assigneeId = _keep}) async =>
      await _send('PATCH', '/api/lists/$id', body: {
        if (name != null) 'name': name,
        if (!identical(assigneeId, _keep)) 'assignee_id': assigneeId,
      }) as Map<String, dynamic>;

  Future<void> deleteNamedList(int id) => _send('DELETE', '/api/lists/$id');

  Future<Map<String, dynamic>> addNamedItem(int listId, String summary, {int? assigneeId}) async =>
      await _send('POST', '/api/lists/$listId/items', body: {
        'summary': summary,
        if (assigneeId != null) 'assignee_id': assigneeId,
      }) as Map<String, dynamic>;

  Future<Map<String, dynamic>> patchNamedItem(int listId, String itemId,
          {bool? done, Object? assigneeId = _keep}) async =>
      await _send('PATCH', '/api/lists/$listId/items/${Uri.encodeComponent(itemId)}', body: {
        if (done != null) 'done': done,
        if (!identical(assigneeId, _keep)) 'assignee_id': assigneeId,
      }) as Map<String, dynamic>;
}

const _keep = Object();
