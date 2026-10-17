import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/colors.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'cookidoo_search_screen.dart';

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
                title: const Text('Eigenes Gericht'),
                onTap: () => Navigator.pop(ctx, 'own'),
              ),
              ListTile(
                leading: const Icon(Icons.menu_book_outlined),
                title: const Text('Rezept aus Cookidoo'),
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
          title: Text('Essen am ${DateFormat('EEEE', 'de_DE').format(day)}'),
          content: TextField(
            controller: c,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(labelText: 'Gericht'),
            onSubmitted: (v) => Navigator.pop(ctx, v),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
            FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('Speichern')),
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
        title: const Text('Eintrag löschen?'),
        content: Text('„${entry.title}“ aus dem Plan entfernen.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Löschen')),
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
          if (mounted) showInfo(context, '$n Zutaten auf der Cookidoo-Einkaufsliste');
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
    final range = '${DateFormat('d.M.', 'de_DE').format(_monday)} – ${DateFormat('d.M.', 'de_DE').format(sunday)}';
    final isCurrent = _monday == mondayOf(DateTime.now());

    return Scaffold(
      appBar: AppBar(
        title: const Text('Essen'),
        actions: [
          ReadStatusIcon(result: async.valueOrNull),
          IconButton(
            tooltip: 'Zutaten der nächsten 7 Tage auf die Einkaufsliste',
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
                IconButton(tooltip: 'Vorige Woche', onPressed: () => _shiftWeek(-1), icon: const Icon(Icons.chevron_left)),
                Expanded(
                  child: TextButton(
                    onPressed: isCurrent ? null : () => setState(() => _monday = mondayOf(DateTime.now())),
                    child: Text(isCurrent ? 'Diese Woche · $range' : 'KW ${_week.split('W').last} · $range'),
                  ),
                ),
                IconButton(tooltip: 'Nächste Woche', onPressed: () => _shiftWeek(1), icon: const Icon(Icons.chevron_right)),
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
  final VoidCallback onAdd;
  final ValueChanged<MealEntry> onDelete;
  final void Function(MealEntry entry, String action) onCookidoo;
  const _DayTile({
    required this.day,
    required this.planning,
    required this.onAdd,
    required this.onDelete,
    required this.onCookidoo,
  });

  Widget? _subtitle(MealEntry e) {
    final parts = [
      if (e.minutes != null) '${e.minutes} Min.',
      if (e.description != null && e.description!.isNotEmpty) e.description!,
    ];
    return parts.isEmpty ? null : Text(parts.join(' · '), maxLines: 2, overflow: TextOverflow.ellipsis);
  }

  Widget _trailing(MealEntry e) {
    if (e.isCookidoo && planning && e.cookidooId != null) {
      return PopupMenuButton<String>(
        tooltip: 'Rezept-Aktionen',
        onSelected: (action) => onCookidoo(e, action),
        itemBuilder: (_) => [
          const PopupMenuItem(value: 'shopping', child: Text('Zutaten auf die Einkaufsliste')),
          if (e.url != null) const PopupMenuItem(value: 'open', child: Text('In Cookidoo öffnen')),
          const PopupMenuItem(value: 'remove', child: Text('Aus dem Plan nehmen')),
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
    return IconButton(tooltip: 'Löschen', onPressed: () => onDelete(e), icon: const Icon(Icons.delete_outline));
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
                      DateFormat('EEEE, d. MMMM', 'de_DE').format(day.date),
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: isToday ? theme.colorScheme.primary : null,
                      ),
                    ),
                  ),
                  IconButton(tooltip: 'Essen eintragen', onPressed: onAdd, icon: const Icon(Icons.add)),
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
