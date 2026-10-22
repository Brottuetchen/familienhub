import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/timetable.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

part 'timetable_copy.dart';
part 'timetable_entry.dart';
part 'timetable_settings.dart';
part 'timetable_week.dart';
part 'timetable_sources.dart';

String _kindLabel(String kind) => switch (kind) {
      'school' => l10n.timetableKindSchool,
      'sport' => l10n.timetableKindSport,
      'music' => l10n.timetableKindMusic,
      'club' => l10n.timetableKindClub,
      _ => l10n.timetableKindOther,
    };


IconData _kindIcon(String kind) => switch (kind) {
      'school' => Icons.school_outlined,
      'sport' => Icons.sports_soccer_outlined,
      'music' => Icons.music_note_outlined,
      'club' => Icons.groups_outlined,
      _ => Icons.event_note_outlined,
    };


String _weekLabel(String week) => switch (week) {
      'a' => l10n.timetableWeekA,
      'b' => l10n.timetableWeekB,
      _ => l10n.timetableWeekAll,
    };


DateTime _mondayOf(DateTime day) => DateTime(day.year, day.month, day.day).subtract(Duration(days: day.weekday - 1));


String _statusLabel(String status) => switch (status) {
      'cancelled' => l10n.timetableStatusCancelled,
      'substitution' => l10n.timetableStatusSubstitution,
      _ => l10n.timetableStatusChanged,
    };


/// Name of a weekday (0 = Monday); 1 January 2024 was a Monday.
String _dayName(int weekday) => localDate('EEEE').format(DateTime(2024, 1, 1 + weekday));


/// Weekly timetable of a child: a day-by-day list (never wider than the screen). Parents edit, children view.
class TimetableScreen extends ConsumerStatefulWidget {
  const TimetableScreen({super.key});

  @override
  ConsumerState<TimetableScreen> createState() => _TimetableScreenState();
}


class _TimetableScreenState extends ConsumerState<TimetableScreen> {
  int? _childId;
  String? _week; // the variant being viewed: all | a | b
  bool _planView = false; // children with a plugin: the weekly plan (own entries) instead of the real week
  DateTime _weekStart = _mondayOf(DateTime.now());

  void _reload(int childId) => ref.invalidate(timetableProvider(childId));

