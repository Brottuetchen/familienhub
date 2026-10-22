import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/colors.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'cookidoo_search_screen.dart';
import 'recipe_quick_view.dart';
import 'recipes_screen.dart';
import '../../l10n/l10n.dart';

class MealsScreen extends ConsumerStatefulWidget {
  const MealsScreen({super.key});

  @override
  ConsumerState<MealsScreen> createState() => _MealsScreenState();
}

class _MealsScreenState extends ConsumerState<MealsScreen> {
  DateTime _monday = mondayOf(DateTime.now());

  String get _week => isoWeekOf(_monday);

  // Calendar days, not 24-hour steps: a 7-day Duration crosses the autumn clock change
  // and lands on the day before (midnight plus 168 hours is still the previous evening).
  void _shiftWeek(int weeks) =>
      setState(() => _monday = DateTime(_monday.year, _monday.month, _monday.day + 7 * weeks));

  Future<void> _reload() async {
    await ref.read(mealsProvider(_week).notifier).refresh();
  }

  bool get _planning => ref.read(appModulesProvider).has('meal_planning');

  /// Tapping a plan entry with a recipe (hub book, Cookidoo, Mealie) opens the recipe quick view.
  Future<void> _openRecipe(DateTime day, MealEntry entry) async {
    final api = ref.read(apiClientProvider);
    final hub = entry.hubRecipeId != null;
    final id = hub ? '${entry.hubRecipeId}' : entry.cookidooId!;
    final result = await showRecipeQuickView(
      context,
      RecipeRef(source: entry.source, id: id, title: entry.title, image: entry.image, url: entry.url, minutes: entry.minutes,
          sourceLabel: entry.sourceLabel),
      onRemove: hub
          ? (entry.id == null ? null : () => api.deleteMeal(entry.id!))
          : () => entry.isCookidoo ? api.unplanCookidoo(day, id) : api.unplanFromSource(entry.source, day, id),
    );
    if (!mounted) return;
    if (result == QuickViewResult.changed) await _reload();
  }

