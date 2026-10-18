import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../models/common.dart';
import '../../models/task.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'habitica_tasks.dart';
import '../main_shell.dart';
import '../more/caldav_account_screen.dart';
import '../../l10n/l10n.dart';

/// „überfällig“, „heute“, „morgen“, „Fr, 17.10.“ oder leer.
String taskDueLabel(Task t, {DateTime? now}) {
  if (t.due == null) return '';
  final n = now ?? DateTime.now();
  if (t.isOverdue(n)) return l10n.overdue;
  final label = dayLabel(t.due!, now: n);
  if (label == l10n.today || label == l10n.tomorrow) {
    final time = t.dueIsDate ? '' : ' ${timeLabel(t.due!)}';
    return '${label.toLowerCase()}$time';
  }
  return localDate('E, d.M.').format(t.due!);
}

class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});

  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends ConsumerState<TasksScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  Task? _selected;
  TaskView _selectedView = TaskView.mine;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(
      length: TaskView.values.length,
      vsync: this,
      initialIndex: TaskView.values.indexOf(ref.read(taskViewProvider)),
    );
    _tabs.addListener(() {
      if (!_tabs.indexIsChanging) {
        ref.read(taskViewProvider.notifier).state = TaskView.values[_tabs.index];
      }
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  /// No provider choice: the hub puts the task where the recipient works (own tasks: my preferred place,
  /// family tasks: the family list). Native Habitica types are created in the Habitica account screen.
  Future<void> _create() async {
    final view = ref.read(taskViewProvider);
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => ProtectedReadModal(
        provider: tasksProvider(view),
        child: const TaskCreateSheet(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Push-Ziel „/tasks?view=for_me“ schaltet den Reiter um
    ref.listen<TaskView>(taskViewProvider, (_, view) {
      final i = TaskView.values.indexOf(view);
      if (_tabs.index != i) _tabs.animateTo(i);
    });
    final wide = isWide(context);
    if (_selected != null) {
      ref.listen(tasksProvider(_selectedView), (_, next) {
        if (next.valueOrNull == null) setState(() => _selected = null);
      });
    }

    final lists = TabBarView(
      controller: _tabs,
      children: [
        for (final v in TaskView.values)
          _TaskList(
            view: v,
            selectedUid: wide ? _selected?.identity : null,
            onOpen: (t) => t.isHabitica ? (ref.read(canEditProvider) ? showNativeEditor(context, ref, t.account, task: t) : null) : wide ? setState(() {
              _selected = t;
              _selectedView = v;
            }) : _showDetails(t, v),
          ),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabTasks),
        actions: [ReadStatusIcon(result: ref.watch(tasksProvider(ref.watch(taskViewProvider))).valueOrNull),
          IconButton(
            key: const Key('tasks-show-done'),
            tooltip: ref.watch(showDoneTasksProvider) ? l10n.hideDone : l10n.showDone,
            icon: Icon(ref.watch(showDoneTasksProvider) ? Icons.visibility_off_outlined : Icons.visibility_outlined),
            onPressed: () => ref.read(showDoneTasksProvider.notifier).state = !ref.read(showDoneTasksProvider),
          ),
          if (ref.watch(canActProvider) && ref.watch(taskAccountsProvider).valueOrNull?.any((p) => p.id == 'habitica') == true)
          IconButton(tooltip: l10n.habiticaAccountSelection, icon: const Icon(Icons.account_tree_outlined), onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => ProtectedReadModal(
              provider: tasksProvider(TaskView.mine), child: const HabiticaAccountScreen())));
            ref.invalidate(taskAccountsProvider); await refreshTasks(ref);
          })],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: !wide,
          tabAlignment: wide ? TabAlignment.fill : TabAlignment.start,
          tabs: [for (final v in TaskView.values) Tab(text: v.label)],
        ),
      ),
      floatingActionButton: ref.watch(canEditProvider)
          ? FloatingActionButton.extended(
              onPressed: _create,
              icon: const Icon(Icons.add),
              label: Text(l10n.task),
            )
          : null,
      body: wide
          ? Row(
              children: [
                Expanded(flex: 5, child: lists),
                const VerticalDivider(width: 1),
                Expanded(
                  flex: 4,
                  child: _selected == null
                      ? EmptyHint(icon: Icons.touch_app_outlined, text: l10n.tapTaskForDetails)
                      : TaskDetails(task: _selected!, view: _selectedView, onClose: () => setState(() => _selected = null)),
                ),
              ],
            )
          : lists,
    );
  }

  void _showDetails(Task t, TaskView view) {
    if (t.isHabitica) {
      if (ref.read(canEditProvider)) showNativeEditor(context, ref, t.account, task: t);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (ctx) => ProtectedReadModal(
        provider: tasksProvider(view),
        child: TaskDetails(task: t, view: view, onClose: () => Navigator.pop(ctx)),
      ),
    );
  }
}