  Future<void> _copyWeek(TimetableData data, String from, String to) async {
    final api = ref.read(apiClientProvider);
    var copied = 0;
    final ok = await runAction(context, () async => copied = await api.copyTimetableWeek(data.child.id, from: from, to: to));
    if (ok && mounted) {
      showInfo(context, l10n.timetableCopied(copied));
      _reload(data.child.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final children = ref.watch(timetableChildrenProvider);
    return children.when(
      loading: () => Scaffold(appBar: AppBar(title: Text(l10n.timetable)), body: const Center(child: HubLoader())),
      error: (e, _) => Scaffold(
        appBar: AppBar(title: Text(l10n.timetable)),
        body: ErrorView(error: e, onRetry: () => ref.invalidate(timetableChildrenProvider)),
      ),
      data: (kids) {
        if (kids.isEmpty) {
          return Scaffold(
            appBar: AppBar(title: Text(l10n.timetable)),
            body: EmptyHint(icon: Icons.calendar_view_week_outlined, text: l10n.timetableNoChildren),
          );
        }
        final id = kids.any((k) => k.id == _childId) ? _childId! : kids.first.id;
        final async = ref.watch(timetableProvider(id));
        final data = async.valueOrNull;
        return Scaffold(
          appBar: AppBar(
            title: Text(l10n.timetable),
            actions: [
              if (data != null && data.canEdit)
                PopupMenuButton<String>(
                  key: const Key('timetable-menu'),
                  onSelected: (v) async {
                    if (v == 'settings') {
                      final saved = await showModalBottomSheet<bool>(
                        context: context,
                        isScrollControlled: true,
                        useSafeArea: true,
                        builder: (_) => _SettingsSheet(settings: data.settings),
                      );
                      if (saved == true) _reload(id);
                    } else if (v == 'sources') {
                      final saved = await showModalBottomSheet<bool>(
                        context: context,
                        isScrollControlled: true,
                        useSafeArea: true,
                        builder: (_) => const _SourcesSheet(),
                      );
                      if (saved == true) {
                        ref.invalidate(timetableWeekProvider);
                        _reload(id);
                      }
                    } else if (v == 'a-b') {
                      _copyWeek(data, 'a', 'b');
                    } else if (v == 'b-a') {
                      _copyWeek(data, 'b', 'a');
                    }
                  },
                  itemBuilder: (_) => [
                    PopupMenuItem(value: 'settings', child: Text(l10n.timetableSettings)),
                    PopupMenuItem(key: const Key('timetable-sources-menu'), value: 'sources', child: Text(l10n.timetableSources)),
                    if (data.settings.hasAbWeeks) ...[
                      PopupMenuItem(value: 'a-b', child: Text(l10n.timetableCopyWeek(_weekLabel('a'), _weekLabel('b')))),
                      PopupMenuItem(value: 'b-a', child: Text(l10n.timetableCopyWeek(_weekLabel('b'), _weekLabel('a')))),
                    ],
                  ],
                ),
            ],
          ),
          body: HubRefresh(
            onRefresh: () => ref.refresh(timetableProvider(id).future),
            child: async.when(
              loading: () => const Center(child: HubLoader()),
              error: (e, _) => ErrorView(error: e, onRetry: () => _reload(id)),
              data: (d) => _body(kids, d),
            ),
          ),
        );
      },
    );
  }

  Widget _body(List<TimetableChild> kids, TimetableData data) {
    final theme = Theme.of(context);
    final ab = data.settings.hasAbWeeks;
    final week = ab ? (_week == 'a' || _week == 'b' ? _week! : data.currentWeek ?? 'a') : 'all';
    final today = DateTime.now();
    final day = DateTime(today.year, today.month, today.day);
    HolidayPeriod? current;
    HolidayPeriod? next;
    for (final h in data.holidays) {
      if (!day.isBefore(h.start) && !day.isAfter(h.end)) current = h;
      if (next == null && h.start.isAfter(day)) next = h;
    }
    final dateFormat = localDate('d. MMM');
    final days = [
      for (var i = 0; i < 7; i++)
        if (i < 5 || data.canEdit || data.forDay(i, week).isNotEmpty) i,
    ];
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        if (kids.length > 1)
          Wrap(spacing: 8, runSpacing: 4, children: [
            for (final k in kids)
              ChoiceChip(
                label: Text(k.name),
                selected: k.id == data.child.id,
                onSelected: (_) => setState(() => _childId = k.id),
              ),
          ]),
        if (data.plugin != null) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 4, children: [
            ChoiceChip(
              key: const Key('timetable-view-week'),
              label: Text(l10n.timetableViewWeek),
              selected: !_planView,
              onSelected: (_) => setState(() => _planView = false),
            ),
            ChoiceChip(
              key: const Key('timetable-view-plan'),
              label: Text(l10n.timetableViewTemplate),
              selected: _planView,
              onSelected: (_) => setState(() => _planView = true),
            ),
          ]),
        ],
        if (data.plugin != null && !_planView)
          _PluginWeek(
            childId: data.child.id,
            plugin: data.plugin!,
            start: _weekStart,
            onShift: (days) => setState(() => _weekStart = _weekStart.add(Duration(days: days))),
            onToday: () => setState(() => _weekStart = _mondayOf(DateTime.now())),
          )
        else ...[
          if (ab) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
              for (final w in ['a', 'b'])
                ChoiceChip(
                  key: Key('timetable-week-$w'),
                  label: Text(_weekLabel(w)),
                  selected: week == w,
                  onSelected: (_) => setState(() => _week = w),
                ),
              if (data.currentWeek != null)
                Text(l10n.timetableThisWeek(_weekLabel(data.currentWeek!)),
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ]),
          ],
          if (current != null || next != null)
            Card(
              key: const Key('timetable-holiday'),
              margin: const EdgeInsets.only(top: 12),
              child: ListTile(
                leading: const Icon(Icons.beach_access_outlined),
                title: Text(current != null
                    ? l10n.timetableHolidayNow(dateFormat.format(current.end))
                    : l10n.timetableHolidayNext(next!.title, dateFormat.format(next.start))),
                subtitle: current != null && current.title.isNotEmpty ? Text(current.title) : null,
              ),
            ),
          for (final d in days) _daySection(data, d, week),
        ],
      ],
    );
  }

  Widget _daySection(TimetableData data, int weekday, String week) {
    final theme = Theme.of(context);
    final entries = data.forDay(weekday, week);
    return Column(
      key: Key('timetable-day-$weekday'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: Text(_dayName(weekday), style: theme.textTheme.titleMedium)),
          if (data.canEdit) ...[
            if (entries.isNotEmpty)
              IconButton(
                key: Key('timetable-copy-$weekday'),
                tooltip: l10n.timetableCopyDay,
                icon: const Icon(Icons.copy_all_outlined),
                onPressed: () => _copyDay(data, weekday, week),
              ),
            IconButton(
              key: Key('timetable-add-$weekday'),
              tooltip: l10n.timetableAddEntry,
              icon: const Icon(Icons.add),
              onPressed: () => _edit(data, null, weekday: weekday, week: week),
            ),
          ],
        ]),
        if (entries.isEmpty)
          Text(l10n.timetableEmptyDay, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant))
        else
          for (final e in entries)
            Card(
              margin: const EdgeInsets.only(top: 4),
              child: ListTile(
                key: Key('timetable-entry-${e.id}'),
                leading: Icon(_kindIcon(e.kind)),
                title: Text(e.title),
                subtitle: Text([
                  '${e.start}–${e.end}',
                  if (e.location != null && e.location!.isNotEmpty) e.location!,
                  if (data.settings.hasAbWeeks && e.week != 'all') _weekLabel(e.week),
                ].join(' · ')),
                onTap: data.canEdit ? () => _edit(data, e) : null,
              ),
            ),
      ],
    );
  }

  Future<void> _edit(TimetableData data, TimetableEntry? entry, {int weekday = 0, String week = 'all'}) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _EntrySheet(
        childId: data.child.id,
        entry: entry,
        weekday: entry?.weekday ?? weekday,
        week: entry?.week ?? week,
        abWeeks: data.settings.hasAbWeeks,
      ),
    );
    if (saved == true) _reload(data.child.id);
  }

  Future<void> _copyDay(TimetableData data, int weekday, String week) async {
    final targets = await showDialog<List<int>>(
      context: context,
      builder: (_) => _CopyDayDialog(from: weekday),
    );
    if (targets == null || targets.isEmpty || !mounted) return;
    final api = ref.read(apiClientProvider);
    var copied = 0;
    final ok = await runAction(context, () async => copied = await api.copyTimetableDay(data.child.id, week: week, from: weekday, to: targets));
    if (ok && mounted) {
      showInfo(context, l10n.timetableCopied(copied));
      _reload(data.child.id);
    }
  }
}
