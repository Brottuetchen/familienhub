import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'recipe_quick_view.dart';

final recipesProvider = FutureProvider.autoDispose.family<List<HubRecipe>, String>(
    (ref, query) => ref.watch(apiClientProvider).recipes(query: query));

String _meta(HubRecipe r) =>
    r.prepMinutes == null ? l10n.servingsOnly(r.servings) : l10n.servingsMinutes(r.servings, r.prepMinutes!);

/// The hub's recipe book. With [pickFor], tapping a recipe plans it on that day and closes with `true`.
class RecipesScreen extends ConsumerStatefulWidget {
  final DateTime? pickFor;
  const RecipesScreen({super.key, this.pickFor});

  @override
  ConsumerState<RecipesScreen> createState() => _RecipesScreenState();
}

class _RecipesScreenState extends ConsumerState<RecipesScreen> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _tap(HubRecipe r) async {
    final day = widget.pickFor;
    final result = await showRecipeQuickView(
      context,
      RecipeRef(source: 'hub', id: '${r.id}', title: r.title, url: r.sourceUrl, minutes: r.prepMinutes),
      planDay: day,
      canEdit: day == null,
    );
    if (!mounted) return;
    if (result == QuickViewResult.changed && day != null) {
      Navigator.pop(context, true);
    } else if (result == QuickViewResult.edit) {
      await Navigator.push(context, MaterialPageRoute(builder: (_) => RecipeDetailScreen(recipeId: r.id!)));
    }
    ref.invalidate(recipesProvider);
  }

  Future<void> _create() async {
    final saved = await Navigator.push<HubRecipe>(context, MaterialPageRoute(builder: (_) => const RecipeEditScreen()));
    if (saved != null) ref.invalidate(recipesProvider);
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = ref.watch(canEditProvider);
    final async = ref.watch(recipesProvider(_query));
    return Scaffold(
      appBar: AppBar(title: Text(widget.pickFor == null ? l10n.recipeBook : l10n.recipeFromBook)),
      floatingActionButton: canEdit
          ? FloatingActionButton.extended(
              key: const Key('recipe-new'),
              onPressed: _create,
              icon: const Icon(Icons.add),
              label: Text(l10n.newRecipe),
            )
          : null,
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: TextField(
            controller: _search,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(prefixIcon: const Icon(Icons.search), labelText: l10n.searchRecipes),
            onSubmitted: (v) => setState(() => _query = v.trim()),
            onChanged: (v) {
              if (v.isEmpty && _query.isNotEmpty) setState(() => _query = '');
            },
          ),
        ),
        Expanded(
          child: async.when(
            loading: () => const Center(child: HubLoader()),
            error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(recipesProvider)),
            data: (list) => list.isEmpty
                ? EmptyHint(icon: Icons.menu_book_outlined, text: _query.isNotEmpty
                    ? l10n.nothingFound
                    : canEdit ? l10n.noRecipes : l10n.noRecipesYet)
                : ListView(padding: const EdgeInsets.only(bottom: 96), children: [
                    for (final r in list)
                      ListTile(
                        key: ValueKey('recipe-${r.id}'),
                        leading: const Icon(Icons.restaurant_menu),
                        title: Text(r.title),
                        subtitle: Text(_meta(r)),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => _tap(r),
                      ),
                  ]),
          ),
        ),
      ]),
    );
  }
}

/// One recipe: ingredients, preparation, plan on a day, ingredients to the shopping list.
class RecipeDetailScreen extends ConsumerStatefulWidget {
  final int recipeId;
  const RecipeDetailScreen({super.key, required this.recipeId});

  @override
  ConsumerState<RecipeDetailScreen> createState() => _RecipeDetailScreenState();
}

class _RecipeDetailScreenState extends ConsumerState<RecipeDetailScreen> {
  late Future<HubRecipe> _future = _load();

  Future<HubRecipe> _load() => ref.read(apiClientProvider).recipe(widget.recipeId);

