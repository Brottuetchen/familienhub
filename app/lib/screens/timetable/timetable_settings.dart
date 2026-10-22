part of 'timetable_screen.dart';

class _SettingsSheet extends ConsumerStatefulWidget {
  final TimetableSettings settings;
  const _SettingsSheet({required this.settings});

  @override
  ConsumerState<_SettingsSheet> createState() => _SettingsSheetState();
}


class _SettingsSheetState extends ConsumerState<_SettingsSheet> {
  late DateTime? _reference = widget.settings.abReference;
  late String? _feed = widget.settings.feeds.any((f) => f.id == widget.settings.holidayFeed) ? widget.settings.holidayFeed : null;
  bool _busy = false;

  Future<void> _pickWeek() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _reference ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 2),
      helpText: l10n.timetablePickWeek,
    );
    if (picked != null) setState(() => _reference = picked);
  }

  Future<void> _save() async {
    final api = ref.read(apiClientProvider);
    setState(() => _busy = true);
    final ok = await runAction(context, () => api.saveTimetableSettings(abReference: _reference, holidayFeed: _feed));
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(l10n.timetableSettings, style: theme.textTheme.titleLarge),
        const SizedBox(height: 12),
        SwitchListTile(
          key: const Key('timetable-ab-switch'),
          contentPadding: EdgeInsets.zero,
          title: Text(l10n.timetableAbWeeks),
          value: _reference != null,
          onChanged: (on) => setState(() => _reference = on ? (_reference ?? DateTime.now()) : null),
        ),
        Text(l10n.timetableAbWeeksHelp, style: muted),
        if (_reference != null)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const Key('timetable-ab-date'),
              onPressed: _pickWeek,
              icon: const Icon(Icons.event),
              label: Text(l10n.timetableAbReference(localDate('d. MMM yyyy').format(_reference!))),
            ),
          ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String?>(
          key: const Key('timetable-feed'),
          initialValue: _feed,
          isExpanded: true,
          decoration: InputDecoration(labelText: l10n.timetableHolidayFeed),
          items: [
            DropdownMenuItem<String?>(value: null, child: Text(l10n.timetableHolidayFeedNone)),
            for (final f in widget.settings.feeds) DropdownMenuItem<String?>(value: f.id, child: Text(f.name)),
          ],
          onChanged: (v) => setState(() => _feed = v),
        ),
        const SizedBox(height: 4),
        Text(l10n.timetableHolidayFeedHelp, style: muted),
        const SizedBox(height: 12),
        Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, children: [
          TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: Text(l10n.cancel)),
          FilledButton(key: const Key('timetable-settings-save'), onPressed: _busy ? null : _save, child: Text(l10n.save)),
        ]),
      ]),
    );
  }
}
