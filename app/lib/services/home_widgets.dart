import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';
import 'package:intl/intl.dart';

import '../core/constants/colors.dart';
import '../core/theme/hub_style.dart';
import '../models/shopping.dart';
import '../models/today.dart';

/// Android-Startbildschirm-Widgets „Heute“ und „Einkauf“.
///
/// Die App schreibt fertige Texte in den Widget-Speicher; die Kotlin-Provider
/// (TodayWidgetProvider, ShoppingWidgetProvider) zeigen sie nur an.
class HomeWidgets {
  static const todayProvider = 'de.familienhub.app.TodayWidgetProvider';
  static const shoppingProvider = 'de.familienhub.app.ShoppingWidgetProvider';
  static const sessionKey = 'widget_session';
  static const _all = [todayProvider, shoppingProvider];
  static const contentKeys = [
    'today_title', 'today_events', 'today_tasks', 'today_meal', 'today_shopping', 'today_updated',
    'shopping_count', 'shopping_items', 'shopping_updated',
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
  static Future<void> updateToday(TodayData d, {DateTime? now}) => _write(todayTexts(d, now: now), [todayProvider]);

  static Future<void> updateShopping(ShoppingData d, {DateTime? now}) =>
      _write(shoppingTexts(d, now: now), [shoppingProvider]);

  static Future<void> _write(Map<String, String> texts, List<String> providers) async {
    if (!supported) return;
    try {
      for (final e in texts.entries) {
        await HomeWidget.saveWidgetData<String>(e.key, e.value);
      }
      for (final p in providers) {
        await HomeWidget.updateWidget(qualifiedAndroidName: p);
      }
    } catch (e) {
      debugPrint('[widgets] nicht aktualisiert: $e');
    }
  }
}

String _time(DateTime t) => DateFormat('HH:mm', 'de_DE').format(t.toLocal());

/// Texte für das Widget „Heute“ (rein, testbar).
Map<String, String> todayTexts(TodayData d, {DateTime? now}) {
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final events = d.events.take(3).map((e) {
    if (e.start == null || e.allDay) return '• ${e.title}';
    final s = e.start!.toLocal();
    final tomorrow = DateTime(s.year, s.month, s.day).isAfter(today);
    return '• ${tomorrow ? 'morgen ' : ''}${_time(s)} ${e.title}';
  }).toList();
  final tasks = d.tasks.items.where((t) => !t.done).take(3).map((t) => '☐ ${t.title}').toList();
  final meal = d.meals.isEmpty ? '' : '🍽 ${d.meals.map((m) => m.title).join(', ')}';
  return {
    'today_title': DateFormat('EEEE, d. MMMM', 'de_DE').format(n),
    'today_events': events.isEmpty ? 'Keine Termine' : events.join('\n'),
    'today_tasks': tasks.isEmpty ? 'Nichts fällig' : tasks.join('\n'),
    'today_meal': meal,
    'today_shopping': d.shoppingOpen == 0 ? '🛒 Liste leer' : '🛒 ${d.shoppingOpen} offen',
    'today_updated': 'Stand ${_time(n)}',
  };
}

/// Texte für das Widget „Einkauf“ (rein, testbar).
Map<String, String> shoppingTexts(ShoppingData d, {DateTime? now}) {
  final open = [
    for (final g in d.groups)
      for (final i in g.items.where((i) => !i.done)) i.summary,
  ];
  return {
    'shopping_count': open.isEmpty ? 'Einkauf' : 'Einkauf · ${open.length}',
    'shopping_items': open.isEmpty ? 'Nichts auf der Liste' : open.take(8).map((s) => '• $s').join('\n') +
        (open.length > 8 ? '\n… und ${open.length - 8} weitere' : ''),
    'shopping_updated': 'Stand ${_time(now ?? DateTime.now())}',
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