  Future<void> _addMeal(DateTime day) async {
    // Recipe sources (Cookidoo, Mealie …); older servers without the endpoint: Cookidoo if the module is on
    var sources = <RecipeSource>[];
    try {
      sources = await ref.read(apiClientProvider).recipeSources();
    } catch (_) {
      if (_planning) sources = const [RecipeSource('cookidoo', 'Cookidoo')];
    }
    if (!mounted) return;
    {
      final choice = await showModalBottomSheet<String>(
        context: context,
        builder: (ctx) => SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.edit_outlined),
                title: Text(l10n.ownDish),
                onTap: () => Navigator.pop(ctx, 'own'),
              ),
              ListTile(
                key: const Key('meal-from-book'),
                leading: const Icon(Icons.restaurant_menu),
                title: Text(l10n.recipeFromBook),
                onTap: () => Navigator.pop(ctx, 'book'),
              ),
              for (final s in sources)
                ListTile(
                  key: Key('meal-from-${s.id}'),
                  leading: const Icon(Icons.menu_book_outlined),
                  title: Text(s.id == 'cookidoo' ? l10n.recipeFromCookidoo : l10n.recipeFromSource(s.name)),
                  onTap: () => Navigator.pop(ctx, s.id),
                ),
            ],
          ),
        ),
      );
      if (choice == null || !mounted) return;
      if (choice == 'book') {
        final planned = await Navigator.push<bool>(
            context, MaterialPageRoute(builder: (_) => RecipesScreen(pickFor: day)));
        if (planned == true && mounted) await _reload();
        return;
      }
      if (choice != 'own') {
        final source = sources.firstWhere((s) => s.id == choice);
        final planned = await Navigator.push<bool>(context, MaterialPageRoute(
            builder: (_) => CookidooSearchScreen(day: day, source: source.id, sourceName: source.name)));
        if (planned == true && mounted) await _reload();
        return;
      }
    }
    if (!mounted) return;
    final title = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final c = TextEditingController();
        return AlertDialog(
          title: Text(l10n.mealOn(localDate('EEEE').format(day))),
          content: TextField(
            controller: c,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.dish),
            onSubmitted: (v) => Navigator.pop(ctx, v),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
            FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: Text(l10n.save)),
          ],
        );
      },
    );
    if (title == null || title.trim().isEmpty || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).addMeal(day, title.trim()))) {
      await _reload();
    }
  }

  Future<void> _deleteMeal(MealEntry entry) async {
    final id = entry.id;
    if (id == null) return;
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => ProtectedReadModal(
        provider: mealsProvider(_week),
        child: AlertDialog(
        title: Text(l10n.deleteEntryQuestion),
        content: Text(l10n.removeFromPlanHint(entry.title)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
        ),
      ),
    );
    if (sure != true || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteMeal(id))) {
      await _reload();
    }
  }

  Future<void> _cookidooAction(DateTime day, MealEntry entry, String action) async {
    final api = ref.read(apiClientProvider);
    final id = entry.cookidooId!;
    final cookidoo = entry.isCookidoo; // Cookidoo keeps its own endpoints, other sources use /api/recipe-sources
    switch (action) {
      case 'shopping':
        try {
          if (cookidoo) {
            final n = await api.cookidooToShopping([id]);
            if (mounted) showInfo(context, l10n.ingredientsOnCookidooList(n));
          } else {
            await api.sourceToShopping(entry.source, [id]);
            if (mounted) showInfo(context, l10n.ingredientsToList);
          }
        } catch (e) {
          if (mounted) showError(context, e);
        }
      case 'open':
        if (entry.url != null) await launchUrl(Uri.parse(entry.url!), mode: LaunchMode.externalApplication);
      case 'remove':
        if (await runAction(context, () => cookidoo ? api.unplanCookidoo(day, id) : api.unplanFromSource(entry.source, day, id))) {
          await _reload();
        }
    }
  }

  Future<void> _toShoppingList() async {
    try {
      final message = await ref.read(apiClientProvider).mealsToShoppingList(
          start: _monday, end: DateTime(_monday.year, _monday.month, _monday.day + 6));
      if (mounted) showInfo(context, message);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(mealsProvider(_week));
    final sunday = _monday.add(const Duration(days: 6));
    final range = '${localDate('d.M.').format(_monday)} – ${localDate('d.M.').format(sunday)}';
    final isCurrent = _monday == mondayOf(DateTime.now());

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabMeals),
        actions: [
          ReadStatusIcon(result: async.valueOrNull),
          IconButton(
            key: const Key('meals-recipe-book'),
            tooltip: l10n.recipeBook,
            icon: const Icon(Icons.restaurant_menu),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const RecipesScreen())),
          ),
          if (ref.watch(canEditProvider))
            IconButton(
              tooltip: l10n.ingredientsNext7Days,
              icon: const Icon(Icons.add_shopping_cart),
              onPressed: _toShoppingList,
            ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                IconButton(tooltip: l10n.previousWeek, onPressed: () => _shiftWeek(-1), icon: const Icon(Icons.chevron_left)),
                Expanded(
                  child: TextButton(
                    onPressed: isCurrent ? null : () => setState(() => _monday = mondayOf(DateTime.now())),
                    child: Text(isCurrent ? l10n.thisWeekRange(range) : l10n.weekNumberRange(_week.split('W').last, range)),
                  ),
                ),
                IconButton(tooltip: l10n.nextWeek, onPressed: () => _shiftWeek(1), icon: const Icon(Icons.chevron_right)),
              ],
            ),
          ),
          Expanded(
            child: HubRefresh(
              onRefresh: _reload,
              child: async.when(
                loading: () => const Center(child: HubLoader()),
                error: (e, _) => ErrorView(error: e, onRetry: _reload),
                data: (result) => ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 24),
                  children: [
                    SourceBanner(source: 'Cookidoo', status: result.data.status, error: result.data.error),
                    for (final day in result.data.days) _DayTile(
                      day: day,
                      planning: ref.watch(appModulesProvider).has('meal_planning'),
                      editable: ref.watch(canEditProvider),
                      onAdd: () => _addMeal(day.date),
                      onDelete: _deleteMeal,
                      onCookidoo: (entry, action) => _cookidooAction(day.date, entry, action),
                      onOpenRecipe: (entry) => _openRecipe(day.date, entry),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  final MealDay day;
  final bool planning;

  /// Essensplan ändern erst ab Partner; Kind und Gast sehen ihn nur.
  final bool editable;
  final VoidCallback onAdd;
  final ValueChanged<MealEntry> onDelete;
  final void Function(MealEntry entry, String action) onCookidoo;
  final ValueChanged<MealEntry>? onOpenRecipe;
  const _DayTile({
    required this.day,
    required this.planning,
    this.editable = true,
    required this.onAdd,
    required this.onDelete,
    required this.onCookidoo,
    this.onOpenRecipe,
  });

  Widget? _subtitle(MealEntry e) {
    final parts = [
      if (e.minutes != null) l10n.minutesShort(e.minutes!),
      if (e.description != null && e.description!.isNotEmpty) e.description!,
    ];
    return parts.isEmpty ? null : Text(parts.join(' · '), maxLines: 2, overflow: TextOverflow.ellipsis);
  }

  Widget? _trailing(MealEntry e) {
    if (!editable) {
      return e.isExternal && e.cookidooId != null && e.url != null
          ? IconButton(tooltip: l10n.openInSource(e.sourceName), onPressed: () => onCookidoo(e, 'open'), icon: const Icon(Icons.open_in_new))
          : null;
    }
    if (e.isExternal && planning && e.cookidooId != null) {
      return PopupMenuButton<String>(
        tooltip: l10n.recipeActions,
        onSelected: (action) => onCookidoo(e, action),
        itemBuilder: (_) => [
          PopupMenuItem(value: 'shopping', child: Text(l10n.ingredientsToList)),
          if (e.url != null) PopupMenuItem(value: 'open', child: Text(l10n.openInSource(e.sourceName))),
          PopupMenuItem(value: 'remove', child: Text(l10n.removeFromPlan)),
        ],
      );
    }
    if (e.isExternal) {
      return Chip(
        label: Text(e.sourceName),
        avatar: Icon(Icons.lock_outline, size: 16),
        side: BorderSide(color: AppColors.cookidoo),
        visualDensity: VisualDensity.compact,
      );
    }
    return IconButton(tooltip: l10n.delete, onPressed: () => onDelete(e), icon: const Icon(Icons.delete_outline));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final now = DateTime.now();
    final isToday = day.date.year == now.year && day.date.month == now.month && day.date.day == now.day;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Card(
        shape: isToday
            ? RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
                side: BorderSide(color: theme.colorScheme.primary),
              )
            : null,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      localDate('EEEE, d. MMMM').format(day.date),
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: isToday ? theme.colorScheme.primary : null,
                      ),
                    ),
                  ),
                  if (editable) IconButton(tooltip: l10n.addMeal, onPressed: onAdd, icon: const Icon(Icons.add)),
                ],
              ),
              if (day.entries.isEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text('–', style: TextStyle(color: theme.colorScheme.onSurfaceVariant)),
                ),
              for (final e in day.entries)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  leading: e.cookidooId != null ? RecipeThumb(url: e.image, size: 40) : null,
                  title: Text(e.title),
                  subtitle: _subtitle(e),
                  trailing: _trailing(e),
                  onTap: (e.hubRecipeId != null || e.cookidooId != null) && onOpenRecipe != null ? () => onOpenRecipe!(e) : null,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
