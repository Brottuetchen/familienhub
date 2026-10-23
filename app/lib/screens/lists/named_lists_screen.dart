import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Named lists inside the shopping or task overview. Filter stays on that screen.
class NamedListSections extends ConsumerStatefulWidget {
  final String kind;
  final bool showDone;

  const NamedListSections({super.key, required this.kind, this.showDone = false});

  @override
  ConsumerState<NamedListSections> createState() => _NamedListSectionsState();
}

class _NamedListSectionsState extends ConsumerState<NamedListSections> {
  int? _person;
  late Future<List<Map<String, dynamic>>> _lists = _load();

  Future<List<Map<String, dynamic>>> _load() =>
      ref.read(apiClientProvider).namedLists(widget.kind, withItems: true);

  void _reload() => setState(() => _lists = _load());

  Future<int?> _pickPerson() async {
    final people = await ref.read(peopleProvider.future);
    if (!mounted) return null;
    return showDialog<int>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(l10n.assignPerson),
        children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 0), child: Text(l10n.nobody)),
          for (final p in people)
            SimpleDialogOption(onPressed: () => Navigator.pop(ctx, p.id), child: Text(p.displayName)),
        ],
      ),
    );
  }

  Future<String?> _ask(String title, String label, {String initial = ''}) async {
    final controller = TextEditingController(text: initial);
    final text = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(controller: controller, autofocus: true, decoration: InputDecoration(labelText: label)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: Text(l10n.save)),
        ],
      ),
    );
    controller.dispose();
    return text == null || text.isEmpty ? null : text;
  }

  Future<void> _create() async {
    final name = await _ask(l10n.namedListNew, l10n.namedListName);
    if (name == null || !mounted) return;
    final person = await _pickPerson();
    if (!mounted || person == null) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).createNamedList(
          widget.kind, name, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  String _who(List<Person> people, Object? id) {
    final n = id is int ? id : int.tryParse('$id');
    if (n == null) return '';
    for (final p in people) {
      if (p.id == n) return p.displayName;
    }
    return '';
  }

  Widget _filter(List<Person> people) => DropdownButton<int>(
        key: Key('list-filter-${widget.kind}'),
        value: _person ?? 0,
        underline: const SizedBox.shrink(),
        items: [
          DropdownMenuItem(value: 0, child: Text(l10n.allPeople)),
          for (final p in people) DropdownMenuItem(value: p.id, child: Text(p.displayName)),
        ],
        onChanged: (v) => setState(() => _person = v == null || v == 0 ? null : v),
      );

  Widget _plus() => IconButton(tooltip: l10n.namedListNew, icon: const Icon(Icons.add), onPressed: _create);

  String _title(String name, String who) => who.isEmpty ? name : '$name · $who';

  Widget _menu(int id, String name) => PopupMenuButton<String>(
        key: Key('named-list-menu-$id'),
        onSelected: (v) {
          if (v == 'item') _add(id);
          if (v == 'person') _assignList(id);
          if (v == 'rename') _rename(id, name);
          if (v == 'delete') _delete(id, name);
        },
        itemBuilder: (_) => [
          PopupMenuItem(value: 'item', child: Text(l10n.listEntry)),
          PopupMenuItem(value: 'person', child: Text(l10n.assignPerson)),
          PopupMenuItem(value: 'rename', child: Text(l10n.rename)),
          PopupMenuItem(value: 'delete', child: Text(l10n.delete)),
        ],
      );

  @override
  Widget build(BuildContext context) {
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _lists,
      builder: (context, snap) {
        final rows = (snap.data ?? const <Map<String, dynamic>>[]).where((row) {
          if (_person == null) return true;
          if (row['assignee_id'] == _person) return true;
          return ((row['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().any(
              (i) => i['own_assignee'] == true && i['assignee_id'] == _person);
        }).toList();
        final single = rows.length == 1 ? rows.first : null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (single == null)
              Row(children: [const SizedBox(width: 8), _filter(people), const Spacer(), _plus()]),
            if (snap.hasError)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TextButton(onPressed: _reload, child: Text(l10n.retry)),
              ),
            if (single != null) _one(single, people) else for (final row in rows) _section(row, people),
          ],
        );
      },
    );
  }

  List<Map<String, dynamic>> _visible(Map<String, dynamic> row) => ((row['items'] as List?) ?? const [])
      .whereType<Map<String, dynamic>>()
      .where((i) => widget.showDone || i['done'] != true)
      .toList();

  Widget _one(Map<String, dynamic> row, List<Person> people) {
    final id = row['id'] as int;
    final name = row['name'] as String? ?? '';
    final who = _who(people, row['assignee_id']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          key: Key('named-list-$id'),
          children: [
            const SizedBox(width: 8),
            _filter(people),
            Expanded(
              child: Text(_title(name, who),
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleMedium),
            ),
            _plus(),
            if (row['mine'] != false) _menu(id, name),
          ],
        ),
        for (final item in _visible(row)) _item(id, item, people, mine: row['mine'] != false),
      ],
    );
  }

  Widget _section(Map<String, dynamic> row, List<Person> people) {
    final id = row['id'] as int;
    final name = row['name'] as String? ?? '';
    final who = _who(people, row['assignee_id']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          key: Key('named-list-$id'),
          children: [
            const SizedBox(width: 16),
            Expanded(
              child: Text(_title(name, who),
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleMedium),
            ),
            if (row['mine'] != false) _menu(id, name),
          ],
        ),
        for (final item in _visible(row)) _item(id, item, people, mine: row['mine'] != false),
      ],
    );
  }

  Widget _item(int listId, Map<String, dynamic> item, List<Person> people, {required bool mine}) {
    final own = item['own_assignee'] == true ? _who(people, item['assignee_id']) : '';
    final summary = item['summary'] as String? ?? '';
    return CheckboxListTile(
      key: Key('named-item-$listId-${item['id']}'),
      value: item['done'] == true,
      controlAffinity: ListTileControlAffinity.leading,
      title: Text(own.isEmpty ? summary : '$summary ${l10n.assignedItem(own)}'),
      secondary: mine
          ? IconButton(
              key: Key('named-item-person-$listId-${item['id']}'),
              tooltip: l10n.assignPerson,
              icon: const Icon(Icons.person_outline),
              onPressed: () => _assignItem(listId, '${item['id']}'),
            )
          : null,
      onChanged: (v) async {
        final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
              listId, '${item['id']}', done: v == true));
        if (ok) _reload();
      },
    );
  }

  Future<void> _rename(int id, String current) async {
    final name = await _ask(l10n.rename, l10n.namedListName, initial: current);
    if (name == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedList(id, name: name));
    if (ok) _reload();
  }

  Future<void> _delete(int id, String name) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.delete),
        content: Text(name),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).deleteNamedList(id));
    if (ok) _reload();
  }

  Future<void> _assignItem(int listId, String itemId) async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
          listId, itemId, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _assignList(int id) async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedList(
          id, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _add(int listId) async {
    final text = await _ask(l10n.listEntry, l10n.listEntry);
    if (text == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).addNamedItem(listId, text));
    if (ok) _reload();
  }
}
