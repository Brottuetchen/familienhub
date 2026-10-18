import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/colors.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'cookidoo_search_screen.dart';
import '../../l10n/l10n.dart';

class MealsScreen extends ConsumerStatefulWidget {
  const MealsScreen({super.key});

  @override
  ConsumerState<MealsScreen> createState() => _MealsScreenState();
}

class _MealsScreenState extends ConsumerState<MealsScreen> {
  DateTime _monday = mondayOf(DateTime.now());

  String get _week => isoWeekOf(_monday);

  void _shiftWeek(int weeks) => setState(() => _monday = _monday.add(Duration(days: 7 * weeks)));

  Future<void> _reload() async {
    await ref.read(mealsProvider(_week).notifier).refresh();
  }

  bool get _planning => ref.read(appModulesProvider).has('meal_planning');

  Future<void> _addMeal(DateTime day) async {
    if (_planning) {
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
                leading: const Icon(Icons.menu_book_outlined),
                title: Text(l10n.recipeFromCookidoo),
                onTap: () => Navigator.pop(ctx, 'cookidoo'),
              ),
            ],
          ),
        ),
      );
      if (choice == null || !mounted) return;
      if (choice == 'cookidoo') {
        final planned = await Navigator.push<bool>(
            context, MaterialPageRoute(builder: (_) => CookidooSearchScreen(day: day)));
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
    switch (action) {
      case 'shopping':
        try {
          final n = await api.cookidooToShopping([id]);
          if (mounted) showInfo(context, l10n.ingredientsOnCookidooList(n));
        } catch (e) {
          if (mounted) showError(context, e);
        }
      case 'open':
        if (entry.url != null) await launchUrl(Uri.parse(entry.url!), mode: LaunchMode.externalApplication);
      case 'remove':
        if (await runAction(context, () => api.unplanCookidoo(day, id))) await _reload();
    }
  }

  Future<void> _toShoppingList() async {
    try {
      final message = await ref.read(apiClientProvider).mealsToShoppingList();
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
  const _DayTile({
    required this.day,
    required this.planning,
    this.editable = true,
    required this.onAdd,
    required this.onDelete,
    required this.onCookidoo,
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
      return e.isCookidoo && e.cookidooId != null && e.url != null
          ? IconButton(tooltip: l10n.openInCookidoo, onPressed: () => onCookidoo(e, 'open'), icon: const Icon(Icons.open_in_new))
          : null;
    }
    if (e.isCookidoo && planning && e.cookidooId != null) {
      return PopupMenuButton<String>(
        tooltip: l10n.recipeActions,
        onSelected: (action) => onCookidoo(e, action),
        itemBuilder: (_) => [
          PopupMenuItem(value: 'shopping', child: Text(l10n.ingredientsToList)),
          if (e.url != null) PopupMenuItem(value: 'open', child: Text(l10n.openInCookidoo)),
          PopupMenuItem(value: 'remove', child: Text(l10n.removeFromPlan)),
        ],
      );
    }
    if (e.isCookidoo) {
      return const Chip(
        label: Text('Cookidoo'),
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
                ),
            ],
          ),
        ),
      ),
    );
  }
}