/// Erledigte Aufgaben einblenden (wie beim Einkauf). Standard: aus.
final showDoneTasksProvider = StateProvider<bool>((_) => false);

class _TaskList extends ConsumerStatefulWidget {
  final TaskView view;
  final String? selectedUid;
  final ValueChanged<Task> onOpen;

  const _TaskList({
    required this.view,
    required this.onOpen,
    this.selectedUid,
  });

  @override
  ConsumerState<_TaskList> createState() => _TaskListState();
}

class _TaskListState extends ConsumerState<_TaskList> {
  /// Weggewischte Aufgaben verschwinden sofort, nicht erst nach dem Neuladen.
  final _gone = <String>{};
  final _completing = <String>{};

  Future<bool> _complete(Task task) async {
    if (_completing.contains(task.identity)) return false;
    if (task.localOnly) {
      showInfo(context, l10n.createdWhenOnline);
      return false;
    }
    setState(() => _completing.add(task.identity));
    try {
      return await runChange(context, () => ref.read(apiClientProvider).completeTask(task.uid, provider: task.provider, account: task.account, title: task.title));
    } finally {
      if (mounted) setState(() => _completing.remove(task.identity));
    }
  }

  void _remove(Task task, {bool deleted = false}) {
    setState(() => _gone.add(task.identity));
    showInfo(context, '„${task.title}“ ${deleted ? 'gelöscht' : 'erledigt'}');
  }

  TaskView get view => widget.view;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(tasksProvider(view));
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    final names = {for (final p in people) p.id: p.displayName};
    final api = ref.read(apiClientProvider);
    Future<void> refresh() async { setState(() => _gone.clear()); await ref.read(tasksProvider(view).notifier).refresh(); }

