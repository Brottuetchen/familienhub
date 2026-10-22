import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Shopping or task lists that stay off the main list. Filter by person, assign the list or one item.
class NamedListsScreen extends ConsumerStatefulWidget {
  final String kind;
  const NamedListsScreen({super.key, required this.kind});

  @override
  ConsumerState<NamedListsScreen> createState() => _NamedListsScreenState();
}

class _NamedListsScreenState extends ConsumerState<NamedListsScreen> {
  int? _person; // null = all
  late Future<List<Map<String, dynamic>>> _lists = _load();

  Future<List<Map<String, dynamic>>> _load() =>
      ref.read(apiClientProvider).namedLists(widget.kind, assigneeId: _person);

  void _reload() => setState(() => _lists = _load());

  Future<int?> _pickPerson({bool allowNone = true}) async {
    final people = await ref.read(peopleProvider.future);
    if (!mounted) return null;
    return showDialog<int>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(l10n.assignPerson),
        children: [
          if (allowNone) SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 0), child: Text(l10n.nobody)),
          for (final p in people) SimpleDialogOption(onPressed: () => Navigator.pop(ctx, p.id), child: Text(p.displayName)),
        ],
      ),
    );
  }

  Future<void> _create() async {
    final name = await _askName(l10n.namedListNew, '');
    if (name == null || !mounted) return;
    final person = await _pickPerson();
    if (!mounted || person == null) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).createNamedList(
          widget.kind, name, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<String?> _askName(String title, String initial) async {
    final controller = TextEditingController(text: initial);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(controller: controller, autofocus: true, decoration: InputDecoration(labelText: l10n.namedListName)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: Text(l10n.save)),
        ],
      ),
    );
    controller.dispose();
    return name == null || name.isEmpty ? null : name;
  }

  @override
  Widget build(BuildContext context) {
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.namedLists),
        actions: [
          DropdownButton<int>(
            value: _person ?? 0,
            underline: const SizedBox.shrink(),
            items: [
              DropdownMenuItem(value: 0, child: Text(l10n.allPeople)),
              for (final p in people) DropdownMenuItem(value: p.id, child: Text(p.displayName)),
            ],
            onChanged: (v) {
              _person = v == null || v == 0 ? null : v;
              _reload();
            },
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _create, icon: const Icon(Icons.add), label: Text(l10n.namedListNew)),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _lists,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: HubLoader());
          if (snap.hasError) return ErrorView(error: snap.error!, onRetry: _reload);
          final rows = snap.data ?? const [];
          if (rows.isEmpty) return Center(child: Text(l10n.namedListsEmpty));
          return ListView(children: [
            for (final row in rows)
              ListTile(
                title: Text(row['name'] as String? ?? ''),
                subtitle: Text(_personName(people, row['assignee_id'])),
                onTap: () async {
                  await Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => NamedListScreen(listId: row['id'] as int, kind: widget.kind)));
                  _reload();
                },
              ),
          ]);
        },
      ),
    );
  }
}

String _personName(List<Person> people, Object? id) {
  final n = id is int ? id : int.tryParse('$id');
  if (n == null) return l10n.nobody;
  for (final p in people) {
    if (p.id == n) return p.displayName;
  }
  return l10n.nobody;
}

class NamedListScreen extends ConsumerStatefulWidget {
  final int listId;
  final String kind;
  const NamedListScreen({super.key, required this.listId, required this.kind});

  @override
  ConsumerState<NamedListScreen> createState() => _NamedListScreenState();
}

class _NamedListScreenState extends ConsumerState<NamedListScreen> {
  late Future<Map<String, dynamic>> _list = _load();

  Future<Map<String, dynamic>> _load() => ref.read(apiClientProvider).namedList(widget.listId);
  void _reload() => setState(() => _list = _load());

  Future<int?> _pickPerson() async {
    final people = await ref.read(peopleProvider.future);
    if (!mounted) return null;
    return showDialog<int>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(l10n.assignPerson),
        children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(ctx, 0), child: Text(l10n.nobody)),
          for (final p in people) SimpleDialogOption(onPressed: () => Navigator.pop(ctx, p.id), child: Text(p.displayName)),
        ],
      ),
    );
  }

  Future<void> _assignList() async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedList(
          widget.listId, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _assignItem(String itemId) async {
    final person = await _pickPerson();
    if (person == null || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
          widget.listId, itemId, assigneeId: person == 0 ? null : person));
    if (ok) _reload();
  }

  Future<void> _add() async {
    final controller = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: TextField(controller: controller, autofocus: true, decoration: InputDecoration(labelText: l10n.item)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: Text(l10n.save)),
        ],
      ),
    );
    controller.dispose();
    if (text == null || text.isEmpty || !mounted) return;
    final ok = await runAction(context, () => ref.read(apiClientProvider).addNamedItem(widget.listId, text));
    if (ok) _reload();
  }

  @override
  Widget build(BuildContext context) {
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    return Scaffold(
      appBar: AppBar(
        title: FutureBuilder<Map<String, dynamic>>(
          future: _list,
          builder: (_, snap) => Text(snap.data?['name'] as String? ?? l10n.namedLists),
        ),
        actions: [
          IconButton(tooltip: l10n.assignPerson, onPressed: _assignList, icon: const Icon(Icons.person_outline)),
        ],
      ),
      floatingActionButton: FloatingActionButton(onPressed: _add, child: const Icon(Icons.add)),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _list,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: HubLoader());
          if (snap.hasError) return ErrorView(error: snap.error!, onRetry: _reload);
          final items = ((snap.data?['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().toList();
          if (items.isEmpty) return Center(child: Text(l10n.namedListsEmpty));
          return ListView(children: [
            for (final item in items)
              CheckboxListTile(
                value: item['done'] == true,
                onChanged: (v) async {
                  final ok = await runAction(context, () => ref.read(apiClientProvider).patchNamedItem(
                        widget.listId, '${item['id']}', done: v == true));
                  if (ok) _reload();
                },
                title: Text(item['summary'] as String? ?? ''),
                subtitle: Text(_personName(people, item['assignee_id'])),
                secondary: IconButton(
                  tooltip: l10n.assignPerson,
                  icon: const Icon(Icons.person_outline),
                  onPressed: () => _assignItem('${item['id']}'),
                ),
              ),
          ]);
        },
      ),
    );
  }
}