  Future<void> _plan(HubRecipe r) async {
    final now = DateTime.now();
    final day = await showDatePicker(
        context: context, initialDate: now, firstDate: now.subtract(const Duration(days: 7)), lastDate: now.add(const Duration(days: 365)));
    if (day == null || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).planRecipe(day, r.id!)) && mounted) {
      showInfo(context, l10n.plannedOn(dayLabel(day)));
    }
  }

  Future<void> _toShopping(HubRecipe r) async {
    try {
      final n = await ref.read(apiClientProvider).recipeToShopping(r.id!);
      if (mounted) showInfo(context, l10n.ingredientsToListCount(n));
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _edit(HubRecipe r) async {
    final saved = await Navigator.push<HubRecipe>(context, MaterialPageRoute(builder: (_) => RecipeEditScreen(recipe: r)));
    if (saved != null && mounted) setState(() => _future = _load());
  }

  Future<void> _delete(HubRecipe r) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.deleteRecipeQuestion),
        content: Text(l10n.deleteRecipeHint(r.title)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteRecipe(r.id!)) && mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = ref.watch(canEditProvider);
    final theme = Theme.of(context);
    return FutureBuilder<HubRecipe>(
      future: _future,
      builder: (context, snap) {
        final r = snap.data;
        return Scaffold(
          appBar: AppBar(
            title: Text(r?.title ?? l10n.recipeBook),
            actions: [
              if (r != null && canEdit) ...[
                IconButton(key: const Key('recipe-edit'), tooltip: l10n.editRecipe, icon: const Icon(Icons.edit_outlined), onPressed: () => _edit(r)),
                IconButton(key: const Key('recipe-delete'), tooltip: l10n.delete, icon: const Icon(Icons.delete_outline), onPressed: () => _delete(r)),
              ],
            ],
          ),
          body: snap.hasError
              ? ErrorView(error: snap.error!, onRetry: () => setState(() => _future = _load()))
              : r == null
                  ? const Center(child: HubLoader())
                  : ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
                      Text(_meta(r), style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                      if (r.description != null && r.description!.isNotEmpty) ...[const SizedBox(height: 8), Text(r.description!)],
                      if (canEdit) ...[
                        const SizedBox(height: 12),
                        Wrap(spacing: 8, runSpacing: 8, children: [
                          FilledButton.tonalIcon(
                              key: const Key('recipe-plan'), onPressed: () => _plan(r), icon: const Icon(Icons.event), label: Text(l10n.planOnDay)),
                          if (r.ingredients.isNotEmpty)
                            FilledButton.tonalIcon(
                                key: const Key('recipe-shopping'),
                                onPressed: () => _toShopping(r),
                                icon: const Icon(Icons.add_shopping_cart),
                                label: Text(l10n.ingredientsToList)),
                        ]),
                      ],
                      if (r.ingredients.isNotEmpty) ...[
                        const SizedBox(height: 20),
                        Text(l10n.ingredients, style: theme.textTheme.titleMedium),
                        for (final i in r.ingredients)
                          Padding(padding: const EdgeInsets.symmetric(vertical: 3), child: Text('•  $i')),
                      ],
                      if (r.instructions != null && r.instructions!.isNotEmpty) ...[
                        const SizedBox(height: 20),
                        Text(l10n.preparation, style: theme.textTheme.titleMedium),
                        const SizedBox(height: 6),
                        SelectableText(r.instructions!),
                      ],
                      if (r.sourceUrl != null) ...[
                        const SizedBox(height: 16),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            icon: const Icon(Icons.open_in_new),
                            label: Text(l10n.openLink),
                            onPressed: () => launchUrl(Uri.parse(r.sourceUrl!), mode: LaunchMode.externalApplication),
                          ),
                        ),
                      ],
                    ]),
        );
      },
    );
  }
}

/// Create or edit a recipe; closes with the saved recipe.
class RecipeEditScreen extends ConsumerStatefulWidget {
  final HubRecipe? recipe;
  const RecipeEditScreen({super.key, this.recipe});

  @override
  ConsumerState<RecipeEditScreen> createState() => _RecipeEditScreenState();
}

class _RecipeEditScreenState extends ConsumerState<RecipeEditScreen> {
  late final _title = TextEditingController(text: widget.recipe?.title);
  late final _ingredients = TextEditingController(text: widget.recipe?.ingredients.join('\n'));
  late final _instructions = TextEditingController(text: widget.recipe?.instructions);
  late final _servings = TextEditingController(text: '${widget.recipe?.servings ?? 2}');
  late final _minutes = TextEditingController(text: widget.recipe?.prepMinutes?.toString() ?? '');
  late final _link = TextEditingController(text: widget.recipe?.sourceUrl);
  bool _saving = false;

  @override
  void dispose() {
    for (final c in [_title, _ingredients, _instructions, _servings, _minutes, _link]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (_title.text.trim().isEmpty) {
      showInfo(context, l10n.titleMissing);
      return;
    }
    final recipe = HubRecipe(
      id: widget.recipe?.id,
      title: _title.text.trim(),
      description: widget.recipe?.description,
      ingredients: [for (final l in _ingredients.text.split('\n')) if (l.trim().isNotEmpty) l.trim()],
      instructions: _instructions.text.trim().isEmpty ? null : _instructions.text.trim(),
      servings: (int.tryParse(_servings.text.trim()) ?? 2).clamp(1, 50),
      prepMinutes: int.tryParse(_minutes.text.trim()),
      sourceUrl: _link.text.trim().isEmpty ? null : _link.text.trim(),
    );
    setState(() => _saving = true);
    try {
      final saved = await ref.read(apiClientProvider).saveRecipe(recipe);
      if (mounted) Navigator.pop(context, saved);
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showError(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(widget.recipe == null ? l10n.newRecipe : l10n.editRecipe),
          actions: [TextButton(key: const Key('recipe-save'), onPressed: _saving ? null : _save, child: Text(l10n.save))],
        ),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          TextField(key: const Key('recipe-title'), controller: _title, textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.title)),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: TextField(key: const Key('recipe-servings'), controller: _servings, keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: l10n.servings))),
            const SizedBox(width: 12),
            Expanded(child: TextField(key: const Key('recipe-minutes'), controller: _minutes, keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: l10n.minutesTotal))),
          ]),
          const SizedBox(height: 12),
          TextField(key: const Key('recipe-ingredients'), controller: _ingredients, minLines: 4, maxLines: null,
              decoration: InputDecoration(labelText: l10n.ingredients, helperText: l10n.ingredientsHint, alignLabelWithHint: true)),
          const SizedBox(height: 12),
          TextField(key: const Key('recipe-instructions'), controller: _instructions, minLines: 5, maxLines: null,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.preparation, alignLabelWithHint: true)),
          const SizedBox(height: 12),
          TextField(key: const Key('recipe-link'), controller: _link, keyboardType: TextInputType.url,
              decoration: InputDecoration(labelText: l10n.recipeLink)),
        ]),
      );
}
