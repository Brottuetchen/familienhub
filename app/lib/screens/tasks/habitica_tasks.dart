import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/task.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Konkrete Habitica-Bedienung, keine zweite Plugin-/UI-Schemaengine.
class HabiticaAccountScreen extends ConsumerStatefulWidget {
  const HabiticaAccountScreen({super.key});
  @override
  ConsumerState<HabiticaAccountScreen> createState() => _HabiticaAccountState();
}

class _HabiticaAccountState extends ConsumerState<HabiticaAccountScreen> {
  final _user = TextEditingController(), _key = TextEditingController();
  Map<String, dynamic>? _account;
  List<Task> _tasks = [];
  String? _error;
  bool _busy = false;
  @override
  void initState() { super.initState(); _load(); }
  @override
  void dispose() { _user.dispose(); _key.dispose(); super.dispose(); }
  Future<void> _load() async {
    setState(() { _busy = true; _error = null; });
    try {
      final api = ref.read(apiClientProvider);
      final account = await api.habiticaAccount();
      final result = account['configured'] == true ? await api.habiticaTasks() : null;
      final tasks = result?.items ?? <Task>[];
      if (result != null && !result.isOk) { throw StateError(result.error ?? 'Habitica-Aufgaben nicht lesbar'); }
      if (mounted) setState(() { _account = account; _tasks = tasks; _user.text = account['remote_user_id'] as String? ?? ''; });
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _save() async {
    setState(() { _busy = true; _error = null; });
    try {
      await ref.read(apiClientProvider).saveHabiticaAccount(_user.text.trim(), _key.text);
      _key.clear();
      await refreshTasks(ref);
      await _load();
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Habitica · eigenes Konto'), actions: [IconButton(onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh), tooltip: 'Remote-Aufgaben aktualisieren')]),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('Der Hub bündelt Aufgaben dieses Kontos. Keine Spiegelung nach Nextcloud, kein Export anderer Aufgaben.'),
      TextField(controller: _user, decoration: const InputDecoration(labelText: 'Habitica-Nutzer-ID (UUID)')),
      TextField(controller: _key, obscureText: true, autocorrect: false, enableSuggestions: false, decoration: const InputDecoration(labelText: 'API-Schlüssel (nur zum Ändern eingeben)')),
      FilledButton(onPressed: _busy ? null : _save, child: const Text('Eigenes Konto prüfen und speichern')),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      if (_account != null) ...[
        Text('Server: ${_account!['server_url']}'),
        Text('Konto: ${_account!['account']}'),
        Text(_account!['writes_enabled'] == true ? 'Native Schreibaktionen freigegeben' : 'Lesemodus: Betreiber muss den geprüften Single-Writer-Übergang freigeben.'),
        if (_account!['unconfirmed_operation'] == true) const Text('Unklares Operationsergebnis: im Fachsystem prüfen. Keine automatische Wiederholung oder Rückbuchung.'),
        if (_account!['configured'] == true) FilledButton.tonal(onPressed: _busy || _account!['writes_enabled'] != true ? null : () async {
          await showNativeEditor(context, ref, _account!['account'] as String);
          await _load();
        }, child: const Text('Native Habitica-Aufgabe erstellen')),
      ],
      const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Text('Remote-Aufgaben ausdrücklich für die Hub-Ansichten auswählen (kein Kopieren):')),
      for (final task in _tasks) CheckboxListTile(
        title: Text(task.title), subtitle: Text('${task.native['type']} · ${task.uid}'),
        value: task.selected,
        onChanged: _busy ? null : (value) async {
          setState(() => _busy = true);
          try {
            await ref.read(apiClientProvider).selectHabiticaTask(task, value!);
            await refreshTasks(ref);
            await _load();
          } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
          finally { if (mounted) setState(() => _busy = false); }
        },
      ),
    ]),
  );
}

