import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/colors.dart';
import '../../core/theme/hub_style.dart';
import '../../models/task.dart';
import '../../models/today.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../main_shell.dart';
import 'house_controls.dart';
import 'today_widgets.dart';
import '../../l10n/l10n.dart';

class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(todayProvider);
    final user = ref.watch(sessionProvider).user;
    final style = HubStyle.of(context);
    Future<void> refresh() => ref.read(todayProvider.notifier).refresh();

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: HubRefresh(
          onRefresh: refresh,
          child: async.when(
            loading: () => const Center(child: HubLoader()),
            error: (e, _) => ErrorView(error: e, onRetry: refresh),
            data: (result) {
              final online = !result.offline;
              final cards = _cards(context, ref, result.data, online: online, compact: style.bento);
              final house = HouseCard(
                // Nicht an „wird aktualisiert“ koppeln: sonst leert sich die Haus-Karte bei jedem Nachladen
                online: online && result.refreshError == null,
                states: result.data.house,
              );
              final ordered = [
                for (final k in ['tasks', 'meals', 'shopping', 'events', 'reminders'])
                  if (cards[k] != null) cards[k]!,
                house,
              ];
              Widget body;
              if (isWide(context)) {
                body = _TwoColumns(children: _accented(ordered));
              } else if (style.bento) {
                body = _bento(cards, house);
              } else {
                body = Column(children: [for (final c in _accented(ordered)) ...[c, const SizedBox(height: 12)]]);
              }
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.only(bottom: 24),
                children: [
                  TodayHeader(
                    greeting: _greeting(user?.displayName),
                    unread: result.data.notificationsUnread,
                    status: ReadStatusIcon(result: result),
                  ),
                  if (ref.watch(appModulesProvider).has('tasks')) const TaskFilterBar(),
                  Padding(padding: const EdgeInsets.all(16), child: body),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  static List<Widget> _accented(List<Widget> cards) =>
      [for (final (i, c) in cards.indexed) SectionAccentScope(index: i, child: c)];

  /// Kachel-Layout (Clean Cards): große Karten volle Breite, kleine paarweise nebeneinander.
  static Widget _bento(Map<String, Widget> cards, Widget house) {
    var i = 0;
    Widget accent(Widget w) => SectionAccentScope(index: i++, child: w);
    final rows = <Widget>[];
    void full(String k) {
      if (cards[k] != null) rows.add(accent(cards[k]!));
    }

    full('tasks');
    final pair = [for (final k in ['shopping', 'events']) if (cards[k] != null) cards[k]!];
    if (pair.length == 2) {
      rows.add(IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [Expanded(child: accent(pair[0])), const SizedBox(width: 12), Expanded(child: accent(pair[1]))],
        ),
      ));
    } else {
      rows.addAll(pair.map(accent));
    }
    for (final k in ['meals', 'reminders']) {
      full(k);
    }
    rows.add(accent(house));
    return Column(children: [for (final r in rows) ...[r, const SizedBox(height: 12)]]);
  }

  static String _greeting(String? name) {
    final h = DateTime.now().hour;
    final hello = h < 11 ? l10n.goodMorning : (h < 18 ? l10n.hello : l10n.goodEvening);
    return name == null ? hello : '$hello, $name';
  }

  Map<String, Widget> _cards(BuildContext context, WidgetRef ref, TodayData data,
      {required bool online, required bool compact}) {
    final modules = ref.watch(appModulesProvider);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    void go(AppTab tab) => ref.read(tabProvider.notifier).state = tab;
    final filter = ref.watch(todayTaskFilterProvider);
    final filtered = filter == null ? null : ref.watch(tasksProvider(filter)).valueOrNull?.data;
    // Erledigte Aufgaben (auch abgehakte Habitica-Dailies) gehören nicht auf „Heute“
    final tasks = (filter == null ? data.tasks.items : (filtered?.items ?? const <Task>[]))
        .where((t) => !t.done)
        .toList();
    final tasksOk = filter == null ? data.tasks.isOk : (filtered?.isOk ?? true);
    final nextEvent = data.events.isEmpty ? null : data.events.first;

    return {
      if (modules.has('calendar'))
        'events': SectionCard(
          key: const Key('today-events'),
          icon: Icons.event,
          title: compact ? l10n.today : l10n.tabCalendar,
          onTap: () => go(AppTab.calendar),
          child: compact
              ? EventsTile(
                  count: data.events.length,
                  next: nextEvent == null
                      ? null
                      : '${nextEvent.allDay || nextEvent.start == null ? '' : '${timeLabel(nextEvent.start!)} '}${nextEvent.title}',
                )
              : data.events.isEmpty
                  ? Text(l10n.nothingTodayTomorrow, style: muted)
                  : Column(
                      children: [
                        for (final e in data.events)
                          _Line(
                            leading: e.allDay || e.start == null
                                ? l10n.allDayLower
                                : '${dayLabel(e.start!) == 'Heute' ? '' : '${dayLabel(e.start!)} '}${timeLabel(e.start!)}',
                            text: e.title,
                          ),
                      ],
                    ),
        ),
      if (modules.has('tasks'))
        'tasks': SectionCard(
          key: const Key('today-tasks'),
          icon: Icons.check_circle_outline,
          title: l10n.tabTasks,
          onTap: () => go(AppTab.tasks),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!tasksOk) Text(l10n.tasksUnavailable, style: muted),
            if (filter == null && data.tasks.error != null) Text(data.tasks.error!, style: muted),
            if (tasksOk && tasks.isEmpty) Text(filter == null ? l10n.nothingDue : l10n.noOpenTasks, style: muted),
            if (tasks.isNotEmpty) TaskChecklist(tasks: tasks, online: online),
          ]),
        ),
      'meals': SectionCard(
        key: const Key('today-meals'),
        icon: Icons.restaurant,
        title: l10n.mealPlan,
        onTap: () => go(AppTab.meals),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (data.meals.isEmpty) Text(l10n.nothingPlannedToday, style: muted),
            for (final m in data.meals)
              _Line(
                leading: m.source == 'cookidoo' ? 'Cookidoo' : l10n.today,
                leadingColor: m.source == 'cookidoo' ? AppColors.cookidoo : null,
                text: m.title,
              ),
            const SizedBox(height: 8),
            MealWeekStrip(onTap: () => go(AppTab.meals)),
          ],
        ),
      ),
      if (modules.has('shopping'))
        'shopping': SectionCard(
          key: const Key('today-shopping'),
          icon: Icons.shopping_cart,
          title: compact ? l10n.tabShopping : l10n.shoppingList,
          onTap: () => go(AppTab.shopping),
          child: ShoppingQuick(openCount: data.shoppingOpen, online: online),
        ),
      if (data.reminders.isNotEmpty)
        'reminders': SectionCard(
          key: const Key('today-reminders'),
          icon: Icons.notifications_active_outlined,
          title: l10n.reminders,
          onTap: () => go(AppTab.more),
          child: Column(
            children: [
              for (final r in data.reminders) _Line(leading: r.due == null ? '' : timeLabel(r.due!), text: r.title),
            ],
          ),
        ),
    };
  }
}

class _Line extends StatelessWidget {
  final String leading;
  final Color? leadingColor;
  final String text;
  const _Line({required this.leading, required this.text, this.leadingColor});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 92,
            child: Text(
              leading,
              style: theme.textTheme.bodySmall?.copyWith(
                color: leadingColor ?? theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

/// Zwei Spalten auf breiten Bildschirmen, Karten abwechselnd verteilt.
class _TwoColumns extends StatelessWidget {
  final List<Widget> children;
  const _TwoColumns({required this.children});

  @override
  Widget build(BuildContext context) {
    Widget column(int parity) => Expanded(
          child: Column(
            children: [
              for (var i = parity; i < children.length; i += 2) ...[
                children[i],
                const SizedBox(height: 12),
              ],
            ],
          ),
        );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [column(0), const SizedBox(width: 12), column(1)],
    );
  }
}
