part of 'timetable_screen.dart';

class _EntrySheet extends ConsumerStatefulWidget {
  final int childId;
  final TimetableEntry? entry;
  final int weekday;
  final String week;
  final bool abWeeks;
  const _EntrySheet({required this.childId, required this.entry, required this.weekday, required this.week, required this.abWeeks});

  @override
  ConsumerState<_EntrySheet> createState() => _EntrySheetState();
}


class _EntrySheetState extends ConsumerState<_EntrySheet> {
  late final _title = TextEditingController(text: widget.entry?.title ?? '');
  late final _place = TextEditingController(text: widget.entry?.location ?? '');
  late String _kind = widget.entry?.kind ?? 'school';
  late String _start = widget.entry?.start ?? '08:00';
  late String _end = widget.entry?.end ?? '09:00';
  late int _weekday = widget.weekday;
  late String _week = widget.week;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _place.dispose();
    super.dispose();
  }

  Future<void> _pick(bool start) async {
    final cur = (start ? _start : _end).split(':');
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: int.tryParse(cur[0]) ?? 8, minute: int.tryParse(cur.length > 1 ? cur[1] : '0') ?? 0),
    );
    if (picked == null) return;
    final text = '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
    setState(() => start ? _start = text : _end = text);
  }

  Future<void> _save() async {
    if (_title.text.trim().isEmpty) return;
    if (_end.compareTo(_start) <= 0) {
      setState(() => _error = l10n.timetableEndAfterStart);
      return;
    }
    final api = ref.read(apiClientProvider);
    setState(() => _busy = true);
    final ok = await runAction(context, () => api.saveTimetableEntry({
          if (widget.entry == null) 'child_id': widget.childId,
          'weekday': _weekday,
          'week': _week,
          'start': _start,
          'end': _end,
          'title': _title.text.trim(),
          'kind': _kind,
          'location': _place.text.trim().isEmpty ? null : _place.text.trim(),
        }, id: widget.entry?.id));
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    final api = ref.read(apiClientProvider);
    setState(() => _busy = true);
    final ok = await runAction(context, () => api.deleteTimetableEntry(widget.entry!.id));
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(widget.entry == null ? l10n.timetableAddEntry : l10n.timetableEditEntry,
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        TextField(
          key: const Key('timetable-title'),
          controller: _title,
          maxLength: 80,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(labelText: l10n.title),
        ),
        DropdownButtonFormField<String>(
          key: const Key('timetable-kind'),
          initialValue: _kind,
          isExpanded: true,
                    items: [for (final k in timetableKinds) DropdownMenuItem(value: k, child: Text(_kindLabel(k)))],
          onChanged: (v) => setState(() => _kind = v ?? _kind),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<int>(
          key: const Key('timetable-weekday'),
          initialValue: _weekday,
          isExpanded: true,
          decoration: InputDecoration(labelText: l10n.timetableDay),
          items: [for (var d = 0; d < 7; d++) DropdownMenuItem(value: d, child: Text(_dayName(d)))],
          onChanged: (v) => setState(() => _weekday = v ?? _weekday),
        ),
        if (widget.abWeeks) ...[
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            key: const Key('timetable-week'),
            initialValue: _week,
            isExpanded: true,
            items: [for (final w in timetableWeeks) DropdownMenuItem(value: w, child: Text(_weekLabel(w)))],
            onChanged: (v) => setState(() => _week = v ?? _week),
          ),
        ],
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const Key('timetable-start'),
            onPressed: () => _pick(true),
            icon: const Icon(Icons.schedule),
            label: Text('${l10n.timetableStart} $_start'),
          ),
          OutlinedButton.icon(
            key: const Key('timetable-end'),
            onPressed: () => _pick(false),
            icon: const Icon(Icons.schedule),
            label: Text('${l10n.timetableEnd} $_end'),
          ),
        ]),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        TextField(
          key: const Key('timetable-place'),
          controller: _place,
          maxLength: 80,
          decoration: InputDecoration(labelText: l10n.timetableLocationOptional),
        ),
        const SizedBox(height: 8),
        Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, children: [
          if (widget.entry != null)
            TextButton(key: const Key('timetable-delete'), onPressed: _busy ? null : _delete, child: Text(l10n.delete)),
          TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: Text(l10n.cancel)),
          FilledButton(key: const Key('timetable-save'), onPressed: _busy ? null : _save, child: Text(l10n.save)),
        ]),
      ]),
    );
  }
}
