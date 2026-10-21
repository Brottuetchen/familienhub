import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/hub_style.dart';
import '../../l10n/l10n.dart';
import '../../models/plugin_card.dart';
import '../../models/today_layout.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Arrange "Today": drag to reorder, switch cards on or off, toggle half width.
class TodayLayoutEditor extends ConsumerStatefulWidget {
  const TodayLayoutEditor({super.key});

  @override
  ConsumerState<TodayLayoutEditor> createState() => _TodayLayoutEditorState();
}

class _TodayLayoutEditorState extends ConsumerState<TodayLayoutEditor> {
  List<TodayCard>? _edited;
  bool _busy = false;

  /// Cards that installed plugins show today: they are listed here (new ones at the end, visible) with their title.
  List<PluginCardData> get _pluginCards => ref.read(todayProvider).valueOrNull?.data.pluginCards ?? const [];

  List<TodayCard> get _cards => _edited ??= [
        ...(ref.read(todayLayoutProvider).valueOrNull?.data ?? TodayLayout.builtin)
            .forStyle(bento: HubStyle.of(context).bento)
            .withPluginCards([for (final c in _pluginCards) c.key])
            .cards,
      ];

  String _label(String id) {
    if (isPluginCardId(id)) {
      final card = _pluginCards.where((c) => c.key == id).firstOrNull;
      return card == null ? id.split(':').last : card.title;
    }
    return _builtinLabel(id);
  }

  /// Which plugin a card comes from, shown under its title.
  String? _source(String id) {
    if (!isPluginCardId(id)) return null;
    final card = _pluginCards.where((c) => c.key == id).firstOrNull;
    return card == null || card.pluginName.isEmpty ? null : l10n.pluginCardFrom(card.pluginName);
  }

  static String _builtinLabel(String id) => switch (id) {
        'tasks' => l10n.tabTasks,
        'shopping' => l10n.shoppingList,
        'events' => l10n.tabCalendar,
        'meals' => l10n.mealPlan,
        'reminders' => l10n.reminders,
        'house' => l10n.house,
        'birthdays' => l10n.birthdays,
        'timetable' => l10n.timetable,
        'stars' => l10n.starsTitle,
        _ => id,
      };

  /// Cards of switched-off modules are not offered; they keep their place at the end when saving.
  bool _available(String id) {
    if (isPluginCardId(id)) return _pluginCards.any((c) => c.key == id);
    final modules = ref.read(appModulesProvider);
    return switch (id) {
      'tasks' => modules.has('tasks'),
      'shopping' => modules.has('shopping'),
      'events' => modules.has('calendar'),
      'stars' => ref.read(starsProvider).valueOrNull?.data.enabled ?? false,
      _ => true,
    };
  }

  TodayLayout get _layout => TodayLayout([
        ..._cards.where((c) => _available(c.id)),
        ..._cards.where((c) => !_available(c.id)),
      ]);

  Future<void> _run(Future<void> Function() action, {String? done, bool close = false}) async {
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      if (done != null) showInfo(context, done);
      if (close) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.read(apiClientProvider);
    final isAdmin = ref.watch(sessionProvider.select((s) => s.user?.isAdmin ?? false));
    final shown = [for (final c in _cards) if (_available(c.id)) c];
    return Scaffold(
      appBar: AppBar(title: Text(l10n.customiseToday)),
      body: SafeArea(
        child: ReorderableListView(
          key: const Key('today-layout-list'),
          buildDefaultDragHandles: false,
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          header: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(l10n.customiseTodayHintBento,
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ),
          footer: Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              FilledButton(
                key: const Key('today-layout-save'),
                onPressed: _busy ? null : () => _run(() => api.saveTodayLayout(_layout), close: true),
                child: Text(l10n.save),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('today-layout-reset'),
                onPressed: _busy ? null : () => _run(api.resetTodayLayout, close: true),
                child: Text(l10n.resetTodayLayout),
              ),
              if (isAdmin) ...[
                const SizedBox(height: 8),
                OutlinedButton(
                  key: const Key('today-layout-family'),
                  onPressed: _busy
                      ? null
                      : () => _run(() => api.saveFamilyTodayLayout(_layout), done: l10n.familyTodayLayoutSaved),
                  child: Text(l10n.saveAsFamilyDefault),
                ),
                TextButton(
                  key: const Key('today-layout-family-reset'),
                  onPressed: _busy
                      ? null
                      : () => _run(api.resetFamilyTodayLayout, done: l10n.familyTodayLayoutRemoved),
                  child: Text(l10n.removeFamilyDefault),
                ),
              ],
            ]),
          ),
          onReorderItem: (from, to) {
            final moved = shown[from];
            final target = shown[to];
            setState(() {
              _cards.remove(moved);
              _cards.insert(_cards.indexOf(target) + (to > from ? 1 : 0), moved);
            });
          },
          children: [
            for (final (i, c) in shown.indexed)
              Padding(
                key: ValueKey('layout-${c.id}'),
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  ReorderableDragStartListener(
                    index: i,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Icon(Icons.drag_handle, semanticLabel: l10n.dragToReorder),
                    ),
                  ),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_label(c.id), style: Theme.of(context).textTheme.titleMedium),
                      if (_source(c.id) != null)
                        Text(_source(c.id)!,
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                    ]),
                  ),
                    IconButton(
                      key: Key('layout-size-${c.id}'),
                      tooltip: c.half ? l10n.sizeHalfTapForFull : l10n.sizeFullTapForHalf,
                      onPressed: () => setState(() => _replace(c, c.copyWith(half: !c.half))),
                      icon: Icon(c.half ? Icons.view_agenda_outlined : Icons.view_column_outlined),
                    ),
                  Switch(
                    key: Key('layout-visible-${c.id}'),
                    value: c.visible,
                    onChanged: (v) => setState(() => _replace(c, c.copyWith(visible: v))),
                  ),
                ]),
              ),
          ],
        ),
      ),
    );
  }

  void _replace(TodayCard old, TodayCard replacement) => _cards[_cards.indexOf(old)] = replacement;
}
