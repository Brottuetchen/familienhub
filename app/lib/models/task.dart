import 'dart:convert';

import 'common.dart';
import '../l10n/l10n.dart';

/// Ansichten wie im Backend (`/api/tasks?view=`).
enum TaskView {
  mine('mine'),
  forMe('for_me'),
  fromMe('from_me'),
  family('family');

  final String apiName;
  const TaskView(this.apiName);

  String get label => switch (this) {
        mine => l10n.mine,
        forMe => l10n.forMe,
        fromMe => l10n.fromMe,
        family => l10n.family,
      };

  static TaskView fromApi(String? name) =>
      values.firstWhere((v) => v.apiName == name, orElse: () => mine);
}

class Task {
  final String uid;
  final String provider;
  final String account;
  final Map<String, dynamic> native;
  String get identity => jsonEncode([provider, account, uid]);
  bool get isHabitica => provider == 'habitica';
  final String title;
  final String notes;
  final DateTime? due;
  final bool dueIsDate;
  final int? priority;
  final bool done;
  final bool selected;
  final List<String> actions;
  final String? listName;
  final String? listKind;
  final int? createdBy;
  final int? assignee;
  final String recurrence;
  final List<int> rotation;

  const Task({
    required this.uid,
    this.provider = 'nextcloud',
    this.account = '',
    this.native = const {},
    required this.title,
    this.notes = '',
    this.due,
    this.dueIsDate = false,
    this.priority,
    this.done = false,
    this.selected = false,
    this.actions = const [],
    this.listName,
    this.listKind,
    this.createdBy,
    this.assignee,
    this.recurrence = 'none',
    this.rotation = const [],
  });

  /// Offline angelegt (#32): gibt es auf dem Server noch nicht, also weder abhaken noch bearbeiten.
  bool get localOnly => uid.startsWith('pending:');

  factory Task.fromJson(Map<String, dynamic> json) {
    final list = json['list'];
    final dueRaw = json['due'];
    final dueIsDate = dueRaw is String && dueRaw.length == 10;
    return Task(
      uid: json['uid'] as String,
      provider: json['provider'] as String? ?? 'nextcloud',
      account: json['account'] as String? ?? '',
      native: Map<String, dynamic>.from(json['native'] as Map? ?? const {}),
      title: (json['title'] as String?) ?? l10n.task,
      notes: (json['notes'] as String?) ?? '',
      due: dueIsDate ? parseDay(dueRaw) : parseDate(dueRaw),
      dueIsDate: dueIsDate,
      priority: parseInt(json['priority']),
      done: json['done'] == true,
      selected: json['selected'] == true,
      actions: (json['actions'] as List? ?? const []).cast<String>(),
      listName: list is Map ? list['name'] as String? : null,
      listKind: list is Map ? list['kind'] as String? : null,
      createdBy: parseInt(json['created_by']),
      assignee: parseInt(json['assignee']),
      recurrence: (json['recurrence'] as String?) ?? 'none',
      rotation: ((json['rotation'] as List?) ?? const []).map(parseInt).whereType<int>().toList(),
    );
  }

  bool isOverdue(DateTime now) {
    if (due == null || done) return false;
    final today = DateTime(now.year, now.month, now.day);
    return dueIsDate ? due!.isBefore(today) : due!.isBefore(now);
  }
}

class TaskListInfo {
  final String caldavUrl;
  final String displayName;
  final String? kind; // personal | family | hidden
  final int? ownerUserId;

  const TaskListInfo({
    required this.caldavUrl,
    required this.displayName,
    this.kind,
    this.ownerUserId,
  });

  factory TaskListInfo.fromJson(Map<String, dynamic> json) => TaskListInfo(
        caldavUrl: json['caldav_url'] as String,
        displayName: (json['display_name'] as String?) ?? l10n.list,
        kind: json['kind'] as String?,
        ownerUserId: parseInt(json['owner_user_id']),
      );
}


/// Anbieter und ausschließlich die Kontoreferenz der aktuellen Sitzung.
class TaskProviderInfo {
  final String id, name, account;
  final bool configured;
  const TaskProviderInfo(this.id, this.name, this.account, this.configured);
  factory TaskProviderInfo.fromJson(Map<String, dynamic> j) => TaskProviderInfo(
    j['id'] as String, j['name'] as String, j['account'] as String, j['configured'] == true);
}
