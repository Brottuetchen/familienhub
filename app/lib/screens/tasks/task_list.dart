part of 'tasks_screen.dart';

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
              NamedListSections(kind: 'tasks', showDone: ref.watch(showDoneTasksProvider)),
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
      if (t.stars > 0) l10n.starsCount(t.stars),
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
