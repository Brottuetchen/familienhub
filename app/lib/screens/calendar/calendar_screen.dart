import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/calendar_event.dart';
import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';
import '../more/caldav_account_screen.dart';
import '../../l10n/l10n.dart';

class CalendarScreen extends ConsumerWidget {
  const CalendarScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(eventsProvider);
    Future<void> refresh() => ref.read(eventsProvider.notifier).refresh();

    return Scaffold(
      appBar: AppBar(title: Text(l10n.tabCalendar), actions: [ReadStatusIcon(result: async.valueOrNull)]),
      floatingActionButton: !ref.watch(canEditProvider) ? null : FloatingActionButton.extended(
        onPressed: () async {
          await showModalBottomSheet<bool>(
            context: context,
            isScrollControlled: true,
            useSafeArea: true,
            builder: (_) => const EventCreateSheet(),
          );
        },
        icon: const Icon(Icons.add),
        label: Text(l10n.event),
      ),
      body: HubRefresh(
        onRefresh: refresh,
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: refresh),
          data: (result) {
            final byDay = <DateTime, List<CalendarEvent>>{};
            for (final e in result.data.where((e) => e.start != null)) {
              final d = DateTime(e.start!.year, e.start!.month, e.start!.day);
              byDay.putIfAbsent(d, () => []).add(e);
            }
            final days = byDay.keys.toList()..sort();
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: 96),
              children: [
                if (days.isEmpty)
                  EmptyHint(icon: Icons.event_available, text: l10n.noEvents30),
                for (final day in days) ...[
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 18, 16, 4),
                    child: Text(dayLabel(day), style: Theme.of(context).textTheme.titleSmall),
                  ),
                  for (final e in byDay[day]!) _EventTile(event: e),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

class _EventTile extends StatelessWidget {
  final CalendarEvent event;
  const _EventTile({required this.event});

  Color _color(BuildContext context) {
    final hex = event.color?.replaceFirst('#', '');
    final value = hex != null && hex.length >= 6 ? int.tryParse(hex.substring(0, 6), radix: 16) : null;
    return value == null ? Theme.of(context).colorScheme.primary : Color(0xFF000000 | value);
  }

  @override
  Widget build(BuildContext context) {
    final time = event.allDay || event.start == null
        ? l10n.allDayLower
        : event.end == null
            ? timeLabel(event.start!)
            : '${timeLabel(event.start!)} – ${timeLabel(event.end!)}';
    final sub = [time, if (event.location != null) event.location!, if (event.calendar != null) event.calendar!];
    return ListTile(
      leading: Container(width: 4, height: 36, decoration: BoxDecoration(color: _color(context), borderRadius: BorderRadius.circular(2))),
      title: Text(event.title),
      subtitle: Text(sub.join(' · ')),
    );
  }
}

class EventCreateSheet extends ConsumerStatefulWidget {
  const EventCreateSheet({super.key});

  @override
  ConsumerState<EventCreateSheet> createState() => _EventCreateSheetState();
}

class _EventCreateSheetState extends ConsumerState<EventCreateSheet> {
  final _title = TextEditingController();
  DateTime _day = DateTime.now();
  TimeOfDay _start = TimeOfDay(hour: (TimeOfDay.now().hour + 1) % 24, minute: 0);
  Duration _length = const Duration(hours: 1);
  bool _allDay = false;
  bool _saving = false;

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    if (title.isEmpty) return;
    final start = _allDay
        ? DateTime(_day.year, _day.month, _day.day)
        : DateTime(_day.year, _day.month, _day.day, _start.hour, _start.minute);
    // Ganztägig: Ende ist der Folgetag (iCalendar DTEND exklusiv)
    final end = _allDay ? start.add(const Duration(days: 1)) : start.add(_length);
    setState(() => _saving = true);
    try {
      await ref.read(apiClientProvider).createEvent(title: title, start: start, end: end, allDay: _allDay);
      if (mounted) Navigator.pop(context, true);
    } on NoCalDavAccountException catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showError(context, e);
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const CalDavAccountScreen()));
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lengths = const [
      Duration(minutes: 30),
      Duration(hours: 1),
      Duration(hours: 2),
      Duration(hours: 3),
    ];
    String lengthLabel(Duration d) => d.inMinutes < 60 ? l10n.durationMinutes(d.inMinutes) : '${d.inHours} h';
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.newEvent, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          TextField(
            controller: _title,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.title),
          ),
          const SizedBox(height: 8),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.allDay),
            value: _allDay,
            onChanged: (v) => setState(() => _allDay = v),
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              OutlinedButton.icon(
                icon: const Icon(Icons.calendar_today, size: 18),
                label: Text(localDate('EEE, d. MMM').format(_day)),
                onPressed: () async {
                  final now = DateTime.now();
                  final d = await showDatePicker(
                    context: context,
                    initialDate: _day,
                    firstDate: now.subtract(const Duration(days: 30)),
                    lastDate: now.add(const Duration(days: 365 * 3)),
                  );
                  if (d != null) setState(() => _day = d);
                },
              ),
              if (!_allDay) ...[
                OutlinedButton.icon(
                  icon: const Icon(Icons.schedule, size: 18),
                  label: Text(_start.format(context)),
                  onPressed: () async {
                    final t = await showTimePicker(context: context, initialTime: _start);
                    if (t != null) setState(() => _start = t);
                  },
                ),
                DropdownButton<Duration>(
                  value: _length,
                  items: [for (final d in lengths) DropdownMenuItem(value: d, child: Text(lengthLabel(d)))],
                  onChanged: (d) => setState(() => _length = d ?? _length),
                ),
              ],
            ],
          ),
          const SizedBox(height: 16),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(onPressed: _saving ? null : _save, child: Text(l10n.save)),
          ),
        ],
      ),
    );
  }
}
