import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models/common.dart';
import '../../models/shopping.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';
import '../templates/templates_screen.dart';
import '../lists/named_lists_screen.dart';

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
  bool _byRecipe = false; // view choice, remembered per device (#69)
  static const _byRecipeKey = 'shopping_group_by_recipe';

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((prefs) {
      if (mounted && prefs.getBool(_byRecipeKey) == true) setState(() => _byRecipe = true);
    }).catchError((_) {});
  }

  Future<void> _toggleView() async {
    setState(() => _byRecipe = !_byRecipe);
    try {
      (await SharedPreferences.getInstance()).setBool(_byRecipeKey, _byRecipe);
    } catch (_) {
      // not remembered: the view still switches
    }
  }

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
            key: const Key('shopping-view-toggle'),
            tooltip: _byRecipe ? l10n.shoppingShowAsList : l10n.shoppingGroupByRecipe,
            icon: Icon(_byRecipe ? Icons.view_list_outlined : Icons.restaurant_menu),
            onPressed: _toggleView,
          ),
          IconButton(
            tooltip: _showDone ? l10n.hideDone : l10n.showDone,
            icon: Icon(_showDone ? Icons.visibility_off_outlined : Icons.visibility_outlined),
            onPressed: () => setState(() => _showDone = !_showDone),
          ),
          PopupMenuButton<String>(
            key: const Key('shopping-menu'),
            onSelected: (v) {
              if (v == 'save') {
                saveShoppingAsTemplate(context, ref);
              } else {
                Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) => const TemplatesScreen(target: TemplateTarget.shopping)));
              }
            },
            itemBuilder: (_) => [
              PopupMenuItem(value: 'templates', child: Text(l10n.templates)),
              if (ref.read(canEditProvider)) PopupMenuItem(value: 'save', child: Text(l10n.templateSaveShopping)),
            ],
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
                if (_byRecipe) ..._byRecipeView(data) else ..._oneList(data),
                NamedListSections(kind: 'shopping', showDone: _showDone),
              ],
            );
          },
        ),
      ),
    );
  }

  /// One list. Source groups stay in the payload so a recipe item cannot be swiped away; they are not headings.
  List<Widget> _oneList(ShoppingData data) {
    bool isDone(ShoppingItem i) => _doneOverride[i.uid] ?? i.done;
    final rows = <(ShoppingItem, bool)>[
      for (final g in data.groups)
        for (final i in g.items)
          if (!_gone.contains(i.uid)) (i, g.isRecipes),
    ];
    final open = rows.where((r) => !isDone(r.$1)).toList();
    final visible = [...open, if (_showDone) ...rows.where((r) => isDone(r.$1))];
    return [
      Padding(
        key: const Key('group-manual'),
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Row(
          children: [
            const Icon(Icons.edit_note, size: 18),
            const SizedBox(width: 8),
            Text(l10n.mainList, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(width: 8),
            Text('${open.length}', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
      ),
      if (visible.isEmpty)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: Text(l10n.nothingOnList, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ),
      for (final (item, locked) in visible) locked ? _tile(item, isDone(item)) : _deletable(item, isDone(item)),
    ];
  }

  /// Items grouped by recipe (#69): one header per recipe, an item of several recipes shows under each of them,
  /// entries without a recipe come last.
  List<Widget> _byRecipeView(ShoppingData data) {
    bool isDone(ShoppingItem i) => _doneOverride[i.uid] ?? i.done;
    final entries = <(ShoppingItem, bool)>[
      for (final g in data.groups)
        for (final i in g.items)
          if (!_gone.contains(i.uid) && (_showDone || !isDone(i))) (i, g.isRecipes),
    ];
    final names = <String>[];
    for (final (item, _) in entries) {
      for (final r in item.recipes) {
        if (!names.contains(r)) names.add(r);
      }
    }
    List<Widget> section(String key, String title, IconData icon, List<(ShoppingItem, bool)> rows) => [
          Padding(
            key: Key('recipe-group-$key'),
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
            child: Row(
              children: [
                Icon(icon, size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
                const SizedBox(width: 8),
                Text('${rows.where((r) => !isDone(r.$1)).length}',
                    style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ],
            ),
          ),
          for (final (item, isRecipes) in rows)
            isRecipes ? _tile(item, isDone(item), scope: key) : _deletable(item, isDone(item), scope: key),
        ];
    final none = [for (final e in entries) if (e.$1.recipes.isEmpty) e];
    return [
      for (final name in names)
        ...section('r:$name', name, Icons.menu_book_outlined, [for (final e in entries) if (e.$1.recipes.contains(name)) e]),
      if (none.isNotEmpty || names.isEmpty)
        ...section('none', l10n.shoppingNoRecipe, Icons.edit_note, none),
      if (none.isEmpty && names.isEmpty)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: Text(l10n.nothingOnList, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ),
    ];
  }

  Widget _tile(ShoppingItem item, bool done, {String? scope}) => CheckboxListTile(
        key: Key(scope == null ? 'item-${item.uid}' : 'item-$scope-${item.uid}'),
        value: done,
        controlAffinity: ListTileControlAffinity.leading,
        title: Text(item.summary, style: done ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
        subtitle: _subtitle(item),
        // Gemerkt, noch nicht gesendet: kleine Wolke
        secondary: item.pending
            ? Tooltip(
                message: l10n.waitingForNetwork,
                child: Icon(Icons.cloud_upload_outlined, key: Key('pending-item-${item.uid}'), size: 18),
              )
            : null,
        onChanged: item.localOnly ? null : (v) => _toggle(item, v ?? false),
      );

  /// Description and, for an entry that serves several recipes (merged), "for 2 recipes".
  Widget? _subtitle(ShoppingItem item) {
    final parts = [
      if (item.description != null && item.description!.isNotEmpty) item.description!,
      if (item.recipes.length > 1) l10n.shoppingFromRecipeCount(item.recipes.length),
    ];
    return parts.isEmpty ? null : Text(parts.join(' · '));
  }

  /// Nur freie Artikel lassen sich wegwischen; Rezeptzutaten kommen aus Cookidoo.
  // Löschen ab Kind; Gäste dürfen nur hinzufügen und abhaken
  Widget _deletable(ShoppingItem item, bool done, {String? scope}) => item.localOnly || !ref.watch(canActProvider) ? _tile(item, done, scope: scope) : Dismissible(
        key: Key(scope == null ? 'dismiss-${item.uid}' : 'dismiss-$scope-${item.uid}'),
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
        child: _tile(item, done, scope: scope),
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
