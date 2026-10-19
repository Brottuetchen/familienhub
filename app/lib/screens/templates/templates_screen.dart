import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/list_template.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../tasks/habitica_tasks.dart' show refreshTasks;

/// Where a tapped template goes: the shopping list or the tasks (the entry point decides).
enum TemplateTarget { shopping, tasks }

/// Saves the open shopping list as a new template (asks for a name). Returns true when saved.
Future<bool> saveShoppingAsTemplate(BuildContext context, WidgetRef ref) async {
  final name = await _askName(context, l10n.templateSaveShopping);
  if (name == null || !context.mounted) return false;
  final ok = await runAction(context, () => ref.read(apiClientProvider).templateFromShopping(name));
  if (ok && context.mounted) showInfo(context, l10n.templateSaved);
  return ok;
}

Future<String?> _askName(BuildContext context, String title) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        key: const Key('template-name-dialog'),
        controller: controller,
        autofocus: true,
        textCapitalization: TextCapitalization.sentences,
        decoration: InputDecoration(labelText: l10n.name),
        onSubmitted: (v) => Navigator.pop(ctx, v.trim().isEmpty ? null : v.trim()),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, controller.text.trim().isEmpty ? null : controller.text.trim()),
          child: Text(l10n.save),
        ),
      ],
    ),
  );
}

class TemplatesScreen extends ConsumerStatefulWidget {
  final TemplateTarget target;
  const TemplatesScreen({super.key, required this.target});

  @override
  ConsumerState<TemplatesScreen> createState() => _TemplatesScreenState();
}

class _TemplatesScreenState extends ConsumerState<TemplatesScreen> {
  late Future<List<ListTemplate>> _future = ref.read(apiClientProvider).templates();

  void _reload() {
    setState(() {
      _future = ref.read(apiClientProvider).templates();
    });
  }

  Future<void> _edit([ListTemplate? template]) async {
    final saved = await Navigator.of(context)
        .push<bool>(MaterialPageRoute(builder: (_) => TemplateEditScreen(template: template)));
    if (saved == true) _reload();
  }

  Future<void> _delete(ListTemplate t) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.templateDeleteQuestion(t.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteTemplate(t.id))) _reload();
  }

  Future<void> _apply(ListTemplate t) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => TemplateApplySheet(template: t, target: widget.target),
    );
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = ref.watch(canEditProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.templates)),
      floatingActionButton: canEdit
          ? FloatingActionButton.extended(
              key: const Key('template-new'),
              onPressed: _edit,
              icon: const Icon(Icons.add),
              label: Text(l10n.templateNew),
            )
          : null,
      body: FutureBuilder<List<ListTemplate>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: HubLoader());
          if (snap.hasError) return ErrorView(error: snap.error!, onRetry: _reload);
          final items = snap.data ?? const [];
          if (items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.templatesEmpty, textAlign: TextAlign.center),
              ),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.only(bottom: 96),
            itemCount: items.length,
            itemBuilder: (context, i) {
              final t = items[i];
              return ListTile(
                key: Key('template-${t.id}'),
                title: Text(t.name),
                subtitle: Text(l10n.templateItemCount(t.items.length)),
                onTap: t.items.isEmpty ? null : () => _apply(t),
                trailing: canEdit
                    ? PopupMenuButton<String>(
                        key: Key('template-menu-${t.id}'),
                        onSelected: (v) => v == 'edit' ? _edit(t) : _delete(t),
                        itemBuilder: (_) => [
                          PopupMenuItem(value: 'edit', child: Text(l10n.templateEdit)),
                          PopupMenuItem(value: 'delete', child: Text(l10n.delete)),
                        ],
                      )
                    : null,
              );
            },
          );
        },
      ),
    );
  }
}

/// Pick a subset of the template's items and apply them to the shopping list or the tasks.
class TemplateApplySheet extends ConsumerStatefulWidget {
  final ListTemplate template;
  final TemplateTarget target;
  const TemplateApplySheet({super.key, required this.template, required this.target});

  @override
  ConsumerState<TemplateApplySheet> createState() => _TemplateApplySheetState();
}

class _TemplateApplySheetState extends ConsumerState<TemplateApplySheet> {
  late final Set<int> _picked = {for (final i in widget.template.items) if (i.id != null) i.id!};
  bool _family = false;
  bool _busy = false;