/// Aufgabenlisten und „Heute“ im Hintergrund nachladen. Die angezeigten Daten bleiben stehen:
/// kein Lade-Bildschirm, nichts wird neu aufgebaut (früher: invalidate → alles lud neu).
Future<void> refreshTasks(WidgetRef ref) async {
  Future<void> quiet(Future<Object?> f) => f.then((_) {}, onError: (Object _) {}); // Fehler zeigt der Status
  await Future.wait([
    for (final view in TaskView.values)
      if (ref.exists(tasksProvider(view))) quiet(ref.read(tasksProvider(view).notifier).refresh()),
    if (ref.exists(todayProvider)) quiet(ref.read(todayProvider.notifier).refresh()),
  ]);
}

Future<void> showNativeEditor(BuildContext context, WidgetRef ref, String account, {Task? task}) async {
  await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => ProtectedReadModal(
    provider: tasksProvider(TaskView.mine), child: HabiticaTaskEditor(account: account, task: task))));
  await refreshTasks(ref);
}

class HabiticaTaskButtons extends ConsumerStatefulWidget {
  final Task task;
  final bool enabled;
  final Future<void> Function() onChanged;
  const HabiticaTaskButtons({super.key, required this.task, required this.onChanged, this.enabled = true});
  @override
  ConsumerState<HabiticaTaskButtons> createState() => _HabiticaButtonsState();
}

class _HabiticaButtonsState extends ConsumerState<HabiticaTaskButtons> {
  bool _busy = false;
  Future<void> _act(String action) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).nativeTaskActionAndRefresh(widget.task, action);
      await widget.onChanged();
    } catch (e) { if (mounted) showError(context, e); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  Widget build(BuildContext context) {
    final task = widget.task, n = task.native;
    final enabled = widget.enabled && !_busy && !ref.read(apiClientProvider).nativeTaskBlocked(task.account);
    final type = n['type'];
    return Row(mainAxisSize: MainAxisSize.min, children: [
      if (type == 'habit') ...[
        IconButton(tooltip: 'Habit minus', onPressed: enabled && n['down'] == true && task.actions.contains('down') ? () => _act('down') : null, icon: const Icon(Icons.remove_circle_outline)),
        IconButton(tooltip: 'Habit plus', onPressed: enabled && n['up'] == true && task.actions.contains('up') ? () => _act('up') : null, icon: const Icon(Icons.add_circle_outline)),
      ] else if (type == 'reward')
        IconButton(tooltip: 'Belohnung einlösen', onPressed: enabled && task.actions.contains('up') ? () => _act('up') : null, icon: const Icon(Icons.redeem))
      else
        // To-do/Daily: rundes Kästchen wie bei allen Aufgaben – leer = offen, Haken = erledigt
        Tooltip(
          message: task.done ? 'Wieder öffnen' : 'Erledigen',
          child: Checkbox(
            shape: const CircleBorder(),
            value: task.done,
            semanticLabel: task.done ? '„${task.title}“ wieder öffnen' : '„${task.title}“ erledigen',
            onChanged: enabled && task.actions.contains(task.done ? 'down' : 'up') ? (_) => _act(task.done ? 'down' : 'up') : null,
          ),
        ),
    ]);
  }
}

class HabiticaTaskEditor extends ConsumerStatefulWidget {
  final String account;
  final Task? task;
  const HabiticaTaskEditor({super.key, required this.account, this.task});
  @override
  ConsumerState<HabiticaTaskEditor> createState() => _HabiticaEditorState();
}

