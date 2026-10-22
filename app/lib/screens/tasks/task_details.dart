part of 'tasks_screen.dart';

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
