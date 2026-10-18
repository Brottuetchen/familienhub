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

Color? _hex(String? raw) {
  var hex = raw?.trim().replaceFirst('#', '');
  if (hex != null && hex.length == 3) hex = hex.split('').map((c) => '$c$c').join();
  // #RRGGBBAA (some servers) -> the alpha digits are dropped, calendars are never translucent.
  final value = hex != null && (hex.length == 6 || hex.length == 8) ? int.tryParse(hex.substring(0, 6), radix: 16) : null;
  return value == null ? null : Color(0xFF000000 | value);
}

/// Calendars the person sees; failures (older server, offline) just mean "no list".
final calendarsProvider = FutureProvider.autoDispose<List<CalendarInfo>>((ref) async {
  try {
    return await ref.watch(apiClientProvider).calendars();
  } catch (_) {
    return const [];
  }
});

/// Readable on light and dark themes; used when a calendar brings no colour of its own.
const _palette = [Color(0xFF3D85C6), Color(0xFFE07A5F), Color(0xFF81B29A), Color(0xFFE3B23C), Color(0xFF9B5DE5),
  Color(0xFF00A6A6), Color(0xFFF15BB5), Color(0xFF8D6E63)];

/// Colour per calendar id: the server's colour (CalDAV), otherwise a stable palette colour.
final calendarColorsProvider = Provider.autoDispose<Map<String, Color>>((ref) {
  final cals = ref.watch(calendarsProvider).valueOrNull ?? const <CalendarInfo>[];
  return {for (final (i, c) in cals.indexed) c.id: _hex(c.color) ?? _palette[i % _palette.length]};
});

/// The calendar's colour (same as its filter chip) wins over the event's own colour; the latter is only a fallback.
Color eventColor(BuildContext context, CalendarEvent e, [Map<String, Color> colors = const {}]) =>
    (e.calendarId == null ? null : colors[e.calendarId]) ?? _hex(e.color) ?? Theme.of(context).colorScheme.primary;

const _hiddenKey = 'calendar_hidden';

