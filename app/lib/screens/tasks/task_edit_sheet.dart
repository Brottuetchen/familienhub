part of 'tasks_screen.dart';

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
  late int _stars = widget.task.stars;
  bool _busy = false;
  @override
  void initState() { super.initState(); _title = TextEditingController(text: widget.task.title); _notes = TextEditingController(text: widget.task.notes); _due = widget.task.due; _priority = widget.task.priority; }
  @override
  void dispose() { _title.dispose(); _notes.dispose(); super.dispose(); }
  Future<void> _save() async {
    setState(() => _busy = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).updateTask(widget.task, title: _title.text, notes: _notes.text, due: _due, priority: _priority, stars: widget.task.isHabitica ? null : _stars));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.pop(context, true);
  }
  Future<void> _pickDue() async {
    final date = await showDatePicker(context: context, initialDate: _due ?? DateTime.now(), firstDate: DateTime(2000), lastDate: DateTime(2100));
    if (date != null) setState(() => _due = date);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Every field has its own full-width row with a gap; nothing is placed next to another widget, so labels,
    // values and buttons cannot overlap at any width or text size.
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(l10n.editTask, style: theme.textTheme.titleLarge),
          const SizedBox(height: 16),
          TextField(key: const Key('edit-title'), controller: _title, decoration: InputDecoration(labelText: l10n.title)),
          const SizedBox(height: 16),
          TextField(key: const Key('edit-notes'), controller: _notes, minLines: 1, maxLines: 4,
              keyboardType: TextInputType.multiline, decoration: InputDecoration(labelText: l10n.notes)),
          const SizedBox(height: 16),
          DropdownButtonFormField<int>(
            key: const Key('edit-priority'),
            isExpanded: true,
            initialValue: _priority ?? 0,
            decoration: InputDecoration(labelText: widget.task.provider == 'nextcloud' ? l10n.caldavPriority : l10n.taskPriority),
            items: [for (final p in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) DropdownMenuItem(value: p, child: Text('$p'))],
            onChanged: _busy ? null : (v) => setState(() => _priority = v),
          ),
          if (!widget.task.isHabitica) ...[
            const SizedBox(height: 16),
            DropdownButtonFormField<int>(
              key: const Key('edit-stars'),
              isExpanded: true,
              initialValue: _stars,
              decoration: InputDecoration(labelText: l10n.taskStars),
              items: [for (final n in {..._starOptions, _stars}.toList()..sort()) DropdownMenuItem(value: n, child: Text('$n'))],
              onChanged: _busy ? null : (v) => setState(() => _stars = v ?? 0),
            ),
          ],
          const SizedBox(height: 8),
          ListTile(
            key: const Key('edit-due'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.event),
            title: Text(_due == null ? l10n.dueDate : dayLabel(_due!)),
            onTap: _busy ? null : _pickDue,
            trailing: IconButton(onPressed: _busy || _due == null ? null : () => setState(() => _due = null),
                icon: const Icon(Icons.clear), tooltip: l10n.removeDueDate),
          ),
          const SizedBox(height: 8),
          FilledButton(key: const Key('edit-save'), onPressed: _busy ? null : _save, child: Text(l10n.save)),
        ]),
      ),
    );
  }
}
