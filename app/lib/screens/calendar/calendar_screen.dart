import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models/calendar_event.dart';
import '../../models/common.dart';
import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';
import '../more/caldav_account_screen.dart';
import '../../l10n/l10n.dart';

enum CalendarView { list, week, month }

const _viewKey = 'calendar_view';

DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);
DateTime _monday(DateTime d) => _day(d).subtract(Duration(days: d.weekday - 1));
String _key(DateTime start, int days) =>
    '${start.year}-${start.month.toString().padLeft(2, '0')}-${start.day.toString().padLeft(2, '0')}:$days';

Color eventColor(BuildContext context, CalendarEvent e) {
  final hex = e.color?.replaceFirst('#', '');
  final value = hex != null && hex.length >= 6 ? int.tryParse(hex.substring(0, 6), radix: 16) : null;
  return value == null ? Theme.of(context).colorScheme.primary : Color(0xFF000000 | value);
}

/// Calendar: list (next 30 days), week or month; the choice is remembered on the device.
class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});

  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  CalendarView _view = CalendarView.list;
  DateTime _anchor = _day(DateTime.now()); // shown week/month
  DateTime _selected = _day(DateTime.now());

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      final v = CalendarView.values.where((v) => v.name == p.getString(_viewKey)).firstOrNull;
      if (v != null && mounted) setState(() => _view = v);
    }).catchError((Object _) {});
  }

  Future<void> _setView(CalendarView v) async {
    setState(() => _view = v);
    try {
      (await SharedPreferences.getInstance()).setString(_viewKey, v.name);
    } catch (_) {}
  }

  (DateTime, int) get _range {
    if (_view == CalendarView.week) return (_monday(_anchor), 7);
    return (_monday(DateTime(_anchor.year, _anchor.month, 1)), 42);
  }

  void _shift(int delta) => setState(() {
        _anchor = _view == CalendarView.week
            ? _anchor.add(Duration(days: 7 * delta))
            : DateTime(_anchor.year, _anchor.month + delta, 1);
        if (_view == CalendarView.month) _selected = _anchor;
      });

  void _today() => setState(() => _anchor = _selected = _day(DateTime.now()));

  Future<void> _refresh() async {
    if (_view == CalendarView.list) {
      await ref.read(eventsProvider.notifier).refresh();
      return;
    }
    final (start, days) = _range;
    await ref.read(eventsRangeProvider(_key(start, days)).notifier).refresh();
  }

  @override
  Widget build(BuildContext context) {
    final listAsync = ref.watch(eventsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.tabCalendar), actions: [ReadStatusIcon(result: listAsync.valueOrNull)]),
      floatingActionButton: !ref.watch(canEditProvider) ? null : FloatingActionButton.extended(
        onPressed: () async {
          await showModalBottomSheet<bool>(
            context: context,
            isScrollControlled: true,
            useSafeArea: true,
            builder: (_) => const EventCreateSheet(),
          );
          ref.invalidate(eventsRangeProvider);
        },
        icon: const Icon(Icons.add),
        label: Text(l10n.event),
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: SegmentedButton<CalendarView>(
            key: const Key('calendar-view'),
            showSelectedIcon: false,
            segments: [
              ButtonSegment(value: CalendarView.list, label: Text(l10n.viewList)),
              ButtonSegment(value: CalendarView.week, label: Text(l10n.viewWeek)),
              ButtonSegment(value: CalendarView.month, label: Text(l10n.viewMonth)),
            ],
            selected: {_view},
            onSelectionChanged: (v) => _setView(v.first),
          ),
        ),
        Expanded(child: HubRefresh(onRefresh: _refresh, child: switch (_view) {
          CalendarView.list => _list(listAsync),
          CalendarView.week => _rangeView(_week),
          CalendarView.month => _rangeView(_month),
        })),
      ]),
    );
  }

  Widget _list(AsyncValue<ApiResult<List<CalendarEvent>>> async) => async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: _refresh),
        data: (result) {
          final byDay = <DateTime, List<CalendarEvent>>{};
          for (final e in result.data.where((e) => e.start != null)) {
            byDay.putIfAbsent(_day(e.start!), () => []).add(e);
          }
          final days = byDay.keys.toList()..sort();
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              if (days.isEmpty) EmptyHint(icon: Icons.event_available, text: l10n.noEvents30),
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
      );

  Widget _rangeView(Widget Function(List<CalendarEvent>) build) {
    final (start, days) = _range;
    final async = ref.watch(eventsRangeProvider(_key(start, days)));
    return async.when(
      loading: () => const Center(child: HubLoader()),
      error: (e, _) => ErrorView(error: e, onRetry: _refresh),
      data: (r) => build(r.data),
    );
  }

  Widget _nav(String title, {required String prevTip, required String nextTip}) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(children: [
          IconButton(key: const Key('calendar-prev'), tooltip: prevTip, onPressed: () => _shift(-1), icon: const Icon(Icons.chevron_left)),
          Expanded(child: TextButton(onPressed: _today, child: Text(title, style: Theme.of(context).textTheme.titleMedium))),
          IconButton(key: const Key('calendar-next'), tooltip: nextTip, onPressed: () => _shift(1), icon: const Icon(Icons.chevron_right)),
        ]),
      );

  List<CalendarEvent> _on(List<CalendarEvent> all, DateTime day) => [for (final e in all) if (e.occursOn(day)) e];

  Widget _week(List<CalendarEvent> all) {
    final monday = _monday(_anchor);
    final sunday = monday.add(const Duration(days: 6));
    final week = ((int.parse(localDate('D').format(monday)) - monday.weekday + 10) / 7).floor();
    final range = '${localDate('d.M.').format(monday)} – ${localDate('d.M.').format(sunday)}';
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return ListView(physics: const AlwaysScrollableScrollPhysics(), padding: const EdgeInsets.only(bottom: 96), children: [
      _nav(l10n.weekRange(week, range), prevTip: l10n.previousWeek, nextTip: l10n.nextWeek),
      for (var i = 0; i < 7; i++) ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
          child: Text(dayLabel(monday.add(Duration(days: i))), style: Theme.of(context).textTheme.titleSmall),
        ),
        if (_on(all, monday.add(Duration(days: i))).isEmpty)
          Padding(padding: const EdgeInsets.fromLTRB(16, 2, 16, 4), child: Text('–', style: muted))
        else
          for (final e in _on(all, monday.add(Duration(days: i)))) _EventTile(event: e),
      ],
    ]);
  }

  Widget _month(List<CalendarEvent> all) {
    final theme = Theme.of(context);
    final first = DateTime(_anchor.year, _anchor.month, 1);
    final gridStart = _monday(first);
    final today = _day(DateTime.now());
    final dayEvents = _on(all, _selected);
    return ListView(physics: const AlwaysScrollableScrollPhysics(), padding: const EdgeInsets.only(bottom: 96), children: [
      _nav(localDate('MMMM y').format(first), prevTip: l10n.previousMonth, nextTip: l10n.nextMonth),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(children: [
          for (var i = 0; i < 7; i++)
            Expanded(child: Center(child: Text(localDate('E').format(gridStart.add(Duration(days: i))).substring(0, 2),
                style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)))),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Column(children: [
          for (var w = 0; w < 6; w++)
            Row(children: [
              for (var i = 0; i < 7; i++) Expanded(child: _cell(all, gridStart.add(Duration(days: w * 7 + i)), first.month, today)),
            ]),
        ]),
      ),
      const Divider(height: 24),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
        child: Text(dayLabel(_selected), style: theme.textTheme.titleSmall),
      ),
      if (dayEvents.isEmpty)
        Padding(padding: const EdgeInsets.all(16), child: Text(l10n.noEventsThisDay, style: TextStyle(color: theme.colorScheme.onSurfaceVariant)))
      else
        for (final e in dayEvents) _EventTile(event: e),
    ]);
  }

  Widget _cell(List<CalendarEvent> all, DateTime day, int month, DateTime today) {
    final theme = Theme.of(context);
    final events = _on(all, day);
    final bars = [for (final e in events) if (e.isMultiDay) e].take(2).toList();
    final dots = [for (final e in events) if (!e.isMultiDay) e].take(3).toList();
    final selected = day == _selected;
    final outside = day.month != month;
    return InkWell(
      key: ValueKey('cal-day-${day.month}-${day.day}'),
      borderRadius: BorderRadius.circular(10),
      onTap: () => setState(() => _selected = day),
      child: Container(
        height: 58,
        margin: const EdgeInsets.all(1.5),
        decoration: BoxDecoration(
          color: selected ? theme.colorScheme.primaryContainer : null,
          borderRadius: BorderRadius.circular(10),
          border: day == today ? Border.all(color: theme.colorScheme.primary, width: 1.5) : null,
        ),
        child: Column(children: [
          const SizedBox(height: 4),
          Text('${day.day}', style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: day == today ? FontWeight.w700 : null,
              color: outside ? theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5) : null)),
          const SizedBox(height: 3),
          for (final e in bars)
            Container(height: 4, margin: const EdgeInsets.only(bottom: 2), color: eventColor(context, e).withValues(alpha: 0.8)),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (final e in dots)
              Container(width: 6, height: 6, margin: const EdgeInsets.symmetric(horizontal: 1.5),
                  decoration: BoxDecoration(color: eventColor(context, e), shape: BoxShape.circle)),
          ]),
        ]),
      ),
    );
  }
}

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
      leading: Container(width: 4, height: 36, decoration: BoxDecoration(color: eventColor(context, event), borderRadius: BorderRadius.circular(2))),
      title: Text(event.title),
      subtitle: Text(sub.join(' · ')),
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