/// Calendar: list (next 30 days), week or month; the choice is remembered on the device.
class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});

  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  CalendarView _view = CalendarView.list;
  Set<String> _hidden = {}; // calendar ids switched off with the chips
  DateTime _anchor = _day(DateTime.now()); // shown week/month
  DateTime _selected = _day(DateTime.now());

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      final v = CalendarView.values.where((v) => v.name == p.getString(_viewKey)).firstOrNull;
      final hidden = p.getStringList(_hiddenKey);
      if (mounted) {
        setState(() {
          if (v != null) _view = v;
          if (hidden != null) _hidden = hidden.toSet();
        });
      }
    }).catchError((Object _) {});
  }

  Future<void> _setView(CalendarView v) async {
    setState(() => _view = v);
    try {
      (await SharedPreferences.getInstance()).setString(_viewKey, v.name);
    } catch (_) {}
  }

  Future<void> _toggle(String id) async {
    setState(() => _hidden.contains(id) ? _hidden.remove(id) : _hidden.add(id));
    try {
      (await SharedPreferences.getInstance()).setStringList(_hiddenKey, _hidden.toList());
    } catch (_) {}
  }

  List<CalendarEvent> _visible(List<CalendarEvent> all) =>
      [for (final e in all) if (e.calendarId == null || !_hidden.contains(e.calendarId)) e];

  Widget _viewSwitch() => SegmentedButton<CalendarView>(
        key: const Key('calendar-view'),
        showSelectedIcon: false,
        style: const ButtonStyle(
          visualDensity: VisualDensity.compact,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          padding: WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 8)),
        ),
        segments: [
          ButtonSegment(value: CalendarView.list, icon: const Icon(Icons.view_agenda_outlined), tooltip: l10n.viewList),
          ButtonSegment(value: CalendarView.week, icon: const Icon(Icons.view_week_outlined), tooltip: l10n.viewWeek),
          ButtonSegment(value: CalendarView.month, icon: const Icon(Icons.calendar_view_month), tooltip: l10n.viewMonth),
        ],
        selected: {_view},
        onSelectionChanged: (v) => _setView(v.first),
      );

  Widget _filters() {
    final cals = ref.watch(calendarsProvider).valueOrNull ?? const <CalendarInfo>[];
    if (cals.length < 2) return const SizedBox.shrink();
    final colors = ref.watch(calendarColorsProvider);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
      child: Row(children: [
        for (final c in cals)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: FilterChip(
              key: Key('cal-filter-${c.id}'),
              avatar: CircleAvatar(radius: 6, backgroundColor: colors[c.id]?.withValues(alpha: _hidden.contains(c.id) ? 0.35 : 1)),
              label: Text(c.name, style: _hidden.contains(c.id)
                  ? TextStyle(decoration: TextDecoration.lineThrough, color: Theme.of(context).colorScheme.onSurfaceVariant)
                  : null),
              selected: !_hidden.contains(c.id),
              showCheckmark: false,
              onSelected: (_) => _toggle(c.id),
            ),
          ),
      ]),
    );
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
      appBar: AppBar(
        title: Text(l10n.tabCalendar),
        // Icon-only segments (tooltips carry the words): fits 360 dp and large fonts in any language.
        actions: [_viewSwitch(), ReadStatusIcon(result: listAsync.valueOrNull), const SizedBox(width: 4)],
      ),
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
        _filters(),
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
          for (final e in _visible(result.data).where((e) => e.start != null)) {
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
      data: (r) => build(_visible(r.data)),
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
    final colors = ref.watch(calendarColorsProvider);
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
            Container(height: 4, margin: const EdgeInsets.only(bottom: 2), color: eventColor(context, e, colors).withValues(alpha: 0.8)),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (final e in dots)
              Container(width: 6, height: 6, margin: const EdgeInsets.symmetric(horizontal: 1.5),
                  decoration: BoxDecoration(color: eventColor(context, e, colors), shape: BoxShape.circle)),
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

const _targetKey = 'calendar_last_target';

/// New event: target calendar (family calendar suggested, then the last choice), times, place, notes, repeat.
class EventCreateSheet extends ConsumerStatefulWidget {
  /// Edit this event instead of creating one (calendar stays fixed).
  final CalendarEvent? initial;
  const EventCreateSheet({super.key, this.initial});

  @override
  ConsumerState<EventCreateSheet> createState() => _EventCreateSheetState();
}

class _EventCreateSheetState extends ConsumerState<EventCreateSheet> {
  final _title = TextEditingController();
  final _location = TextEditingController();
  final _notes = TextEditingController();
  DateTime _day = DateTime.now();
  DateTime _endDay = DateTime.now();
  TimeOfDay _start = TimeOfDay(hour: (TimeOfDay.now().hour + 1) % 24, minute: 0);
  TimeOfDay _end = TimeOfDay(hour: (TimeOfDay.now().hour + 2) % 24, minute: 0);
  bool _allDay = false;
  bool _saving = false;
  String _recurrence = 'none';
  String? _target; // calendar id
  String? _lastTarget;

  static const _recurrences = ['none', 'daily', 'weekly', 'monthly', 'yearly'];

  bool get _editing => widget.initial != null;

  /// CalDAV series: times can't be changed here (the hub would move the whole series).
  bool get _timesLocked => _editing && widget.initial!.source == 'caldav' && widget.initial!.recurring;

  @override
  void initState() {
    super.initState();
    final e = widget.initial;
    if (e != null) {
      _title.text = e.title;
      _location.text = e.location ?? '';
      _notes.text = e.notes ?? '';
      _allDay = e.allDay;
      _recurrence = e.source == 'hub' ? e.recurrence : 'none';
      final s = e.start ?? DateTime.now();
      final end = e.end ?? s.add(const Duration(hours: 1));
      _day = s;
      _start = TimeOfDay.fromDateTime(s);
      _end = TimeOfDay.fromDateTime(end);
      _endDay = e.allDay ? end.subtract(const Duration(days: 1)) : end;
      if (_endDay.isBefore(_day)) _endDay = _day;
    }
    SharedPreferences.getInstance().then((p) {
      if (mounted) setState(() => _lastTarget = p.getString(_targetKey));
    }).catchError((Object _) {});
  }

  @override
  void dispose() {
    _title.dispose();
    _location.dispose();
    _notes.dispose();
    super.dispose();
  }

  String _recurrenceLabel(String r) => switch (r) {
        'daily' => l10n.recurDaily,
        'weekly' => l10n.recurWeekly,
        'monthly' => l10n.recurMonthly,
        'yearly' => l10n.recurYearly,
        _ => l10n.recurNone,
      };

  /// Suggestion: the user's last choice, else the family calendar, else the first writable one.
  String? _defaultTarget(List<CalendarInfo> writable) {
    if (writable.isEmpty) return null;
    if (writable.any((c) => c.id == _lastTarget)) return _lastTarget;
    return (writable.where((c) => c.family).firstOrNull ?? writable.first).id;
  }

  Future<void> _save(String? target) async {
    final title = _title.text.trim();
    if (title.isEmpty) return;
    final start = _allDay
        ? DateTime(_day.year, _day.month, _day.day)
        : DateTime(_day.year, _day.month, _day.day, _start.hour, _start.minute);
    var end = _allDay
        ? DateTime(_endDay.year, _endDay.month, _endDay.day).add(const Duration(days: 1)) // iCalendar DTEND exclusive
        : DateTime(_day.year, _day.month, _day.day, _end.hour, _end.minute);
    if (!_allDay && !end.isAfter(start)) end = end.add(const Duration(days: 1)); // e.g. 22:00–01:00
    if (_allDay && !end.isAfter(start)) end = start.add(const Duration(days: 1));
    setState(() => _saving = true);
    try {
      final api = ref.read(apiClientProvider);
      if (_editing) {
        await api.updateEvent(widget.initial!, title: title, start: start, end: end, allDay: _allDay,
            location: _location.text.trim(), notes: _notes.text.trim(), recurrence: _recurrence);
      } else {
        await api.createEvent(
            title: title, start: start, end: end, allDay: _allDay, calendarId: target,
            location: _location.text.trim(), notes: _notes.text.trim(), recurrence: _recurrence);
      }
      if (target != null && !_editing) {
        try {
          (await SharedPreferences.getInstance()).setString(_targetKey, target);
        } catch (_) {}
      }
      ref.invalidate(eventsProvider);
      ref.invalidate(eventsRangeProvider);
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

  Future<DateTime?> _pickDay(DateTime initial) {
    final now = DateTime.now();
    return showDatePicker(context: context, initialDate: initial,
        firstDate: now.subtract(const Duration(days: 365)), lastDate: now.add(const Duration(days: 365 * 3)));
  }

  @override
  Widget build(BuildContext context) {
    final cals = ref.watch(calendarsProvider).valueOrNull ?? const <CalendarInfo>[];
    final writable = [for (final c in cals) if (c.writable) c];
    final colors = ref.watch(calendarColorsProvider);
    final target = writable.any((c) => c.id == _target) ? _target : _defaultTarget(writable);
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_editing ? l10n.editEvent : l10n.newEvent, style: theme.textTheme.titleLarge),
            const SizedBox(height: 16),
            TextField(
              key: const Key('event-title'),
              controller: _title,
              autofocus: true,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.title),
            ),
            if (writable.length > 1 && !_editing) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                key: const Key('event-calendar'),
                initialValue: target,
                isExpanded: true,
                decoration: InputDecoration(labelText: l10n.calendarTarget),
                items: [
                  for (final c in writable)
                    DropdownMenuItem(
                      value: c.id,
                      child: Row(children: [
                        CircleAvatar(radius: 6, backgroundColor: colors[c.id]),
                        const SizedBox(width: 10),
                        Flexible(child: Text(c.name, overflow: TextOverflow.ellipsis)),
                        if (c.family) ...[
                          const SizedBox(width: 8),
                          Flexible(child: Text('· ${l10n.familyCalendarHint}', style: theme.textTheme.bodySmall,
                              overflow: TextOverflow.ellipsis)),
                        ],
                      ]),
                    ),
                ],
                onChanged: (v) => setState(() => _target = v),
              ),
            ],
            const SizedBox(height: 8),
            if (_timesLocked)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(l10n.seriesTimesHint, style: TextStyle(color: theme.colorScheme.onSurfaceVariant)),
              )
            else ...[
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l10n.allDay),
              value: _allDay,
              onChanged: (v) => setState(() => _allDay = v),
            ),
            Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              OutlinedButton.icon(
                key: const Key('event-day'),
                icon: const Icon(Icons.calendar_today, size: 18),
                label: Text(localDate('EEE, d. MMM').format(_day)),
                onPressed: () async {
                  final d = await _pickDay(_day);
                  if (d != null) setState(() => (_day = d, _endDay = _endDay.isBefore(d) ? d : _endDay));
                },
              ),
              if (_allDay) ...[
                Text(l10n.untilDay),
                OutlinedButton.icon(
                  key: const Key('event-end-day'),
                  icon: const Icon(Icons.event, size: 18),
                  label: Text(localDate('EEE, d. MMM').format(_endDay)),
                  onPressed: () async {
                    final d = await _pickDay(_endDay.isBefore(_day) ? _day : _endDay);
                    if (d != null) setState(() => _endDay = d.isBefore(_day) ? _day : d);
                  },
                ),
              ] else ...[
                OutlinedButton.icon(
                  key: const Key('event-start'),
                  icon: const Icon(Icons.schedule, size: 18),
                  label: Text(_start.format(context)),
                  onPressed: () async {
                    final t = await showTimePicker(context: context, initialTime: _start);
                    if (t == null) return;
                    // keep the length when the start moves
                    final length = (_end.hour * 60 + _end.minute) - (_start.hour * 60 + _start.minute);
                    final endMin = (t.hour * 60 + t.minute + (length > 0 ? length : 60)) % (24 * 60);
                    setState(() => (_start = t, _end = TimeOfDay(hour: endMin ~/ 60, minute: endMin % 60)));
                  },
                ),
                const Text('–'),
                OutlinedButton.icon(
                  key: const Key('event-end'),
                  icon: const Icon(Icons.schedule_outlined, size: 18),
                  label: Text(_end.format(context)),
                  onPressed: () async {
                    final t = await showTimePicker(context: context, initialTime: _end);
                    if (t != null) setState(() => _end = t);
                  },
                ),
              ],
            ]),
            ],
            const SizedBox(height: 12),
            TextField(
              key: const Key('event-location'),
              controller: _location,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.location, prefixIcon: const Icon(Icons.place_outlined)),
            ),
            const SizedBox(height: 8),
            TextField(
              key: const Key('event-notes'),
              controller: _notes,
              minLines: 1,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.notes, prefixIcon: const Icon(Icons.notes)),
            ),
            const SizedBox(height: 8),
            if (!_editing || widget.initial!.source == 'hub')
            DropdownButtonFormField<String>(
              key: const Key('event-repeat'),
              initialValue: _recurrence,
              decoration: InputDecoration(labelText: l10n.repeat, prefixIcon: const Icon(Icons.repeat)),
              items: [for (final r in _recurrences) DropdownMenuItem(value: r, child: Text(_recurrenceLabel(r)))],
              onChanged: (v) => setState(() => _recurrence = v ?? 'none'),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                key: const Key('event-save'),
                onPressed: _saving ? null : () => _save(target),
                child: Text(l10n.save),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