class _HabiticaEditorState extends ConsumerState<HabiticaTaskEditor> {
  final _controllers = <String, TextEditingController>{};
  final _changes = <String, dynamic>{};
  late Map<String, dynamic> _native;
  late String _type;
  Map<String, dynamic>? _options;
  bool _busy = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _native = Map.of(widget.task?.native ?? {});
    _type = _native['type'] as String? ?? 'todo';
    if (widget.task == null) _changes['type'] = _type;
    _loadOptions();
  }
  Future<void> _loadOptions() async {
    try {
      final options = await ref.read(apiClientProvider).habiticaOptions();
      if (mounted) setState(() => _options = options);
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
  }
  Future<void> _reloadNative() async {
    setState(() { _busy = true; _error = null; });
    try {
      final result = await ref.read(apiClientProvider).reconcileHabiticaTasks(widget.account);
      if (!result.isOk) throw StateError(result.error ?? 'Native Aufgaben nicht lesbar');
      final matches = widget.task == null ? const <Task>[] : result.items.where((t) => t.identity == widget.task!.identity).toList();
      final current = matches.isEmpty ? null : matches.single;
      if (widget.task != null && current == null) {
        throw StateError('Native Aufgabe in der Aktualisierung nicht gefunden.');
      }
      if (mounted && current != null) setState(() => _native = Map.of(current.native));
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Native Aufgabe endgültig löschen?'), content: Text(widget.task!.title), actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Löschen'))]));
    if (sure != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final task = widget.task!;
      await ref.read(apiClientProvider).deleteTask(task.uid, provider: task.provider, account: task.account);
      if (mounted) Navigator.pop(context);
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<void> _editReminder(int index) async {
    final reminders = List<Map<String, dynamic>>.from((value('reminders', []) as List).map((r) => Map<String, dynamic>.from(r as Map)));
    final item = reminders[index];
    final time = await _pickTime(item['time'] as String?);
    if (time == null || !mounted) return;
    reminders[index] = {...item, 'time': time};
    setState(() => _changes['reminders'] = reminders);
  }
  @override
  void dispose() { for (final c in _controllers.values) { c.dispose(); } super.dispose(); }
  dynamic value(String key, [dynamic fallback]) => _changes.containsKey(key) ? _changes[key] : _native[key] ?? fallback;
  bool get _writable => !_busy && _options?['writes_enabled'] == true && !ref.read(apiClientProvider).nativeTaskBlocked(widget.account);
  TextEditingController controller(String key) => _controllers.putIfAbsent(key, () => TextEditingController(text: value(key)?.toString() ?? ''));
  Widget field(String key, String label, {bool number = false, int maxLines = 1}) => TextField(
    key: Key('native-$key'), controller: controller(key), enabled: _writable,
    minLines: 1, maxLines: maxLines,
    decoration: InputDecoration(labelText: label),
    keyboardType: number ? TextInputType.number : (maxLines > 1 ? TextInputType.multiline : TextInputType.text),
    onChanged: (text) => _changes[key] = number ? num.tryParse(text) : text,
  );

  /// Datum mit Auswahl statt ISO-Text. Gespeichert wird wie in Habitica: Mitternacht Ortszeit als UTC-ISO.
  Widget dateField(String key, String label) {
    final raw = value(key) as String?;
    final date = raw == null || raw.isEmpty ? null : DateTime.tryParse(raw)?.toLocal();
    return InputDecorator(
      key: Key('native-$key'),
      decoration: InputDecoration(
        labelText: label,
        enabled: _writable,
        suffixIcon: date == null || !_writable
            ? const Icon(Icons.calendar_today_outlined)
            : IconButton(tooltip: 'Datum entfernen', icon: const Icon(Icons.clear), onPressed: () => setState(() => _changes[key] = null)),
      ),
      child: InkWell(
        onTap: !_writable ? null : () async {
          final now = DateTime.now();
          final picked = await showDatePicker(context: context, initialDate: date ?? now,
              firstDate: DateTime(now.year - 5), lastDate: DateTime(now.year + 10));
          if (picked != null) setState(() => _changes[key] = DateTime(picked.year, picked.month, picked.day).toUtc().toIso8601String());
        },
        child: Text(date == null ? 'Kein Datum' : DateFormat('EEE, d. MMMM y', 'de_DE').format(date)),
      ),
    );
  }
  Widget toggle(String key, String label, [bool fallback = false]) => SwitchListTile(
    title: Text(label), value: value(key, fallback) == true,
    onChanged: !_writable ? null : (v) => setState(() => _changes[key] = v));
  Widget choice(String key, String label, Map<String, String> values, [String? fallback]) => DropdownButtonFormField<String>(
    initialValue: value(key, fallback) as String?, decoration: InputDecoration(labelText: label),
    items: [for (final v in values.entries) DropdownMenuItem(value: v.key, child: Text(v.value))],
    onChanged: !_writable ? null : (v) => setState(() => _changes[key] = v));

  static const _types = {'todo': 'To-do', 'daily': 'Tägliche Aufgabe', 'habit': 'Gewohnheit', 'reward': 'Belohnung'};
  static const _attributes = {'str': 'Stärke', 'int': 'Intelligenz', 'per': 'Wahrnehmung', 'con': 'Ausdauer'};
  static final _priorities = <num, String>{0.1: 'Trivial', 1: 'Leicht', 1.5: 'Mittel', 2: 'Schwer'};
  static const _frequencies = {'daily': 'Täglich', 'weekly': 'Wöchentlich', 'monthly': 'Monatlich', 'yearly': 'Jährlich'};

  /// Erinnerungszeit: Habitica speichert ein ISO-Datum, für Erinnerungen zählt nur die Uhrzeit.
  Future<String?> _pickTime([String? current]) async {
    final parsed = current == null ? null : DateTime.tryParse(current)?.toLocal();
    final t = await showTimePicker(context: context,
        initialTime: parsed == null ? const TimeOfDay(hour: 9, minute: 0) : TimeOfDay.fromDateTime(parsed));
    if (t == null) return null;
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day, t.hour, t.minute).toUtc().toIso8601String();
  }

  String _timeLabel(Object? iso) {
    final d = iso is String ? DateTime.tryParse(iso)?.toLocal() : null;
    return d == null ? '–' : DateFormat('HH:mm', 'de_DE').format(d);
  }
  Future<void> _save() async {
    setState(() { _busy = true; _error = null; });
    try {
      if (widget.task == null && !_changes.containsKey('text')) _changes['text'] = controller('text').text;
      if (value('text', '').toString().trim().isEmpty) throw const FormatException('Titel fehlt');
      await ref.read(apiClientProvider).saveNativeTask(widget.account, _changes, uid: widget.task?.uid, expectedVersion: _native['updatedAt'] as String?);
      if (mounted) Navigator.of(context).pop();
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  Future<String?> _ask(String title, [String initial = '']) {
    var value = initial;
    return showDialog<String>(context: context, builder: (ctx) => AlertDialog(title: Text(title),
      content: TextFormField(initialValue: initial, autofocus: true, onChanged: (text) => value = text),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
        FilledButton(onPressed: () => Navigator.pop(ctx, value), child: const Text('Übernehmen'))]));
  }
  Future<void> _checklist(String action, {String? id, String? text, bool? completed, int? position}) async {
    setState(() { _busy = true; _error = null; });
    try {
      final current = await ref.read(apiClientProvider).nativeTaskActionAndRefresh(widget.task!, action, itemId: id, fields: {if (text != null) 'text': text, if (completed != null) 'completed': completed, if (position != null) 'position': position});
      if (_changes.keys.any((key) => jsonEncode(_native[key]) != jsonEncode(current.native[key]))) {
        throw StateError('Native Aktion bestätigt, aber bearbeitete Felder wurden extern geändert. Neu laden, nichts überschreiben.');
      }
      if (mounted) setState(() => _native = Map.of(current.native));
      await refreshTasks(ref);
    } catch (e) { if (mounted) setState(() => _error = errorText(e)); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  Widget build(BuildContext context) {
    final enabled = _writable;
    final theme = Theme.of(context);
    final frequency = value('frequency', 'weekly') as String?;
    final reminders = (value('reminders', []) as List);
    final checklist = (_native['checklist'] as List? ?? const []).cast<Map>();
    Widget section(String title) => Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(title, style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary)));

    final items = <Widget>[
      if (_options?['writes_enabled'] != true)
        Text('Nur Ansicht – Änderungen an Habitica sind für dieses Konto nicht freigegeben.',
            style: TextStyle(color: theme.colorScheme.onSurfaceVariant)),
      DropdownButtonFormField<String>(initialValue: _type,
        decoration: InputDecoration(labelText: widget.task == null ? 'Art' : 'Art (nach dem Anlegen nicht änderbar)'),
        items: [for (final t in _types.entries) DropdownMenuItem(value: t.key, child: Text(t.value))],
        onChanged: widget.task != null || !_writable ? null : (v) => setState(() { _type = v!; _changes.removeWhere((key, _) => !['text','notes','alias','attribute','priority','tags','reminders'].contains(key)); _changes['type'] = v; })),
      field('text', 'Titel'),
      field('notes', 'Notizen', maxLines: 4),
      Row(children: [
        Expanded(child: DropdownButtonFormField<num>(initialValue: value('priority', 1) as num, decoration: const InputDecoration(labelText: 'Schwierigkeit'),
          items: [for (final p in _priorities.entries) DropdownMenuItem(value: p.key, child: Text(p.value))],
          onChanged: !_writable ? null : (v) => setState(() => _changes['priority'] = v))),
        const SizedBox(width: 12),
        Expanded(child: choice('attribute', 'Attribut', _attributes, 'str')),
      ]),
      if (_type == 'todo') dateField('date', 'Fällig am'),
      if (_type == 'reward') field('value', 'Kosten (Gold)', number: true),
      if (_type == 'habit') ...[
        toggle('up', 'Plus zulassen', true),
        toggle('down', 'Minus zulassen', true),
        choice('frequency', 'Zähler zurücksetzen', const {'daily': 'Täglich', 'weekly': 'Wöchentlich', 'monthly': 'Monatlich'}, 'daily'),
      ],
      if (_type == 'daily') ...[
        section('Wiederholung'),
        Row(children: [
          Expanded(child: choice('frequency', 'Rhythmus', _frequencies, 'weekly')),
          const SizedBox(width: 12),
          SizedBox(width: 120, child: field('everyX', switch (frequency) {
            'daily' => 'Alle … Tage', 'monthly' => 'Alle … Monate', 'yearly' => 'Alle … Jahre', _ => 'Alle … Wochen' }, number: true)),
        ]),
        if (frequency == 'weekly' || frequency == null)
          Wrap(spacing: 6, runSpacing: 6, children: [for (final d in const {'m':'Mo','t':'Di','w':'Mi','th':'Do','f':'Fr','s':'Sa','su':'So'}.entries) FilterChip(
            label: Text(d.value), selected: (value('repeat', {}) as Map)[d.key] != false,
            onSelected: !_writable ? null : (v) => setState(() => _changes['repeat'] = {...value('repeat', {}) as Map, d.key: v}))]),
        if (frequency == 'monthly')
          for (final pair in const {'daysOfMonth': 'Tage im Monat (z. B. 1, 15)', 'weeksOfMonth': 'Wochen im Monat (1–5)'}.entries)
            TextFormField(initialValue: (value(pair.key, []) as List).join(', '), decoration: InputDecoration(labelText: pair.value),
              enabled: _writable, onChanged: (s) => _changes[pair.key] = s.trim().isEmpty ? [] : s.split(',').map((n) => int.tryParse(n.trim())).toList()),
        dateField('startDate', 'Beginnt am'),
        field('streak', 'Serie (Tage in Folge)', number: true),
      ],
      if (_options != null && (_options!['tags'] as List).isNotEmpty) ...[
        section('Tags'),
        Wrap(spacing: 6, runSpacing: 6, children: [for (final tag in _options!['tags'] as List) FilterChip(
          label: Text(tag['name'] as String), selected: (value('tags', []) as List).contains(tag['id']),
          onSelected: !_writable ? null : (selected) => setState(() {
            final tags = List<String>.from(value('tags', []) as List);
            if (selected) { tags.add(tag['id'] as String); } else { tags.remove(tag['id']); }
            _changes['tags'] = tags;
          }))]),
      ],
      if (_type == 'todo' || _type == 'daily') ...[
        section('Unterpunkte'),
        if (widget.task == null)
          Text('Unterpunkte kannst du nach dem Anlegen hinzufügen.', style: TextStyle(color: theme.colorScheme.onSurfaceVariant))
        else ...[
          for (final entry in checklist.asMap().entries) Builder(builder: (_) {
            final item = entry.value;
            return ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Checkbox(shape: const CircleBorder(), value: item['completed'] == true,
                  onChanged: enabled ? (_) => _checklist('checklist_edit', id: item['id'] as String, completed: item['completed'] != true) : null),
              title: Text(item['text'] as String? ?? ''),
              onTap: enabled ? () async { final text = await _ask('Unterpunkt bearbeiten', item['text'] as String? ?? ''); if (text != null) await _checklist('checklist_edit', id: item['id'] as String, text: text); } : null,
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                IconButton(tooltip: 'Unterpunkt nach oben', icon: const Icon(Icons.arrow_upward), onPressed: enabled && entry.key > 0 ? () => _checklist('checklist_move', id: item['id'] as String, position: entry.key - 1) : null),
                IconButton(tooltip: 'Unterpunkt löschen', icon: const Icon(Icons.delete_outline), onPressed: enabled ? () => _checklist('checklist_delete', id: item['id'] as String) : null),
              ]));
          }),
          Align(alignment: Alignment.centerLeft, child: TextButton.icon(icon: const Icon(Icons.add), label: const Text('Unterpunkt hinzufügen'),
            onPressed: enabled ? () async { final text = await _ask('Unterpunkt hinzufügen'); if (text != null) await _checklist('checklist_add', text: text); } : null)),
          toggle('collapseChecklist', 'Unterpunkte eingeklappt zeigen'),
        ],
      ],
      section('Erinnerungen'),
      for (final entry in reminders.asMap().entries) ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.alarm),
        title: Text(_timeLabel(entry.value['time'])),
        onTap: !_writable ? null : () => _editReminder(entry.key),
        trailing: IconButton(tooltip: 'Erinnerung entfernen', icon: const Icon(Icons.delete_outline), onPressed: !_writable ? null : () => setState(() {
          final list = List<Map<String, dynamic>>.from((value('reminders', []) as List).map((r) => Map<String, dynamic>.from(r as Map)));
          list.removeAt(entry.key); _changes['reminders'] = list;
        }))),
      Align(alignment: Alignment.centerLeft, child: TextButton.icon(icon: const Icon(Icons.add_alarm), label: const Text('Erinnerung hinzufügen'),
        onPressed: !_writable ? null : () async {
          final time = await _pickTime();
          if (time == null || !mounted) return;
          // UUID wird von derselben vorhandenen Operationsquelle im ApiClient vergeben.
          final id = ref.read(apiClientProvider).newNativeId();
          setState(() => _changes['reminders'] = [...value('reminders', []) as List, {'id': id, 'time': time}]);
        })),
      if (_busy) const LinearProgressIndicator(),
      if (ref.read(apiClientProvider).nativeTaskBlocked(widget.account))
        const Text('Änderung bestätigt, Aktualisierung fehlgeschlagen. Bitte ausdrücklich neu laden; nicht wiederholen.', style: TextStyle(fontWeight: FontWeight.bold)),
      if (_error != null) Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
      FilledButton(key: const Key('native-save'), onPressed: enabled ? _save : null, child: const Text('Speichern')),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.task == null ? 'Neue Habitica-Aufgabe' : 'Habitica-Aufgabe'),
        actions: [
          IconButton(tooltip: 'Aus Habitica neu laden', icon: const Icon(Icons.refresh), onPressed: _busy ? null : _reloadNative),
          if (widget.task != null) IconButton(tooltip: 'Aufgabe in Habitica löschen', icon: const Icon(Icons.delete_outline), onPressed: enabled ? _delete : null),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [for (final (i, w) in items.indexed) ...[if (i > 0) const SizedBox(height: 16), w]],
      ),
    );
  }
}
