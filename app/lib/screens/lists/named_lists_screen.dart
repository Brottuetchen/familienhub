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

  Future<String?> _ask(String title, String label) async {
    final controller = TextEditingController();
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
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const SizedBox(width: 8),
                DropdownButton<int>(
                  key: Key('list-filter-${widget.kind}'),
                  value: _person ?? 0,
                  underline: const SizedBox.shrink(),
                  items: [
                    DropdownMenuItem(value: 0, child: Text(l10n.allPeople)),
                    for (final p in people) DropdownMenuItem(value: p.id, child: Text(p.displayName)),
                  ],
                  onChanged: (v) => setState(() => _person = v == null || v == 0 ? null : v),
                ),
                const Spacer(),
                TextButton(onPressed: _create, child: Text(l10n.namedListNew)),
              ],
            ),
            if (snap.hasError)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TextButton(onPressed: _reload, child: Text(l10n.retry)),
              ),
            for (final row in rows) _section(row, people),
          ],
        );
      },
    );
  }

  Widget _section(Map<String, dynamic> row, List<Person> people) {
    final id = row['id'] as int;
    final who = _who(people, row['assignee_id']);
    final name = row['name'] as String? ?? '';
    final items = ((row['items'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .where((i) => widget.showDone || i['done'] != true)
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          key: Key('named-list-$id'),
          padding: const EdgeInsets.fromLTRB(16, 12, 4, 0),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  who.isEmpty ? l10n.namedListHeadingPlain(name) : l10n.namedListHeading(name, who),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              IconButton(tooltip: l10n.item, icon: const Icon(Icons.add), onPressed: () => _add(id)),
              IconButton(
                tooltip: l10n.assignPerson,
                icon: const Icon(Icons.person_outline),
                onPressed: () => _assignList(id),
              ),
            ],
          ),
        ),
        for (var i = 0; i < items.length; i++) _item(id, i + 1, items[i], people),
      ],
    );
  }

  Widget _item(int listId, int n, Map<String, dynamic> item, List<Person> people) {
    final own = item['own_assignee'] == true ? _who(people, item['assignee_id']) : '';
    final summary = item['summary'] as String? ?? '';
    return CheckboxListTile(
      key: Key('named-item-$listId-${item['id']}'),
      value: item['done'] == true,
      controlAffinity: ListTileControlAffinity.leading,
      title: Text(own.isEmpty ? '$n. $summary' : '$n. $summary ${l10n.assignedItem(own)}'),
      secondary: IconButton(
        tooltip: l10n.assignPerson,
        icon: const Icon(Icons.person_outline),
        onPressed: () => _assignItem(listId, '${item['id']}'),
      ),
      onChanged: (v) async {
        final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
              listId, '${item['id']}', done: v == true));
        if (ok) _reload();
      },
    );
  }

  Future<void> _assignList(int id) async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedList(
          id, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _assignItem(int listId, String itemId) async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
          listId, itemId, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _add(int listId) async {
    final text = await _ask(l10n.item, l10n.item);
    if (text == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).addNamedItem(listId, text));
    if (ok) _reload();
  }
}
