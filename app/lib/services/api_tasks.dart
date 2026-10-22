part of 'api_client.dart';

/// Tasks, Habitica and CalDAV task lists.
mixin TasksApi on ApiClientBase {
  // ── Aufgaben ───────────────────────────────────────────────────────────────

  Future<ApiResult<SourceResult<Task>>> tasks(TaskView view) => _cachedGet(
        '/api/tasks?provider=all&include_done=true&view=${view.apiName}',
        'tasks:${view.apiName}',
        (j) => SourceResult.fromJson(j as Map<String, dynamic>, Task.fromJson),
      );

  /// Liefert die angelegte Aufgabe, oder null, wenn sie ohne Netz gemerkt wurde.
  ///
  /// `provider: 'auto'` (default): the hub routes by recipient: a task for someone else goes to her preferred
  /// place, family tasks to the family list, own tasks to my preferred place.
  Future<Task?> createTask({
    required String title,
    String provider = 'auto',
    String? account,
    int? assigneeId,
    DateTime? due,
    bool family = false,
    String? notes,
    String recurrence = 'none',
    List<int> rotation = const [],
    int? meId,
    int? priority,
    int? stars,
    Map<String, dynamic>? native,
  }) async {
    final path = _taskPath('', provider, account);
    final body = {
      if (stars != null && stars > 0) 'stars': stars,
      'title': title,
      if (notes != null && notes.isNotEmpty) 'notes': notes,
      if (due != null) 'due': _dateOnly(due),
      if (assigneeId != null) 'assignee_id': assigneeId,
      if (priority != null) 'priority': priority,
      if (native != null && native.isNotEmpty) 'native': native,
      if (family) 'list': 'family',
      if (rotation.isNotEmpty) ...{
        'recurrence': recurrence,
        'rotation': rotation,
        'habitica': false,
      },
    };
    // Einfache Nextcloud-Aufgaben gehen auch offline; Haushaltsrotation und Habitica nicht.
    // Native Habitica options mean the task lands in Habitica (hub-routed): never queued either.
    if (provider == 'habitica' || rotation.isNotEmpty || (native != null && native.isNotEmpty)) {
      final json = await _send('POST', path, replayOn401: false, body: body);
      return Task.fromJson(json as Map<String, dynamic>);
    }
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final mine = !family && (assigneeId == null || assigneeId == meId);
    final views = family ? ['family'] : mine ? ['mine'] : ['from_me'];
    if (mine && due != null && !DateTime(due.year, due.month, due.day).isAfter(today)) views.add('today');
    final change = PendingChange(
      id: PendingChange.newId(), kind: 'task_create', method: 'POST', path: path, body: body,
      label: l10n.createdTitle(title), created: now,
      meta: {
        'views': views,
        'task': {
          'title': title, 'provider': provider, 'account': account ?? '', 'done': false,
          if (due != null) 'due': _dateOnly(due),
          if (assigneeId != null) 'assignee': assigneeId,
          if (family) 'list': {'name': l10n.family, 'kind': 'family'},
        },
      },
    );
    final result = await _sendOrQueueJson(change);
    return result == null ? null : Task.fromJson(result as Map<String, dynamic>);
  }


  /// Preferred task place of the signed-in person; null if the server is older or unreachable.
  Future<TaskPlaceInfo?> taskPlace() async {
    try {
      return TaskPlaceInfo.fromJson(await _send('GET', '/api/tasks/me/place') as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Place type (`habitica`, `nextcloud`, `hub_tasks`, ...) where a task for [userId] (or the family list) lands,
  /// so the create sheet can show the matching fields. null if unknown (old server, offline).
  Future<String?> taskPlaceOf({int? userId, bool family = false}) async {
    try {
      final json = await _send('GET', family ? '/api/tasks/place/family' : '/api/tasks/place/$userId') as Map<String, dynamic>;
      final place = json['place'] as String?;
      return place == null || place.isEmpty ? null : place;
    } catch (_) {
      return null;
    }
  }

  /// `place == null` resets to the place derived from the connected accounts.
  Future<TaskPlaceInfo> setTaskPlace(String? place) async => TaskPlaceInfo.fromJson(
      await _send('PUT', '/api/tasks/me/place', body: {'place': place}) as Map<String, dynamic>);

  Future<List<TaskProviderInfo>> taskProviders() async =>
    _maps((await _send('GET', '/api/tasks/providers'))['items']).map(TaskProviderInfo.fromJson).toList();

  Future<void> updateTask(Task task, {required String title, required String notes, DateTime? due, int? priority, int? stars}) =>
    _send('PATCH', _taskPath('/${Uri.encodeComponent(task.uid)}', task.provider, task.account), replayOn401: false, body: {
      if (stars != null && stars != task.stars) 'stars': stars,
      if (title != task.title) 'title': title,
      if (notes != task.notes) 'notes': notes,
      if (due != task.due) 'due': due == null ? null : _dateOnly(due),
      if (priority != task.priority) 'priority': priority,
    });

  /// true = erledigt gesendet, false = ohne Netz gemerkt. Habitica nie gemerkt (Punkte würden doppelt zählen).
  Future<bool> completeTask(String uid, {String provider = 'nextcloud', String? account, String? title}) async {
    if (provider == 'habitica') {
      await nativeTaskActionAndRefresh(Task(uid: uid, title: '', provider: provider, account: account ?? ''), 'up');
      return true;
    }
    return _sendOrQueue(PendingChange(
        id: PendingChange.newId(), kind: 'task_complete', method: 'POST',
        path: _taskPath('/${Uri.encodeComponent(uid)}/complete', provider, account), target: uid,
        label: l10n.completedTitle(title ?? l10n.task), created: DateTime.now()));
  }

  Future<void> deleteTask(String uid, {String provider = 'nextcloud', String? account}) async {
    final path = _taskPath('/${Uri.encodeComponent(uid)}', provider, account);
    if (provider == 'habitica') {
      await _nativeTaskOperation(account ?? '', () async {
        await _nativeTaskMutation('DELETE', path, {});
        await _nativeReadAfterWrite(account ?? '', targetIdentity: _nativeIdentity(uid, account ?? ''), expectedPresent: false);
      });
    } else {
      await _send('DELETE', path, replayOn401: false);
    }
  }

  bool nativeTaskBlocked(String account) =>
    _nativeTaskLocks[account] == _epoch || _nativeTaskUncertain[account] == _epoch || _nativeTaskConfirmed[account] == _epoch;

  String newNativeId() => _operationId();

  Future<T> _nativeTaskOperation<T>(String account, Future<T> Function() operation) async {
    if (account.isEmpty) throw ApiException(403, l10n.noTaskAccount);
    if (nativeTaskBlocked(account)) throw ApiException(409, l10n.actionRunningUnclear);
    final epoch = _epoch;
    // ponytail: pro Konto serialisiert; per-account locks keep unrelated accounts independent.
    _nativeTaskLocks[account] = epoch;
    try {
      return await operation();
    } catch (e) {
      if (epoch == _epoch && (e is OfflineException || e is! ApiException || e.statusCode >= 500 || e.statusCode < 400)) {
        _nativeTaskUncertain[account] = epoch;
      }
      rethrow;
    } finally {
      if (_nativeTaskLocks[account] == epoch) _nativeTaskLocks.remove(account);
    }
  }

  Future<dynamic> _nativeTaskMutation(String method, String path, Map<String, dynamic> body) async {
    final operation = _operationId();
    return _send(method, method == 'DELETE' ? '$path&operation_id=$operation' : path, replayOn401: false,
      body: method == 'DELETE' ? null : {...body, 'operation_id': operation});
  }

  Future<Map<String, dynamic>> habiticaOptions() async =>
    await _send('GET', '/api/habitica/options') as Map<String, dynamic>;

  Future<Map<String, dynamic>> habiticaAccount() async =>
    await _send('GET', '/api/habitica/account') as Map<String, dynamic>;

  Future<void> saveHabiticaAccount(String userId, String key) =>
    _send('PUT', '/api/habitica/account', replayOn401: false, body: {'remote_user_id': userId, 'api_key': key});

  Future<SourceResult<Task>> habiticaTasks() async => SourceResult.fromJson(
    await _send('GET', '/api/habitica/tasks') as Map<String, dynamic>, Task.fromJson);

  Future<void> selectHabiticaTask(Task task, bool selected) => _send(
    'PUT', _taskPath('/${Uri.encodeComponent(task.uid)}/selection', task.provider, task.account), replayOn401: false,
    body: {'selected': selected});

  Future<void> saveNativeTask(String account, Map<String, dynamic> native, {String? uid, String? expectedVersion}) async {
    await _nativeTaskOperation(account, () async {
      final response = await _nativeTaskMutation(
        uid == null ? 'POST' : 'PATCH', _taskPath(uid == null ? '' : '/${Uri.encodeComponent(uid)}', 'habitica', account),
        {'native': native, if (uid == null) 'title': native['text'] ?? '', if (uid != null) 'expected_version': expectedVersion});
      final targetUid = uid ?? (response is Map<String, dynamic> ? response['uid'] as String? : null);
      if (targetUid == null || targetUid.isEmpty) throw NativeTaskConfirmedReadException();
      await _nativeReadAfterWrite(account, targetIdentity: _nativeIdentity(targetUid, account), expectedPresent: true);
    });
  }

  Future<void> nativeTaskAction(Task task, String action, {String? itemId, Map<String, dynamic> fields = const {}}) =>
      _nativeTaskOperation(task.account, () async {
        await _nativeTaskMutation(
          'POST', _taskPath('/${Uri.encodeComponent(task.uid)}/actions', task.provider, task.account),
          {'action': action, if (itemId != null) 'item_id': itemId, 'fields': fields});
        await _nativeReadAfterWrite(task.account, targetIdentity: task.identity, expectedPresent: true);
      });

  Future<SourceResult<Task>> _nativeReadAfterWrite(String account, {String? targetIdentity, bool? expectedPresent}) async {
    final epoch = _epoch;
    try {
      final result = await habiticaTasks();
      final present = targetIdentity == null || result.items.any((task) => task.identity == targetIdentity);
      if (epoch != _epoch || !result.isOk || (expectedPresent != null && present != expectedPresent)) {
        throw NativeTaskConfirmedReadException();
      }
      return result;
    } catch (error) {
      if (epoch == _epoch) _nativeTaskConfirmed[account] = epoch;
      if (error is NativeTaskConfirmedReadException) rethrow;
      throw NativeTaskConfirmedReadException();
    }
  }

  Future<Task> nativeTaskActionAndRefresh(Task task, String action, {String? itemId, Map<String, dynamic> fields = const {}}) =>
      _nativeTaskOperation(task.account, () async {
        await _nativeTaskMutation(
          'POST', _taskPath('/${Uri.encodeComponent(task.uid)}/actions', task.provider, task.account),
          {'action': action, if (itemId != null) 'item_id': itemId, 'fields': fields});
        final result = await _nativeReadAfterWrite(task.account, targetIdentity: task.identity, expectedPresent: true);
        return result.items.firstWhere((current) => current.identity == task.identity);
      });

  Future<SourceResult<Task>> reconcileHabiticaTasks(String account) async {
    if (account.isEmpty) throw ApiException(403, l10n.noTaskAccount);
    final epoch = _epoch;
    if (_nativeTaskLocks[account] == epoch) throw ApiException(409, l10n.actionRunning);
    _nativeTaskLocks[account] = epoch;
    try {
      final result = await habiticaTasks();
      if (epoch == _epoch && result.isOk) {
        _nativeTaskConfirmed.remove(account);
        _nativeTaskUncertain.remove(account);
      }
      return result;
    } finally {
      if (_nativeTaskLocks[account] == epoch) _nativeTaskLocks.remove(account);
    }
  }

  Future<CalDavAccountInfo?> caldavAccount() async {
    try {
      return CalDavAccountInfo.fromJson(
          await _send('GET', '/api/tasks/me/caldav') as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  Future<void> saveCaldavAccount(String url, String username, String password) =>
      _send('PUT', '/api/tasks/me/caldav',
          body: {'url': url, 'username': username, 'password': password});

  /// Alle VTODO-Listen des Kontos, ergänzt um die gespeicherte Zuordnung.
  Future<SourceResult<TaskListInfo>> taskLists() async {
    final available = SourceResult.fromJson(
        await _send('GET', '/api/tasks/lists') as Map<String, dynamic>,
        TaskListInfo.fromJson,
        key: 'lists');
    final config = {
      for (final c in _maps(await _send('GET', '/api/tasks/me/task-lists')).map(TaskListInfo.fromJson))
        c.caldavUrl: c
    };
    return SourceResult(
      status: available.status,
      error: available.error,
      items: [
        for (final l in available.items)
          TaskListInfo(
            caldavUrl: l.caldavUrl,
            displayName: l.displayName,
            kind: config[l.caldavUrl]?.kind,
            ownerUserId: config[l.caldavUrl]?.ownerUserId,
          ),
      ],
    );
  }

  Future<void> saveTaskLists(List<TaskListInfo> lists) => _send('PUT', '/api/tasks/me/task-lists',
      body: [
        for (final l in lists.where((l) => l.kind != null))
          {'caldav_url': l.caldavUrl, 'kind': l.kind, 'owner_user_id': l.ownerUserId},
      ]);
}

String _taskPath(String suffix, String provider, String? account) {
  final query = Uri(queryParameters: {
    'provider': provider, if (account != null && account.isNotEmpty) 'account': account,
  }).query;
  return '/api/tasks$suffix?$query';
}

String _operationId() {
  final random = Random.secure();
  final bytes = List.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  final h = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

String _nativeIdentity(String uid, String account) =>
    Task(uid: uid, title: '', provider: 'habitica', account: account).identity;