    return HubRefresh(
      onRefresh: refresh,
      child: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: refresh),
        data: (result) {
          final data = result.data;
          // Erledigtes ist ausgeblendet – auch Habitica-Tägliche, die heute schon abgehakt sind
          final open = data.items.where((t) => !t.done && !_gone.contains(t.identity)).toList()
            ..sort((a, b) => (a.due ?? DateTime(9999)).compareTo(b.due ?? DateTime(9999)));
          final done = ref.watch(showDoneTasksProvider)
              ? data.items.where((t) => t.done && !_gone.contains(t.identity)).toList()
              : const <Task>[];
          final canAct = ref.watch(canActProvider);
          final canEdit = ref.watch(canEditProvider);
          final habiticaEnabled = canAct && !result.offline && !result.refreshing && result.refreshError == null;
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              SourceBanner(source: l10n.taskProvider, status: data.error != null ? SourceStatus.unavailable : data.status, error: data.error),
              if (data.status == SourceStatus.notConfigured && canAct)
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: FilledButton.tonal(
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => const CalDavAccountScreen())),
                    child: Text(l10n.addNextcloudAccount),
                  ),
                ),
              if (data.isOk && open.isEmpty)
                EmptyHint(icon: Icons.task_alt, text: _emptyText(view)),
              for (final t in open)
                Dismissible(
                  key: ValueKey('task-${view.apiName}-${t.identity}'),
                  direction: t.isHabitica || t.localOnly || t.readOnly || !canAct
                      ? DismissDirection.none
                      : canEdit ? DismissDirection.horizontal : DismissDirection.startToEnd,
                  background: _swipeBackground(context, Icons.check, l10n.done,
                      Colors.green.shade700, Alignment.centerLeft),
                  secondaryBackground: _swipeBackground(context, Icons.delete_outline,
                      l10n.delete, Theme.of(context).colorScheme.error, Alignment.centerRight),
                  confirmDismiss: (dir) async {
                    if (_completing.contains(t.identity)) return false;
                    if (dir == DismissDirection.startToEnd) {
                      return _complete(t);
                    }
                    final sure = await _confirmDelete(context, t);
                    if (!sure || !context.mounted) return false;
                    return runAction(context, () => api.deleteTask(t.uid, provider: t.provider, account: t.account));
                  },
                  onDismissed: (dir) => _remove(t, deleted: dir == DismissDirection.endToStart),
                  child: _tile(t, names, habiticaEnabled, canAct),
                ),
              if (done.isNotEmpty) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
                  child: Text(l10n.doneCount(done.length), style: Theme.of(context).textTheme.titleSmall),
                ),
                for (final t in done) _tile(t, names, habiticaEnabled, canAct),
              ],
            ],
          );
        },
      ),
    );
  }

  /// Eine Zeile für alle Anbieter: Haken immer links (Habitica-Gewohnheiten/Belohnungen: Symbol),
  /// rechts Fälligkeit bzw. +/−- oder Einlöse-Knopf.
  Widget _tile(Task t, Map<int, String> names, bool habiticaEnabled, bool canAct) {
    Future<void> changed() async => refreshTasks(ref);
    final Widget leading;
    if (t.readOnly) {
      // Given to someone else: the recipient completes it in her own place; here only the status
      leading = Checkbox(
        key: Key('assigned-check-${t.uid}'),
        shape: const CircleBorder(),
        value: t.done,
        semanticLabel: t.title,
        onChanged: null,
      );
    } else if (t.isHabitica && habiticaCheckable(t)) {
      leading = HabiticaTaskButtons(task: t, part: HabiticaPart.check, enabled: habiticaEnabled, onChanged: changed);
    } else if (t.isHabitica) {
      leading = SizedBox(
        width: 48,
        child: Icon(t.native['type'] == 'reward' ? Icons.redeem : Icons.auto_awesome_outlined,
            color: Theme.of(context).colorScheme.onSurfaceVariant),
      );
    } else {
      leading = Checkbox(
        shape: const CircleBorder(),
        value: t.done,
        semanticLabel: l10n.completeTitle(t.title),
        onChanged: !canAct || t.done || _completing.contains(t.identity) || t.localOnly ? null : (_) async {
          if (await _complete(t) && mounted) _remove(t);
        },
      );
    }
    final Widget? trailing = t.localOnly
        ? Tooltip(message: l10n.waitingForNetwork, child: Icon(Icons.cloud_upload_outlined, key: Key('pending-task-${t.uid}')))
        : t.isHabitica && !habiticaCheckable(t)
            ? HabiticaTaskButtons(task: t, part: HabiticaPart.actions, enabled: habiticaEnabled, onChanged: changed)
            : _dueChip(context, t);
    return ListTile(
      key: ValueKey('task-tile-${view.apiName}-${t.identity}'),
      contentPadding: const EdgeInsets.only(left: 4, right: 12),
      leading: leading,
      selected: t.identity == widget.selectedUid,
      title: Text(t.title,
          style: t.done ? TextStyle(decoration: TextDecoration.lineThrough, color: Theme.of(context).colorScheme.onSurfaceVariant) : null),
      subtitle: _subtitle(t, names),
      trailing: trailing,
      onTap: t.localOnly ? null : () => widget.onOpen(t),
    );
  }

  static String _emptyText(TaskView v) => switch (v) {
        TaskView.mine => l10n.noOpenTasks,
        TaskView.forMe => l10n.nothingAssignedToYou,
        TaskView.fromMe => l10n.youAssignedNothing,
        TaskView.family => l10n.noFamilyTasks,
      };

  Widget? _subtitle(Task t, Map<int, String> names) {
    final parts = <String>[
      if ((view == TaskView.forMe && t.createdBy != null) ||
          (view == TaskView.mine && t.createdBy != null && t.createdBy != ref.read(sessionProvider).user?.id))
        l10n.fromName(names[t.createdBy] ?? l10n.someoneDat),
      if (view == TaskView.fromMe && t.assignee != null) l10n.forName(names[t.assignee] ?? l10n.someoneAcc),
      if (view == TaskView.family && t.assignee != null) l10n.forName(names[t.assignee] ?? l10n.someoneAcc),
      if (t.listName != null && view != TaskView.mine) t.listName!,
      // Quelle nur, wenn sie hilft (Habitica-Typ); keine internen Konto-IDs
      if (t.readOnly && t.via != null) l10n.taskAssignedVia(taskPlaceName(t.via!)),
      if (t.readOnly && t.stale) l10n.taskStatusUnknown,
      if (t.isHabitica) habiticaLabel(t),
      if (t.isHabitica && t.native['type'] == 'reward') '${t.native['value']} GP',
      if (t.rotation.isNotEmpty) reminderRecurrences[t.recurrence] ?? t.recurrence,
    ];
    return parts.isEmpty ? null : Text(parts.join(' · '));
  }

  Widget? _dueChip(BuildContext context, Task t) {
    final label = taskDueLabel(t);
    if (label.isEmpty) return null;
    final overdue = t.isOverdue(DateTime.now());
    return Text(label,
        style: TextStyle(
            color: overdue ? Theme.of(context).colorScheme.error : Theme.of(context).colorScheme.onSurfaceVariant));
  }

  static Widget _swipeBackground(
      BuildContext context, IconData icon, String text, Color color, Alignment align) {
    return Container(
      color: color,
      alignment: align,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [Icon(icon, color: Colors.white), const SizedBox(width: 8), Text(text, style: const TextStyle(color: Colors.white))],
      ),
    );
  }

  Future<bool> _confirmDelete(BuildContext context, Task t) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => ProtectedReadModal(
        provider: tasksProvider(view),
        child: AlertDialog(
        title: Text(l10n.deleteTaskQuestion),
        content: Text(l10n.deletedPermanently(t.title)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
        ),
      ),
    );
    return ok == true;
  }
}

