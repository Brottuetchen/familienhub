import 'dart:convert';

import '../models/pending.dart';

/// Legt gemerkte Offline-Änderungen (#32) über gelesene Daten, damit alle Ansichten (auch Widgets)
/// sofort den erwarteten Stand zeigen. Reine Funktion: die Quelle bleibt unverändert.
/// Betroffen sind nur Einkauf, „Heute“ und Aufgabenlisten; Konflikte werden nicht überlagert.
dynamic applyPending(String key, dynamic data, List<PendingChange> changes) {
  final active = [for (final c in changes) if (!c.isConflict) c];
  if (active.isEmpty || data is! Map) return data;
  final copy = jsonDecode(jsonEncode(data)) as Map<String, dynamic>;
  if (key == 'shopping') {
    _shopping(copy, active);
  } else if (key == 'today') {
    final tasks = copy['tasks'];
    if (tasks is Map && tasks['items'] is List) _tasks(tasks['items'] as List, active, view: 'today');
    final adds = active.where((c) => c.kind == 'shopping_add').length;
    final checked = active.where((c) => c.kind == 'shopping_done' && c.body?['done'] == true).length;
    final open = copy['shopping_open'];
    if (open is int) copy['shopping_open'] = (open + adds - checked).clamp(0, 1 << 30);
  } else if (key.startsWith('tasks:')) {
    if (copy['items'] is List) _tasks(copy['items'] as List, active, view: key.substring('tasks:'.length));
  }
  return copy;
}

void _shopping(Map<String, dynamic> data, List<PendingChange> active) {
  final groups = (data['groups'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
  final deleted = {for (final c in active) if (c.kind == 'shopping_delete') c.target};
  final done = {for (final c in active) if (c.kind == 'shopping_done') c.target: c.body?['done'] == true};
  for (final g in groups) {
    final items = (g['items'] as List? ?? const []).whereType<Map<String, dynamic>>().toList();
    items.removeWhere((i) => deleted.contains(i['uid']));
    for (final i in items) {
      final d = done[i['uid']];
      if (d != null) {
        i['status'] = d ? 'completed' : 'needs_action';
        i['pending'] = true;
      }
    }
    g['items'] = <dynamic>[...items];
  }
  final adds = [for (final c in active) if (c.kind == 'shopping_add') c];
  if (adds.isNotEmpty) {
    var manual = groups.where((g) => g['key'] == 'manual').firstOrNull;
    if (manual == null) {
      manual = <String, dynamic>{'key': 'manual', 'items': <dynamic>[]};
      groups.insert(0, manual);
    }
    final list = manual['items'] as List;
    for (final c in adds) {
      list.add(<String, dynamic>{
        'uid': 'pending:${c.id}', 'summary': c.body?['item'] ?? '', 'status': 'needs_action', 'pending': true,
      });
    }
  }
  data['groups'] = groups;
}

void _tasks(List items, List<PendingChange> active, {required String view}) {
  final completed = {for (final c in active) if (c.kind == 'task_complete') c.target};
  for (final t in items.whereType<Map<String, dynamic>>()) {
    if (completed.contains(t['uid'])) {
      t['done'] = true;
      t['pending'] = true;
    }
  }
  // Offline angelegte Aufgaben vorn in den passenden Listen (ohne Aktionen, bis sie gesendet sind)
  final created = [
    for (final c in active)
      if (c.kind == 'task_create' && ((c.meta?['views'] as List?) ?? const []).contains(view) && c.meta?['task'] is Map)
        <String, dynamic>{...(c.meta!['task'] as Map).cast<String, dynamic>(), 'uid': 'pending:${c.id}', 'pending': true},
  ];
  items.insertAll(0, created);
}
