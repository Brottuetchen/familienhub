part of 'calendar_screen.dart';

/// Details of an event; edit and delete where the person may (hub family calendar, own CalDAV calendars).
class EventDetailsSheet extends ConsumerWidget {
  final CalendarEvent event;
  const EventDetailsSheet({super.key, required this.event});

  bool _editable(WidgetRef ref) {
    if (!ref.watch(canEditProvider)) return false;
    if (event.source == 'hub') return event.id != null;
    if (event.source != 'caldav' || event.uid == null || event.calendarId == null) return false;
    final cals = ref.watch(calendarsProvider).valueOrNull ?? const <CalendarInfo>[];
    return cals.any((c) => c.id == event.calendarId && c.writable);
  }

  String _when() {
    final s = event.start;
    if (s == null) return '';
    final e = event.end;
    if (event.allDay) {
      final lastDay = e == null ? s : e.subtract(const Duration(days: 1));
      return lastDay.isAfter(s) ? '${dayLabel(s)} – ${dayLabel(lastDay)} · ${l10n.allDayLower}' : '${dayLabel(s)} · ${l10n.allDayLower}';
    }
    if (e == null) return '${dayLabel(s)}, ${timeLabel(s)}';
    final sameDay = s.year == e.year && s.month == e.month && s.day == e.day;
    return sameDay ? '${dayLabel(s)}, ${timeLabel(s)} – ${timeLabel(e)}' : '${dayLabel(s)}, ${timeLabel(s)} – ${dayLabel(e)}, ${timeLabel(e)}';
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(event.recurring ? l10n.deleteSeriesQuestion(event.title) : l10n.deleteEventPlain(event.title)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteAnyEvent(event))) {
      ref.invalidate(eventsProvider);
      ref.invalidate(eventsRangeProvider);
      if (context.mounted) Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final colors = ref.watch(calendarColorsProvider);
    final editable = _editable(ref);
    Widget row(IconData icon, String text) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, size: 20, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: 12),
            Expanded(child: Text(text)),
          ]),
        );
    final repeat = event.recurrence != 'none'
        ? switch (event.recurrence) {
            'daily' => l10n.recurDaily, 'weekly' => l10n.recurWeekly, 'monthly' => l10n.recurMonthly,
            'yearly' => l10n.recurYearly, _ => event.recurrence }
        : event.recurring ? l10n.partOfSeries : null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 6, height: 28, decoration: BoxDecoration(color: eventColor(context, event, colors), borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 12),
          Expanded(child: Text(event.title, style: theme.textTheme.titleLarge)),
          IconButton(tooltip: l10n.close, onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
        ]),
        const SizedBox(height: 8),
        row(Icons.schedule, _when()),
        if (event.alarmMinutes != null) row(Icons.notifications_none, alarmLabel(event.alarmMinutes!)),
        if (event.calendar != null) row(Icons.calendar_month_outlined, event.calendar!),
        if (repeat != null) row(Icons.repeat, repeat),
        if (event.location != null && event.location!.isNotEmpty) row(Icons.place_outlined, event.location!),
        if (event.notes != null && event.notes!.isNotEmpty) row(Icons.notes, event.notes!),
        if (editable) ...[
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.spaceBetween, children: [
            FilledButton.tonalIcon(
              key: const Key('event-edit'),
              icon: const Icon(Icons.edit_outlined),
              label: Text(l10n.editEvent),
              onPressed: () async {
                Navigator.pop(context);
                await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true,
                    builder: (_) => EventCreateSheet(initial: event));
              },
            ),
            TextButton.icon(
              key: const Key('event-details-delete'),
              icon: const Icon(Icons.delete_outline),
              label: Text(l10n.delete),
              onPressed: () => _delete(context, ref),
            ),
          ]),
        ],
      ]),
    );
  }
}