class TaskDetails extends ConsumerWidget {
  final Task task;
  final TaskView view;
  final VoidCallback onClose;
  const TaskDetails({super.key, required this.task, this.view = TaskView.mine, required this.onClose});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final task = ref.watch(tasksProvider(view)).valueOrNull?.data.items
        .where((item) => item.identity == this.task.identity).firstOrNull;
    if (task == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    final names = {for (final p in people) p.id: p.displayName};
    final due = taskDueLabel(task);
    return ListView(
      padding: const EdgeInsets.all(20),
      shrinkWrap: true,
      children: [
        Row(
          children: [
            Expanded(child: Text(task.title, style: theme.textTheme.titleLarge)),
            IconButton(onPressed: onClose, icon: const Icon(Icons.close), tooltip: l10n.close),
          ],
        ),
        if (ref.watch(canEditProvider) && !task.readOnly)
        TextButton.icon(icon: const Icon(Icons.edit_outlined), label: Text(l10n.editTask), onPressed: () async {
          final changed = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true,
            builder: (_) => ProtectedReadModal(provider: tasksProvider(view), child: TaskEditSheet(task: task)));
          if (changed == true) { await refreshTasks(ref); onClose(); }
        }),
        if (task.notes.isNotEmpty) ...[const SizedBox(height: 8), Text(task.notes)],
        const SizedBox(height: 12),
        if (due.isNotEmpty) _info(Icons.schedule, l10n.dueLabel(due)),
        if (task.assignee != null) _info(Icons.person_outline, l10n.forLabel(names[task.assignee] ?? task.assignee!)),
        if (task.createdBy != null) _info(Icons.edit_outlined, l10n.fromLabel(names[task.createdBy] ?? task.createdBy!)),
        if (task.listName != null) _info(Icons.list_alt, l10n.listLabel(task.listName!)),
        if (task.rotation.isNotEmpty) ...[
          _info(Icons.repeat, reminderRecurrences[task.recurrence] ?? task.recurrence),
          _info(Icons.people_outline, l10n.rotationLabel(task.rotation.map((id) => names[id] ?? '#$id').join(' → '))),
          Text(l10n.rotationExplain),
        ],
      ],
    );
  }

  Widget _info(IconData icon, String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [Icon(icon, size: 18), const SizedBox(width: 8), Expanded(child: Text(text))]),
      );
}

