part of 'tasks_screen.dart';

/// Schnell anlegen: Titel, für wen, optional Fälligkeit.
class TaskCreateSheet extends ConsumerStatefulWidget {
  const TaskCreateSheet({super.key});

  @override
  ConsumerState<TaskCreateSheet> createState() => _TaskCreateSheetState();
}


/// Auswahl „für wen“: ich selbst, eine Person oder die Familienliste.
sealed class _Target {
  const _Target();
}


class _Me extends _Target {
  const _Me();
}


class _FamilyList extends _Target {
  const _FamilyList();
}


class _PersonTarget extends _Target {
  final Person person;
  const _PersonTarget(this.person);
}


class _TaskCreateSheetState extends ConsumerState<TaskCreateSheet> {
  final _title = TextEditingController();
  _Target _target = const _Me();
  DateTime? _due;
  bool _saving = false;
  bool _household = false;
  String _recurrence = 'weekly';
  final _rotation = <int>[];

  /// Place type where the task of the current recipient lands (null while unknown): decides which
  /// provider-specific fields are shown (#58). The hub routes the task; the sheet only mirrors that choice.
  String? _place;
  int _placeRequest = 0;
  num _difficulty = 1;
  String? _attribute;
  int _priority = 0;
  int _stars = 0;
  final _tags = <String>{};
  List<Map<String, dynamic>>? _habiticaTags;

  @override
  void initState() {
    super.initState();
    _loadPlace();
  }

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  bool get _isOwn => _target is _Me;

  /// Ask the hub where a task for the current recipient (or the family list) lands. Switching the recipient
  /// supersedes a pending answer; an unknown place simply shows no extra fields.
  Future<void> _loadPlace() async {
    final request = ++_placeRequest;
    final target = _target;
    final api = ref.read(apiClientProvider);
    final String? place;
    if (_household || target is _FamilyList) {
      place = await api.taskPlaceOf(family: true);
    } else if (target is _PersonTarget) {
      place = await api.taskPlaceOf(userId: target.person.id);
    } else {
      place = (await api.taskPlace())?.place;
    }
    if (!mounted || request != _placeRequest) return;
    setState(() => _place = place);
    if (place == 'habitica' && target is _Me && _habiticaTags == null) _loadTags(request);
  }

  /// Own Habitica tags (only the own account's tags are valid for a to-do); fails soft.
  Future<void> _loadTags(int request) async {
    try {
      final options = await ref.read(apiClientProvider).habiticaOptions();
      final tags = [for (final t in (options['tags'] as List? ?? const [])) Map<String, dynamic>.from(t as Map)];
      if (mounted) setState(() => _habiticaTags = tags);
    } catch (_) {
      if (mounted) setState(() => _habiticaTags = const []);
    }
  }

  void _pickTarget(_Target target) {
    setState(() {
      _target = target;
      _place = null;
    });
    _loadPlace();
  }

