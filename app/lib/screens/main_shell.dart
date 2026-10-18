import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quick_actions/quick_actions.dart';

import '../core/theme/hub_style.dart';
import '../providers/providers.dart';
import '../services/background.dart';
import '../services/home_widgets.dart';
import '../services/widget_access.dart';
import '../widgets/hub_background.dart';
import 'calendar/calendar_screen.dart';
import 'meals/meals_screen.dart';
import 'more/more_screen.dart';
import 'shopping/shopping_screen.dart';
import 'tasks/tasks_screen.dart';
import 'today/today_screen.dart';
import '../l10n/l10n.dart';

/// Breite, ab der die Seitenleiste statt der unteren Leiste erscheint (Fold aufgeklappt, Tablet).
const wideLayoutBreakpoint = 600.0;

bool isWide(BuildContext context) =>
    MediaQuery.sizeOf(context).width >= wideLayoutBreakpoint;

class MainShell extends ConsumerStatefulWidget {
  /// In Tests aus, damit kein Firebase angefasst wird.
  final bool startPush;
  const MainShell({super.key, this.startPush = true});

  @override
  ConsumerState<MainShell> createState() => _MainShellState();
}

class _MainShellState extends ConsumerState<MainShell> {
  StreamSubscription<String>? _routes;
  StreamSubscription<void>? _refreshes;

  static List<(AppTab, IconData, IconData, String)> get _allDestinations => [
    (AppTab.today, Icons.wb_sunny_outlined, Icons.wb_sunny, l10n.tabToday),
    (AppTab.calendar, Icons.event_outlined, Icons.event, l10n.tabCalendar),
    (AppTab.tasks, Icons.check_circle_outline, Icons.check_circle, l10n.tabTasks),
    (AppTab.shopping, Icons.shopping_cart_outlined, Icons.shopping_cart, l10n.tabShopping),
    (AppTab.meals, Icons.restaurant_outlined, Icons.restaurant, l10n.tabMeals),
    (AppTab.more, Icons.more_horiz, Icons.more_horiz, l10n.tabMore),
  ];

  /// Bereich → Modul aus /api/modules (Heute, Essen, Mehr gibt es immer).
  static const _moduleFor = {AppTab.calendar: 'calendar', AppTab.tasks: 'tasks', AppTab.shopping: 'shopping'};

  @override
  void initState() {
    super.initState();
    if (widget.startPush) {
      final push = ref.read(pushServiceProvider);
      _routes = push.routes.listen((route) => openRoute(ref, route));
      _refreshes = push.refreshes.listen((_) {
        // stiller Push: geänderte Daten sofort zeigen; die Provider aktualisieren auch die Widgets
        unawaited(ref.read(todayProvider.notifier).refresh());
        unawaited(ref.read(shoppingProvider.notifier).refresh());
      });
      push.start();
      if (HomeWidgets.supported) {
        unawaited(WidgetAccess.ensure(ref.read(apiClientProvider)));
        startWidgetRefresh();
        // App-Symbol lange drücken → direkt in den Bereich
        const actions = QuickActions();
        actions.initialize((route) => openRoute(ref, route));
        actions.setShortcutItems([
          ShortcutItem(type: '/shopping', localizedTitle: l10n.tabShopping),
          ShortcutItem(type: '/tasks', localizedTitle: l10n.shortcutNewTask),
          ShortcutItem(type: '/today', localizedTitle: l10n.tabToday),
        ]);
      }
    }
  }

  @override
  void dispose() {
    _routes?.cancel();
    _refreshes?.cancel();
    super.dispose();
  }

  Widget _screen(AppTab tab) => switch (tab) {
        AppTab.today => const TodayScreen(),
        AppTab.calendar => const CalendarScreen(),
        AppTab.tasks => const TasksScreen(),
        AppTab.shopping => const ShoppingScreen(),
        AppTab.meals => const MealsScreen(),
        AppTab.more => const MoreScreen(),
      };

  @override
  Widget build(BuildContext context) {
    final modules = ref.watch(appModulesProvider);
    final destinations = [
      for (final d in _allDestinations)
        if (_moduleFor[d.$1] == null || modules.has(_moduleFor[d.$1]!)) d,
    ];
    var tab = ref.watch(tabProvider);
    if (!destinations.any((d) => d.$1 == tab)) tab = AppTab.today; // Bereich abgeschaltet
    final index = destinations.indexWhere((d) => d.$1 == tab);
    void select(int i) => ref.read(tabProvider.notifier).state = destinations[i].$1;

    if (isWide(context)) {
      return Scaffold(
        body: SafeArea(
          child: Row(
            children: [
              NavigationRail(
                selectedIndex: index,
                onDestinationSelected: select,
                destinations: [
                  for (final d in destinations)
                    NavigationRailDestination(
                      icon: Icon(d.$2),
                      selectedIcon: Icon(d.$3),
                      label: Text(d.$4),
                    ),
                ],
              ),
              const VerticalDivider(width: 1),
              Expanded(child: _screen(tab)),
            ],
          ),
        ),
      );
    }
    final bar = NavigationBar(
      selectedIndex: index,
      onDestinationSelected: select,
      destinations: [
        for (final d in destinations)
          NavigationDestination(icon: Icon(d.$2), selectedIcon: Icon(d.$3), label: d.$4),
      ],
    );
    final style = HubStyle.of(context);
    if (!style.floatingNav) return Scaffold(body: _screen(tab), bottomNavigationBar: bar);
    // Schwebende Leiste (Liquid Glass, Clean Cards, Neo-Brutalism) mit Abstand zum Rand
    return Scaffold(
      body: _screen(tab),
      bottomNavigationBar: SafeArea(
        minimum: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        child: HubSurface(radius: style.radius >= 20 ? 32 : style.radius, child: bar),
      ),
    );
  }
}
