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

part 'event_tile.dart';
part 'event_details.dart';
part 'event_create.dart';

enum CalendarView { list, week, month }


const _viewKey = 'calendar_view';


DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

DateTime _monday(DateTime d) {
  final day = _day(d);
  return DateTime(day.year, day.month, day.day - (day.weekday - 1));
}

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
        // Calendar days, so a week step stays on the same weekday across the clock change.
        _anchor = _view == CalendarView.week
            ? DateTime(_anchor.year, _anchor.month, _anchor.day + 7 * delta)
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



/// "15 Minuten vorher", "Zur Startzeit", "Keine" (-1).
String alarmLabel(int minutes) => switch (minutes) {
      < 0 => l10n.alarmNone,
      0 => l10n.alarmAtStart,
      1440 => l10n.alarmDayBefore,
      60 => l10n.alarmHourBefore,
      _ => minutes % 1440 == 0 ? l10n.alarmDaysBefore(minutes ~/ 1440)
          : minutes % 60 == 0 ? l10n.alarmHoursBefore(minutes ~/ 60) : l10n.alarmMinutesBefore(minutes),
    };