/// Schnell anlegen: Titel, für wen, optional Fälligkeit.
class TaskCreateSheet extends ConsumerStatefulWidget {
  const TaskCreateSheet({super.key});

  @override
  ConsumerState<TaskCreateSheet> createState() => _TaskCreateSheetState();
}

/// Auswahl „für wen“: ich selbst, eine Person oder die Familienliste.
sealed class _Target {
  const _Target();
}

class _Me extends _Target {
  const _Me();
}

class _FamilyList extends _Target {
  const _FamilyList();
}

class _PersonTarget extends _Target {
  final Person person;
  const _PersonTarget(this.person);
}

class _TaskCreateSheetState extends ConsumerState<TaskCreateSheet> {
  final _title = TextEditingController();
  _Target _target = const _Me();
  DateTime? _due;
  bool _saving = false;
  bool _household = false;
  String _recurrence = 'weekly';
  final _rotation = <int>[];

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    if (title.isEmpty) return;
    if (_household && _rotation.isEmpty) {
      showInfo(context, l10n.rotationNeedsPerson);
      return;
    }
    setState(() => _saving = true);
    final target = _target;
    final meId = ref.read(sessionProvider).user?.id;
    final ok = await runChange(
      context,
      () async => await ref.read(apiClientProvider).createTask(
            title: title,
            due: _due,
            assigneeId: !_household && target is _PersonTarget ? target.person.id : null,
            family: _household || target is _FamilyList,
            recurrence: _household ? _recurrence : 'none',
            rotation: _household ? List.of(_rotation) : const [],
            meId: meId,
          ) != null,
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) Navigator.pop(context, true);
  }

  Future<void> _pickDue() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _due ?? now,
      firstDate: now.subtract(const Duration(days: 365)),
      lastDate: now.add(const Duration(days: 365 * 3)),
    );
    if (picked != null) setState(() => _due = picked);
  }

  @override
  Widget build(BuildContext context) {
    final me = ref.watch(sessionProvider).user;
    final allPeople = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    final people = allPeople
        .where((p) => p.id != me?.id)
        .toList();
    final chips = <(String, _Target)>[
      (l10n.me, const _Me()),
      for (final p in people) (p.displayName, _PersonTarget(p)),
      (l10n.family, const _FamilyList()),
    ];
    bool isSelected(_Target t) => switch ((t, _target)) {
          (_Me(), _Me()) => true,
          (_FamilyList(), _FamilyList()) => true,
          (_PersonTarget a, _PersonTarget b) => a.person.id == b.person.id,
          _ => false,
        };

    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.shortcutNewTask, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          TextField(
            key: const Key('task-title'),
            controller: _title,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.whatToDo),
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: 16),
          SwitchListTile(
            key: const Key('household-toggle'),
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.householdRotation),
            subtitle: Text(l10n.householdRotationHint),
            value: _household,
            onChanged: _saving ? null : (value) => setState(() {
              _household = value;
              if (value) _due ??= DateTime.now();
            }),
          ),
          if (_household) ...[
            DropdownButtonFormField<String>(
              initialValue: _recurrence,
              decoration: InputDecoration(labelText: l10n.repeat),
              items: [for (final entry in reminderRecurrences.entries)
                if (entry.key != 'none') DropdownMenuItem(value: entry.key, child: Text(entry.value))],
              onChanged: _saving ? null : (value) => setState(() => _recurrence = value!),
            ),
            const SizedBox(height: 12),
            Text(l10n.rotationTapHint),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final person in allPeople)
                FilterChip(
                  key: Key('rotation-${person.id}'),
                  label: Text('${_rotation.contains(person.id) ? '${_rotation.indexOf(person.id) + 1}. ' : ''}${person.displayName}'),
                  selected: _rotation.contains(person.id),
                  onSelected: _saving ? null : (selected) => setState(() {
                    if (selected) { _rotation.add(person.id); } else { _rotation.remove(person.id); }
                  }),
                ),
            ]),
          ] else ...[
          Text(l10n.forWhom),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final (label, target) in chips)
                ChoiceChip(
                  label: Text(label),
                  selected: isSelected(target),
                  onSelected: (_) => setState(() => _target = target),
                ),
            ],
          ),
          if (_target case _PersonTarget(:final person))
            Padding(
              key: const Key('task-lands-hint'),
              padding: const EdgeInsets.only(top: 8),
              child: Text(l10n.taskLandsWhereTheyWork(person.displayName),
                  style: Theme.of(context).textTheme.bodySmall),
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            children: [
              TextButton.icon(
                onPressed: _pickDue,
                icon: const Icon(Icons.event),
                label: Text(_due == null ? l10n.dueDate : localDate('EEE, d. MMM').format(_due!)),
              ),
              if (_due != null && !_household)
                IconButton(
                  tooltip: l10n.removeDueDate,
                  onPressed: () => setState(() => _due = null),
                  icon: const Icon(Icons.clear),
                ),
              FilledButton(
                key: const Key('task-save'),
                onPressed: _saving ? null : _save,
                child: Text(l10n.create),
              ),
            ],
          ),
        ],
      )),
    );
  }
}