  Future<void> _apply() async {
    if (_picked.isEmpty) {
      showInfo(context, l10n.templateNothingSelected);
      return;
    }
    final api = ref.read(apiClientProvider);
    final all = _picked.length == widget.template.items.length;
    final ids = all ? null : _picked.toList();
    final shopping = widget.target == TemplateTarget.shopping;
    setState(() => _busy = true);
    TemplateApplied? result;
    final ok = await runAction(context, () async {
      result = shopping
          ? await api.applyTemplateToShopping(widget.template.id, itemIds: ids)
          : await api.applyTemplateToTasks(widget.template.id, itemIds: ids, family: _family);
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (!ok || result == null) return;
    final r = result!;
    if (shopping) {
      await ref.read(shoppingProvider.notifier).refresh().then((_) {}, onError: (_) {});
    } else {
      await refreshTasks(ref);
    }
    if (!mounted) return;
    final message = r.status == 'unavailable'
        ? l10n.templateListUnavailable
        : r.failed > 0
            ? l10n.templateAppliedPartial(r.failed)
            : shopping
                ? l10n.templateAppliedShopping(r.added, r.skipped)
                : l10n.templateAppliedTasks(r.added);
    final messenger = ScaffoldMessenger.of(context);
    Navigator.pop(context);
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.template;
    final shopping = widget.target == TemplateTarget.shopping;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
                  child: Text(t.name, style: Theme.of(context).textTheme.titleLarge),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Text(l10n.templatePickItems, style: Theme.of(context).textTheme.bodySmall),
                ),
                for (final i in t.items)
                  CheckboxListTile(
                    key: Key('template-item-${i.id}'),
                    value: _picked.contains(i.id),
                    onChanged: (v) => setState(() => v == true ? _picked.add(i.id!) : _picked.remove(i.id)),
                    title: Text(i.name),
                    subtitle: i.note.isEmpty ? null : Text(i.note),
                    controlAffinity: ListTileControlAffinity.leading,
                  ),
                if (!shopping)
                  SwitchListTile(
                    key: const Key('template-family'),
                    value: _family,
                    onChanged: (v) => setState(() => _family = v),
                    title: Text(l10n.templateFamilyList),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: FilledButton(
              key: const Key('template-apply'),
              onPressed: _busy ? null : _apply,
              child: Text(shopping ? l10n.templateApplyShopping : l10n.templateApplyTasks),
            ),
          ),
        ],
      ),
    );
  }
}

class _Row {
  final TextEditingController name;
  final TextEditingController note;
  _Row(String n, String o)
      : name = TextEditingController(text: n),
        note = TextEditingController(text: o);
  void dispose() {
    name.dispose();
    note.dispose();
  }
}

/// Create or edit a template (partner and admin only; the server checks too).
class TemplateEditScreen extends ConsumerStatefulWidget {
  final ListTemplate? template;
  const TemplateEditScreen({super.key, this.template});

  @override
  ConsumerState<TemplateEditScreen> createState() => _TemplateEditScreenState();
}

class _TemplateEditScreenState extends ConsumerState<TemplateEditScreen> {
  late final _name = TextEditingController(text: widget.template?.name ?? '');
  late final List<_Row> _rows = [for (final i in widget.template?.items ?? const <TemplateItem>[]) _Row(i.name, i.note)];

  @override
  void initState() {
    super.initState();
    if (_rows.isEmpty) _rows.add(_Row('', ''));
  }

  @override
  void dispose() {
    _name.dispose();
    for (final r in _rows) {
      r.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) return;
    final items = [
      for (final r in _rows)
        if (r.name.text.trim().isNotEmpty) TemplateItem(name: r.name.text.trim(), note: r.note.text.trim()),
    ];
    final ok = await runAction(
        context, () => ref.read(apiClientProvider).saveTemplate(widget.template?.id, name, items));
    if (ok && mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.template == null ? l10n.templateNew : l10n.templateEdit),
        actions: [TextButton(key: const Key('template-save'), onPressed: _save, child: Text(l10n.save))],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            key: const Key('template-name'),
            controller: _name,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.name),
          ),
          const SizedBox(height: 16),
          for (var n = 0; n < _rows.length; n++)
            Padding(
              key: ObjectKey(_rows[n]),
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      children: [
                        TextField(
                          key: Key('template-row-name-$n'),
                          controller: _rows[n].name,
                          textCapitalization: TextCapitalization.sentences,
                          decoration: InputDecoration(labelText: l10n.templateItemName),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          key: Key('template-row-note-$n'),
                          controller: _rows[n].note,
                          decoration: InputDecoration(labelText: l10n.templateItemNote),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: l10n.templateRemoveItem,
                    icon: const Icon(Icons.close),
                    onPressed: () => setState(() => _rows.removeAt(n).dispose()),
                  ),
                ],
              ),
            ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const Key('template-add-item'),
              onPressed: () => setState(() => _rows.add(_Row('', ''))),
              icon: const Icon(Icons.add),
              label: Text(l10n.templateAddItem),
            ),
          ),
        ],
      ),
    );
  }
}
