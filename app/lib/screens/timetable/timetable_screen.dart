import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/timetable.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

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
                    } else if (v == 'a-b') {
                      _copyWeek(data, 'a', 'b');
                    } else if (v == 'b-a') {
                      _copyWeek(data, 'b', 'a');
                    }
                  },
                  itemBuilder: (_) => [
                    PopupMenuItem(value: 'settings', child: Text(l10n.timetableSettings)),
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

class _CopyDayDialog extends StatefulWidget {
  final int from;
  const _CopyDayDialog({required this.from});

  @override
  State<_CopyDayDialog> createState() => _CopyDayDialogState();
}

class _CopyDayDialogState extends State<_CopyDayDialog> {
  final _picked = <int>{};

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(l10n.timetableCopyDayTo(_dayName(widget.from))),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 4, children: [
            for (var d = 0; d < 7; d++)
              if (d != widget.from)
                FilterChip(
                  key: Key('timetable-copy-to-$d'),
                  label: Text(_dayName(d)),
                  selected: _picked.contains(d),
                  onSelected: (on) => setState(() => on ? _picked.add(d) : _picked.remove(d)),
                ),
          ]),
          const SizedBox(height: 12),
          Text(l10n.timetableCopyReplaces, style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
        FilledButton(
          key: const Key('timetable-copy-confirm'),
          onPressed: _picked.isEmpty ? null : () => Navigator.pop(context, _picked.toList()..sort()),
          child: Text(l10n.copy),
        ),
      ],
    );
  }
}

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
