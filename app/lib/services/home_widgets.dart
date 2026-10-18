import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';

import '../core/constants/colors.dart';
import '../core/theme/hub_style.dart';
import '../models/shopping.dart';
import '../models/today.dart';
import '../l10n/l10n.dart';

/// Android home-screen widgets "Today" (configurable), "Events", "Tasks" and "Shopping".
///
/// The app writes ready-made texts into the widget storage; the Kotlin providers only render them.
/// List sections are stored as newline separated rows (events: `when<TAB>title`), see [todayTexts] and
/// [shoppingTexts]. All providers share the same keys, so every update refreshes all of them.
class HomeWidgets {
  static const todayProvider = 'de.familienhub.app.TodayWidgetProvider';
  static const shoppingProvider = 'de.familienhub.app.ShoppingWidgetProvider';
  static const sessionKey = 'widget_session';
  static const eventsProvider = 'de.familienhub.app.EventsWidgetProvider';
  static const tasksProvider = 'de.familienhub.app.TasksWidgetProvider';
  static const _all = [todayProvider, eventsProvider, tasksProvider, shoppingProvider];
  static const contentKeys = [
    'today_title', 'today_meal', 'today_updated',
    'events_items', 'events_empty', 'events_label',
    'tasks_items', 'tasks_empty', 'tasks_label',
    'shopping_items', 'shopping_empty', 'shopping_label', 'shopping_updated',
  ];

  static bool get supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  /// Beim Anmelden: zufällige Sitzungs-Kennung im Widget-Speicher. Ohne Kennung zeigen die Widgets
  /// nur einen Platzhalter, und Hintergrund-Aktualisierungen schreiben nichts.
  static Future<void> startSession() async {
    if (!supported) return;
    try {
      final current = await HomeWidget.getWidgetData<String>(sessionKey);
      if (current == null || current.isEmpty) {
        final r = Random.secure();
        await HomeWidget.saveWidgetData<String>(sessionKey, List.generate(16, (_) => r.nextInt(16).toRadixString(16)).join());
      }
    } catch (e) {
      debugPrint('[widgets] Sitzung nicht gesetzt: $e');
    }
  }

  /// Beim Abmelden: Kennung und alle Inhalte löschen, Widgets zeigen den Platzhalter.
  static Future<void> endSession() async {
    if (!supported) return;
    try {
      await HomeWidget.saveWidgetData<String>(sessionKey, '');
      for (final k in contentKeys) {
        await HomeWidget.saveWidgetData<String>(k, null);
      }
      for (final p in _all) {
        await HomeWidget.updateWidget(qualifiedAndroidName: p);
      }
    } catch (e) {
      debugPrint('[widgets] nicht geleert: $e');
    }
  }

  static Future<String?> session() async {
    if (!supported) return null;
    try {
      final s = await HomeWidget.getWidgetData<String>(sessionKey);
      return s == null || s.isEmpty ? null : s;
    } catch (_) {
      return null;
    }
  }

  /// Hintergrund: nur schreiben, wenn dieselbe Sitzung vor dem Abruf ([expected]), vor dem Schreiben
  /// und nach dem Schreiben gilt. Hat sie gewechselt (Abmelden dazwischen), Widgets sofort leeren.
  static Future<bool> publishFor(String expected, {TodayData? today, ShoppingData? shopping}) async {
    if (await session() != expected) return false;
    if (today != null) await updateToday(today);
    if (shopping != null) await updateShopping(shopping);
    if (await session() != expected) {
      await endSession();
      return false;
    }
    return true;
  }

  /// Aussehen des gewählten Themes für die Widgets (Farben als ARGB-Zahl, Maße in dp).
  static Future<void> updateStyle(ThemeData theme) async {
    if (!supported) return;
    final values = widgetStyle(theme);
    try {
      for (final e in values.entries) {
        await HomeWidget.saveWidgetData<String>(e.key, e.value);
      }
      for (final p in _all) {
        await HomeWidget.updateWidget(qualifiedAndroidName: p);
      }
    } catch (e) {
      debugPrint('[widgets] Stil nicht gesetzt: $e');
    }
  }

  /// Fehler (z. B. kein Widget-Plugin in Tests) brechen nie das Laden der Daten ab.
  static Future<void> updateToday(TodayData d, {DateTime? now}) => _write(todayTexts(d, now: now));