  /// Fields of the place the task lands in; hub and CalDAV share the plain priority.
  List<Widget> _placeFields(BuildContext context) {
    final place = _place;
    if (place == null) return const [];
    final theme = Theme.of(context);
    final fields = <Widget>[
      Text(l10n.taskOptionsIn(taskPlaceName(place)), key: const Key('task-place-fields'),
          style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary)),
    ];
    if (place == 'habitica') {
      fields.addAll([
        DropdownButtonFormField<num>(
          key: const Key('task-field-difficulty'),
          isExpanded: true,
          initialValue: _difficulty,
          decoration: InputDecoration(labelText: l10n.difficulty),
          items: [for (final p in habiticaDifficulties().entries) DropdownMenuItem(value: p.key, child: Text(p.value))],
          onChanged: _saving ? null : (v) => setState(() => _difficulty = v ?? 1),
        ),
        DropdownButtonFormField<String>(
          key: const Key('task-field-attribute'),
          isExpanded: true,
          initialValue: _attribute ?? 'str',
          decoration: InputDecoration(labelText: l10n.attribute),
          items: [for (final a in habiticaAttributes().entries) DropdownMenuItem(value: a.key, child: Text(a.value))],
          onChanged: _saving ? null : (v) => setState(() => _attribute = v),
        ),
        if (_isOwn && (_habiticaTags ?? const []).isNotEmpty)
          Column(key: const Key('task-field-tags'), crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(l10n.tags, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final tag in _habiticaTags!)
                FilterChip(
                  label: Text(tag['name'] as String? ?? ''),
                  selected: _tags.contains(tag['id']),
                  onSelected: _saving ? null : (on) => setState(() {
                    if (on) { _tags.add(tag['id'] as String); } else { _tags.remove(tag['id']); }
                  }),
                ),
            ]),
          ]),
        Text(l10n.checklistLater, key: const Key('task-field-checklist-hint'),
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      ]);
    } else {
      fields.add(DropdownButtonFormField<int>(
        key: const Key('task-field-priority'),
        isExpanded: true,
        initialValue: _priority,
        decoration: InputDecoration(labelText: place == 'nextcloud' ? l10n.caldavPriority : l10n.taskPriority),
        items: [for (final p in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) DropdownMenuItem(value: p, child: Text('$p'))],
        onChanged: _saving ? null : (v) => setState(() => _priority = v ?? 0),
      ));
    }
    if (place != 'habitica') {
      fields.add(DropdownButtonFormField<int>(
        key: const Key('task-field-stars'),
        isExpanded: true,
        initialValue: _stars,
        decoration: InputDecoration(labelText: l10n.taskStars),
        items: [for (final n in _starOptions) DropdownMenuItem(value: n, child: Text('$n'))],
        onChanged: _saving ? null : (v) => setState(() => _stars = v ?? 0),
      ));
    }
    return [for (final (i, w) in fields.indexed) ...[if (i > 0) const SizedBox(height: 12), w]];
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    if (title.isEmpty) return;
    if (_household && _rotation.isEmpty) {
      showInfo(context, l10n.rotationNeedsPerson);
      return;
    }
    setState(() => _saving = true);
    final target = _target;
    final place = _place;
    final meId = ref.read(sessionProvider).user?.id;
    final ok = await runChange(
      context,
      () async => await ref.read(apiClientProvider).createTask(
            title: title,
            due: _due,
            assigneeId: !_household && target is _PersonTarget ? target.person.id : null,
            family: _household || target is _FamilyList,
            recurrence: _household ? _recurrence : 'none',
            rotation: _household ? List.of(_rotation) : const [],
            meId: meId,
            priority: place != null && place != 'habitica' && _priority > 0 ? _priority : null,
            stars: place != 'habitica' ? _stars : null,
            native: place == 'habitica'
                ? {
                    'type': 'todo',
                    'priority': _difficulty,
                    if (_attribute != null) 'attribute': _attribute,
                    if (target is _Me && _tags.isNotEmpty) 'tags': _tags.toList(),
                  }
                : null,
          ) != null,
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) Navigator.pop(context, true);
  }

  Future<void> _pickDue() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _due ?? now,
      firstDate: now.subtract(const Duration(days: 365)),
      lastDate: now.add(const Duration(days: 365 * 3)),
    );
    if (picked != null) setState(() => _due = picked);
  }

  @override
  Widget build(BuildContext context) {
    final me = ref.watch(sessionProvider).user;
    final allPeople = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    final people = allPeople
        .where((p) => p.id != me?.id)
        .toList();
    final chips = <(String, _Target)>[
      (l10n.me, const _Me()),
      for (final p in people) (p.displayName, _PersonTarget(p)),
      (l10n.family, const _FamilyList()),
    ];
    bool isSelected(_Target t) => switch ((t, _target)) {
          (_Me(), _Me()) => true,
          (_FamilyList(), _FamilyList()) => true,
          (_PersonTarget a, _PersonTarget b) => a.person.id == b.person.id,
          _ => false,
        };

    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.shortcutNewTask, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          TextField(
            key: const Key('task-title'),
            controller: _title,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.whatToDo),
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: 16),
          SwitchListTile(
            key: const Key('household-toggle'),
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.householdRotation),
            subtitle: Text(l10n.householdRotationHint),
            value: _household,
            onChanged: _saving ? null : (value) {
              setState(() {
                _household = value;
                _place = null;
                if (value) _due ??= DateTime.now();
              });
              _loadPlace();
            },
          ),
          if (_household) ...[
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _recurrence,
              decoration: InputDecoration(labelText: l10n.repeat),
              items: [for (final entry in reminderRecurrences.entries)
                if (entry.key != 'none') DropdownMenuItem(value: entry.key, child: Text(entry.value))],
              onChanged: _saving ? null : (value) => setState(() => _recurrence = value!),
            ),
            const SizedBox(height: 12),
            Text(l10n.rotationTapHint),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final person in allPeople)
                FilterChip(
                  key: Key('rotation-${person.id}'),
                  label: Text('${_rotation.contains(person.id) ? '${_rotation.indexOf(person.id) + 1}. ' : ''}${person.displayName}'),
                  selected: _rotation.contains(person.id),
                  onSelected: _saving ? null : (selected) => setState(() {
                    if (selected) { _rotation.add(person.id); } else { _rotation.remove(person.id); }
                  }),
                ),
            ]),
          ] else ...[
          Text(l10n.forWhom),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final (label, target) in chips)
                ChoiceChip(
                  label: Text(label),
                  selected: isSelected(target),
                  onSelected: (_) => _pickTarget(target),
                ),
            ],
          ),
          if (_target case _PersonTarget(:final person))
            Padding(
              key: const Key('task-lands-hint'),
              padding: const EdgeInsets.only(top: 8),
              child: Text(l10n.taskLandsWhereTheyWork(person.displayName),
                  style: Theme.of(context).textTheme.bodySmall),
            ),
          ],
          if (_place != null) ...[const SizedBox(height: 16), ..._placeFields(context)],
          const SizedBox(height: 12),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            runSpacing: 8,
            children: [
              TextButton.icon(
                onPressed: _pickDue,
                icon: const Icon(Icons.event),
                label: Text(_due == null ? l10n.dueDate : localDate('EEE, d. MMM').format(_due!)),
              ),
              if (_due != null && !_household)
                IconButton(
                  tooltip: l10n.removeDueDate,
                  onPressed: () => setState(() => _due = null),
                  icon: const Icon(Icons.clear),
                ),
              FilledButton(
                key: const Key('task-save'),
                onPressed: _saving ? null : _save,
                child: Text(l10n.create),
              ),
            ],
          ),
        ],
      )),
    );
  }
}
