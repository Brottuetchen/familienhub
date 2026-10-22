part of 'calendar_screen.dart';

class _EventTile extends ConsumerWidget {
  final CalendarEvent event;
  const _EventTile({required this.event});

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(l10n.deleteEventQuestion(event.title)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteEvent(event.id!))) {
      await ref.read(eventsProvider.notifier).refresh();
    }
  }


  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final deletable = event.source == 'hub' && event.id != null && ref.watch(canEditProvider);
    final time = event.allDay || event.start == null
        ? l10n.allDayLower
        : event.end == null
            ? timeLabel(event.start!)
            : '${timeLabel(event.start!)} – ${timeLabel(event.end!)}';
    final sub = [time, if (event.location != null) event.location!, if (event.calendar != null) event.calendar!];
    return ListTile(
      leading: Container(width: 4, height: 36, decoration: BoxDecoration(color: eventColor(context, event, ref.watch(calendarColorsProvider)), borderRadius: BorderRadius.circular(2))),
      title: Text(event.title),
      subtitle: Text(sub.join(' · ')),
      onTap: () => showModalBottomSheet<void>(
        context: context,
        useSafeArea: true,
        isScrollControlled: true,
        builder: (_) => EventDetailsSheet(event: event),
      ),
      trailing: deletable
          ? IconButton(
              key: ValueKey('event-delete-${event.id}'),
              tooltip: l10n.deleteEvent,
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _delete(context, ref),
            )
          : null,
    );
  }
}
