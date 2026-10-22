part of 'timetable_screen.dart';

/// One calendar week with real dates for a child whose lessons come from a plugin: cancelled lessons are struck
/// through, substitutions highlighted. Fails softly: the server falls back to the entered timetable.
class _PluginWeek extends ConsumerWidget {
  final int childId;
  final TimetablePluginInfo plugin;
  final DateTime start;
  final void Function(int days) onShift;
  final VoidCallback onToday;
  const _PluginWeek({required this.childId, required this.plugin, required this.start, required this.onShift, required this.onToday});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final async = ref.watch(timetableWeekProvider((childId: childId, start: start)));
    final fmt = localDate('d. MMM');
    final end = start.add(const Duration(days: 6));
    return Column(
      key: const Key('timetable-plugin-week'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),
        Row(children: [
          IconButton(
            key: const Key('timetable-prev-week'),
            tooltip: l10n.timetablePrevWeek,
            icon: const Icon(Icons.chevron_left),
            onPressed: () => onShift(-7),
          ),
          Expanded(
            child: TextButton(
              key: const Key('timetable-this-week'),
              onPressed: onToday,
              child: Text(l10n.timetableWeekRange(fmt.format(start), fmt.format(end)), textAlign: TextAlign.center),
            ),
          ),
          IconButton(
            key: const Key('timetable-next-week'),
            tooltip: l10n.timetableNextWeek,
            icon: const Icon(Icons.chevron_right),
            onPressed: () => onShift(7),
          ),
        ]),
        Text(l10n.timetableFromPlugin(plugin.name), style: muted),
        async.when(
          loading: () => const Padding(padding: EdgeInsets.all(24), child: Center(child: HubLoader())),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(timetableWeekProvider)),
          data: (week) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (week.plugin?.unavailable ?? false)
              Card(
                key: const Key('timetable-plugin-unavailable'),
                margin: const EdgeInsets.only(top: 12),
                child: ListTile(
                  leading: const Icon(Icons.cloud_off_outlined),
                  title: Text(l10n.timetablePluginUnavailable(plugin.name)),
                ),
              ),
            for (final d in week.days)
              if (d.weekday < 5 || d.entries.isNotEmpty) _dayBlock(context, d),
          ]),
        ),
      ],
    );
  }

  Widget _dayBlock(BuildContext context, TimetableDay d) {
    final theme = Theme.of(context);
    return Column(
      key: Key('timetable-date-${d.date.year}-${d.date.month}-${d.date.day}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Text(localDate('EEEE, d. MMM').format(d.date), style: theme.textTheme.titleMedium),
        if (d.holiday != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(children: [
              const Icon(Icons.beach_access_outlined, size: 18),
              const SizedBox(width: 6),
              Expanded(child: Text(d.holiday == '-' ? l10n.timetableHolidays : '${l10n.timetableHolidays}: ${d.holiday}')),
            ]),
          ),
        if (d.entries.isEmpty && d.holiday == null)
          Text(l10n.timetableEmptyDay, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant))
        else
          for (final e in d.entries) _LessonTile(entry: e),
      ],
    );
  }
}


/// A dated lesson: cancelled ones struck through, substitutions highlighted, with the note under it.
class _LessonTile extends StatelessWidget {
  final TimetableEntry entry;
  const _LessonTile({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final e = entry;
    final background = e.isCancelled ? scheme.errorContainer : (e.isChanged ? scheme.tertiaryContainer : null);
    final foreground = e.isCancelled ? scheme.onErrorContainer : (e.isChanged ? scheme.onTertiaryContainer : null);
    final details = [
      '${e.start}–${e.end}',
      if (e.location != null && e.location!.isNotEmpty) e.location!,
      if (e.teacher != null && e.teacher!.isNotEmpty) e.teacher!,
    ].join(' · ');
    final status = e.status == 'normal' ? null : [_statusLabel(e.status), if (e.note != null && e.note!.isNotEmpty) e.note!].join(' · ');
    return Card(
      color: background,
      margin: const EdgeInsets.only(top: 4),
      child: ListTile(
        key: Key('timetable-lesson-${e.date?.day ?? 0}-${e.start}-${e.status}'),
        iconColor: foreground,
        textColor: foreground,
        leading: Icon(_kindIcon(e.kind)),
        title: Text(
          e.title,
          style: e.isCancelled ? const TextStyle(decoration: TextDecoration.lineThrough) : null,
        ),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(details),
          if (status != null) Text(status, style: const TextStyle(fontWeight: FontWeight.w600)),
        ]),
      ),
    );
  }
}
