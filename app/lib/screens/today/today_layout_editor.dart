import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/hub_style.dart';
import '../../l10n/l10n.dart';
import '../../models/today_layout.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Arrange "Today": drag to reorder, switch cards on or off, toggle half width (bento themes).
class TodayLayoutEditor extends ConsumerStatefulWidget {
  const TodayLayoutEditor({super.key});

  @override
  ConsumerState<TodayLayoutEditor> createState() => _TodayLayoutEditorState();
}

class _TodayLayoutEditorState extends ConsumerState<TodayLayoutEditor> {
  List<TodayCard>? _edited;
  bool _busy = false;

  List<TodayCard> get _cards => _edited ??= [
        ...(ref.read(todayLayoutProvider).valueOrNull?.data ?? TodayLayout.builtin)
            .forStyle(bento: HubStyle.of(context).bento)
            .cards,
      ];

  static String _label(String id) => switch (id) {
        'tasks' => l10n.tabTasks,
        'shopping' => l10n.shoppingList,
        'events' => l10n.tabCalendar,
        'meals' => l10n.mealPlan,
        'reminders' => l10n.reminders,
        'house' => l10n.house,
        _ => id,
      };

  /// Cards of switched-off modules are not offered; they keep their place at the end when saving.
  bool _available(String id) {
    final modules = ref.read(appModulesProvider);
    return switch (id) {
      'tasks' => modules.has('tasks'),
      'shopping' => modules.has('shopping'),
      'events' => modules.has('calendar'),
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
    final bento = HubStyle.of(context).bento;
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
            child: Text(bento ? l10n.customiseTodayHintBento : l10n.customiseTodayHint,
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
                  Expanded(child: Text(_label(c.id), style: Theme.of(context).textTheme.titleMedium)),
                  if (bento)
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
