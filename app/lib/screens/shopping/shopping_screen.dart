import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants/colors.dart';
import '../../models/common.dart';
import '../../models/shopping.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Zuletzt eingegebene Artikel als Vorschläge (lokal, weil `/api/shopping/recent` noch leer ist).
class RecentItems {
  static const _key = 'shopping_recent';
  static const _max = 30;

  static Future<List<String>> load() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_key) ?? const [];
  }

  static Future<void> remember(String item) async {
    final prefs = await SharedPreferences.getInstance();
    final list = (prefs.getStringList(_key) ?? <String>[])
      ..removeWhere((e) => e.toLowerCase() == item.toLowerCase())
      ..insert(0, item);
    await prefs.setStringList(_key, list.take(_max).toList());
  }
}

class ShoppingScreen extends ConsumerStatefulWidget {
  const ShoppingScreen({super.key});

  @override
  ConsumerState<ShoppingScreen> createState() => _ShoppingScreenState();
}

class _ShoppingScreenState extends ConsumerState<ShoppingScreen> {
  /// Sofortige Rückmeldung beim Abhaken, bevor der Server antwortet.
  final _doneOverride = <String, bool>{};
  final _gone = <String>{};
  bool _showDone = false;

  Future<void> _reload() async {
    final ApiResult<ShoppingData> result;
    try {
      result = await ref.read(shoppingProvider.notifier).refresh();
    } catch (_) {
      return; // offline: Status-Symbol zeigt es, gemerkte Änderungen bleiben überlagert sichtbar
    }
    if (mounted) {
      setState(() {
        _doneOverride.clear();
        _gone.retainAll(result.data.groups.expand((g) => g.items).map((i) => i.uid));
      });
    }
  }

  Future<void> _toggle(ShoppingItem item, bool done) async {
    setState(() => _doneOverride[item.uid] = done);
    final ok = await runChange(context, () => ref.read(apiClientProvider).setShoppingDone(item.uid, done, name: item.summary));
    if (!ok && mounted) setState(() => _doneOverride.remove(item.uid));
  }

  Future<void> _add() async {
    final text = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => ProtectedReadModal(
        provider: shoppingProvider,
        child: const _AddItemSheet(),
      ),
    );
    if (text == null || text.trim().isEmpty || !mounted) return;
    final item = text.trim();
    final ok = await runChange(context, () => ref.read(apiClientProvider).addShoppingItem(item));
    if (ok) {
      await RecentItems.remember(item);
      await _reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(shoppingProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabShopping),
        actions: [
          ReadStatusIcon(result: async.valueOrNull),
          IconButton(
            tooltip: _showDone ? l10n.hideDone : l10n.showDone,
            icon: Icon(_showDone ? Icons.visibility_off_outlined : Icons.visibility_outlined),
            onPressed: () => setState(() => _showDone = !_showDone),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _add,
        icon: const Icon(Icons.add),
        label: Text(l10n.item),
      ),
      body: HubRefresh(
        onRefresh: _reload,
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: _reload),
          data: (result) {
            final data = result.data;
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: 96),
              children: [
                SourceBanner(source: 'Home Assistant', status: data.status, error: data.error),
                for (final group in data.groups) ..._group(group),
              ],
            );
          },
        ),
      ),
    );
  }

  List<Widget> _group(ShoppingGroup group) {
    bool isDone(ShoppingItem i) => _doneOverride[i.uid] ?? i.done;
    final items = group.items.where((i) => !_gone.contains(i.uid)).toList();
    final open = items.where((i) => !isDone(i)).toList();
    final done = items.where(isDone).toList();
    final visible = [...open, if (_showDone) ...done];
    return [
      Padding(
        key: Key('group-${group.key}'),
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Row(
          children: [
            Icon(group.isRecipes ? Icons.menu_book_outlined : Icons.edit_note,
                size: 18, color: group.isRecipes ? AppColors.cookidoo : null),
            const SizedBox(width: 8),
            Text(group.title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(width: 8),
            Text('${open.length}', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
      ),
      if (visible.isEmpty)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: Text(
            group.isRecipes ? l10n.noPlanIngredients : l10n.nothingOnList,
            style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
          ),
        ),
      for (final item in visible)
        group.isRecipes ? _tile(item, isDone(item)) : _deletable(item, isDone(item)),
    ];
  }

  Widget _tile(ShoppingItem item, bool done) => CheckboxListTile(
        key: Key('item-${item.uid}'),
        value: done,
        controlAffinity: ListTileControlAffinity.leading,
        title: Text(item.summary,
            style: done ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
        subtitle: item.description == null || item.description!.isEmpty ? null : Text(item.description!),
        // Gemerkt, noch nicht gesendet: kleine Wolke
        secondary: item.pending
            ? Tooltip(
                message: l10n.waitingForNetwork,
                child: Icon(Icons.cloud_upload_outlined, key: Key('pending-item-${item.uid}'), size: 18),
              )
            : null,
        onChanged: item.localOnly ? null : (v) => _toggle(item, v ?? false),
      );

  /// Nur freie Artikel lassen sich wegwischen; Rezeptzutaten kommen aus Cookidoo.
  // Löschen ab Kind; Gäste dürfen nur hinzufügen und abhaken
  Widget _deletable(ShoppingItem item, bool done) => item.localOnly || !ref.watch(canActProvider) ? _tile(item, done) : Dismissible(
        key: Key('dismiss-${item.uid}'),
        direction: DismissDirection.endToStart,
        background: Container(
          color: Theme.of(context).colorScheme.error,
          alignment: Alignment.centerRight,
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: const Icon(Icons.delete_outline, color: Colors.white),
        ),
        confirmDismiss: (_) => runChange(context, () => ref.read(apiClientProvider).deleteShoppingItem(item.uid, name: item.summary)),
        onDismissed: (_) {
          setState(() => _gone.add(item.uid));
          showInfo(context, l10n.removedTitle(item.summary));
        },
        child: _tile(item, done),
      );
}

class _AddItemSheet extends ConsumerStatefulWidget {
  const _AddItemSheet();

  @override
  ConsumerState<_AddItemSheet> createState() => _AddItemSheetState();
}

class _AddItemSheetState extends ConsumerState<_AddItemSheet> {
  final _text = TextEditingController();
  List<String> _recent = const [];

  @override
  void initState() {
    super.initState();
    // Eigene letzte Eingaben zuerst, dann was die Familie zuletzt gekauft hat (Server)
    RecentItems.load().then((local) async {
      if (mounted) setState(() => _recent = local);
      try {
        final server = await ref.read(apiClientProvider).shoppingRecent();
        final seen = local.map((e) => e.toLowerCase()).toSet();
        if (mounted) {
          setState(() => _recent = [...local, ...server.where((e) => seen.add(e.toLowerCase()))]);
        }
      } catch (_) {
        // offline: nur lokale Vorschläge
      }
    });
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final q = _text.text.trim().toLowerCase();
    final suggestions = _recent.where((r) => q.isEmpty || r.toLowerCase().contains(q)).take(12).toList();
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            key: const Key('shopping-input'),
            controller: _text,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(
              labelText: l10n.item,
              suffixIcon: IconButton(
                tooltip: l10n.add,
                icon: const Icon(Icons.send),
                onPressed: () => Navigator.pop(context, _text.text),
              ),
            ),
            onSubmitted: (v) => Navigator.pop(context, v),
          ),
          if (suggestions.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final s in suggestions)
                  ActionChip(label: Text(s), onPressed: () => Navigator.pop(context, s)),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