  static Future<void> updateShopping(ShoppingData d, {DateTime? now}) =>
      _write(shoppingTexts(d, now: now));

  static Future<void> _write(Map<String, String> texts) async {
    if (!supported) return;
    try {
      for (final e in texts.entries) {
        await HomeWidget.saveWidgetData<String>(e.key, e.value);
      }
      for (final p in _all) {
        await HomeWidget.updateWidget(qualifiedAndroidName: p);
      }
    } catch (e) {
      debugPrint('[widgets] nicht aktualisiert: $e');
    }
  }
}

String _time(DateTime t) => localDate('HH:mm').format(t.toLocal());

/// Maximum rows stored per list section (the widgets show as many as fit and add "+N more").
const widgetMaxRows = 20;

String _oneLine(String s) => s.replaceAll(RegExp(r'\s+'), ' ').trim();

/// Texts for the "Today" and "Events"/"Tasks" widgets (pure, testable).
Map<String, String> todayTexts(TodayData d, {DateTime? now}) {
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final events = d.events.take(widgetMaxRows).map((e) {
    final title = _oneLine(e.title);
    if (e.start == null || e.allDay) return '\t$title';
    final s = e.start!.toLocal();
    final tomorrow = DateTime(s.year, s.month, s.day).isAfter(today);
    return '${tomorrow ? '${l10n.widgetTomorrow} ' : ''}${_time(s)}\t$title';
  }).toList();
  final tasks = d.tasks.items.where((t) => !t.done).take(widgetMaxRows).map((t) => _oneLine(t.title)).toList();
  final meal = d.meals.isEmpty ? '' : '🍽 ${d.meals.map((m) => m.title).join(', ')}';
  return {
    'today_title': localDate('EEEE, d. MMMM').format(n),
    'today_meal': meal,
    'today_updated': l10n.asOfTime(_time(n)),
    'events_items': events.join('\n'),
    'events_empty': l10n.noEvents,
    'events_label': l10n.tabCalendar,
    'tasks_items': tasks.join('\n'),
    'tasks_empty': l10n.nothingDueShort,
    'tasks_label': l10n.tabTasks,
  };
}

/// Texts for the shopping section (pure, testable).
Map<String, String> shoppingTexts(ShoppingData d, {DateTime? now}) {
  final open = [
    for (final g in d.groups)
      for (final i in g.items.where((i) => !i.done)) _oneLine(i.summary),
  ];
  return {
    'shopping_items': open.take(widgetMaxRows).join('\n'),
    'shopping_empty': l10n.nothingOnList,
    'shopping_label': open.isEmpty ? l10n.tabShopping : l10n.shoppingCount(open.length),
    'shopping_updated': l10n.asOfTime(_time(now ?? DateTime.now())),
  };
}


String _argb(Color c) => c.toARGB32().toString();

/// Stilwerte für die Kotlin-Widgets (rein, testbar). Glas gibt es auf dem Startbildschirm nicht
/// (keine Unschärfe), dort deckt die Kartenfarbe zu 90 %.
Map<String, String> widgetStyle(ThemeData theme) {
  final style = theme.extension<HubStyle>() ?? HubStyle.standard;
  final scheme = theme.colorScheme;
  final card = style.glass
      ? Color.alphaBlend(style.surface.withValues(alpha: 0.9), style.base)
      : identical(style, HubStyle.standard)
          ? style.surface.withValues(alpha: 0.95)
          : style.surface;
  final band = style.bandHeader && style.accents.isNotEmpty ? style.accents.first : null;
  final onBand = band == null
      ? scheme.onSurface
      : (ThemeData.estimateBrightnessForColor(band) == Brightness.dark ? Colors.white : Colors.black);
  return {
    'w_card': _argb(card),
    'w_text': _argb(scheme.onSurface),
    'w_muted': _argb(scheme.onSurfaceVariant),
    'w_accent': _argb(band ?? scheme.primary),
    'w_green': _argb(AppColors.cookidoo),
    'w_border': _argb(style.glass ? Colors.white.withValues(alpha: 0.16) : style.border),
    'w_border_w': style.borderWidth.toStringAsFixed(0),
    'w_radius': style.radius.toStringAsFixed(0),
    'w_shadow': style.shadow.name, // none | soft | hard
    'w_band': band == null ? '' : _argb(band),
    'w_on_band': _argb(onBand),
  };
}