class TaskEditSheet extends ConsumerStatefulWidget {
  final Task task;
  const TaskEditSheet({super.key, required this.task});
  @override
  ConsumerState<TaskEditSheet> createState() => _TaskEditState();
}

class _TaskEditState extends ConsumerState<TaskEditSheet> {
  late final TextEditingController _title, _notes;
  late DateTime? _due;
  late int? _priority;
  bool _busy = false;
  @override
  void initState() { super.initState(); _title = TextEditingController(text: widget.task.title); _notes = TextEditingController(text: widget.task.notes); _due = widget.task.due; _priority = widget.task.priority; }
  @override
  void dispose() { _title.dispose(); _notes.dispose(); super.dispose(); }
  Future<void> _save() async {
    setState(() => _busy = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).updateTask(widget.task, title: _title.text, notes: _notes.text, due: _due, priority: _priority));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.pop(context, true);
  }
  @override
  Widget build(BuildContext context) => Padding(padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom), child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
    Text(l10n.editTask), TextField(controller: _title, decoration: InputDecoration(labelText: l10n.title)),
    TextField(controller: _notes, decoration: InputDecoration(labelText: l10n.notes)),
    DropdownButtonFormField<int>(initialValue: _priority ?? 0, decoration: InputDecoration(labelText: l10n.caldavPriority), items: [for (final p in [0,1,2,3,4,5,6,7,8,9]) DropdownMenuItem(value: p, child: Text('$p'))], onChanged: _busy ? null : (v) => _priority = v),
    Row(children: [TextButton(onPressed: _busy ? null : () async { final date = await showDatePicker(context: context, initialDate: _due ?? DateTime.now(), firstDate: DateTime(2000), lastDate: DateTime(2100)); if (date != null) setState(() => _due = date); }, child: Text(_due == null ? l10n.dueDate : dayLabel(_due!))),
      IconButton(onPressed: _busy ? null : () => setState(() => _due = null), icon: const Icon(Icons.clear), tooltip: l10n.removeDueDate)]),
    FilledButton(onPressed: _busy ? null : _save, child: Text(l10n.save)),
  ])));
}
