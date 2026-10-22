part of 'calendar_screen.dart';

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
  int _alarm = 15; // minutes before the start; -1 = none
  String? _target; // calendar id
  String? _lastTarget;

  static const _recurrences = ['none', 'daily', 'weekly', 'monthly', 'yearly'];
  static const _alarms = [-1, 0, 5, 15, 30, 60, 1440];

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
      _alarm = e.alarmMinutes ?? -1;
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
            location: _location.text.trim(), notes: _notes.text.trim(), recurrence: _recurrence,
            alarmMinutes: _alarm < 0 ? null : _alarm);
      } else {
        await api.createEvent(
            title: title, start: start, end: end, allDay: _allDay, calendarId: target,
            location: _location.text.trim(), notes: _notes.text.trim(), recurrence: _recurrence,
            alarmMinutes: _alarm < 0 ? null : _alarm);
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
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(
              key: const Key('event-alarm'),
              initialValue: _alarm,
              isExpanded: true,
              decoration: InputDecoration(labelText: l10n.eventAlarm, prefixIcon: const Icon(Icons.notifications_none)),
              items: [for (final m in _alarms) DropdownMenuItem(value: m, child: Text(alarmLabel(m)))],
              onChanged: (v) => setState(() => _alarm = v ?? -1),
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
