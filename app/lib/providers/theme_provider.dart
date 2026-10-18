import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart' show Brightness, ThemeMode;
import 'package:flutter/scheduler.dart' show SchedulerBinding;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/theme/app_theme.dart';
import '../models/themes.dart';
import '../services/home_widgets.dart';
import '../l10n/l10n.dart';
import 'providers.dart';

const _key = 'theme_spec';

/// Gewähltes Farbschema dieses Geräts; null = Standard. Gespeichert wird das ganze Schema,
/// damit die App auch ohne Netz sofort in der gewählten Darstellung startet.
class ThemeChoice extends StateNotifier<ThemeSpec?> {
  ThemeChoice() : super(null) {
    _load();
  }

  Future<void> _load() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_key);
      if (raw == null) return;
      final spec = ThemeSpec.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      if (spec.usable && mounted) state = spec;
    } catch (_) {
      // kaputter Eintrag → Standard
    } finally {
      unawaited(_publishStyle());
    }
  }

  /// Hell/Dunkel für die Widgets: gewählter Modus, bei „Automatisch“ der des Systems.
  ThemeMode mode = ThemeMode.system;

  /// Widgets auf dem Startbildschirm im gleichen Stil wie die App (passende Fassung hell/dunkel).
  Future<void> _publishStyle() {
    final system = SchedulerBinding.instance.platformDispatcher.platformBrightness;
    final wanted = switch (mode) { ThemeMode.light => Brightness.light, ThemeMode.dark => Brightness.dark, _ => system };
    return HomeWidgets.updateStyle(state == null ? AppTheme.dark : AppTheme.fromSpec(state!.forBrightness(wanted)));
  }

  /// Nach einem Moduswechsel die Widgets nachziehen.
  void modeChanged(ThemeMode m) {
    mode = m;
    unawaited(_publishStyle());
  }

  Future<void> select(ThemeSpec? spec) async {
    state = spec;
    unawaited(_publishStyle());
    final prefs = await SharedPreferences.getInstance();
    if (spec == null) {
      await prefs.remove(_key);
    } else {
      await prefs.setString(_key, jsonEncode(spec.toJson()));
    }
  }
}

final themeChoiceProvider = StateNotifierProvider<ThemeChoice, ThemeSpec?>((ref) => ThemeChoice());

const _modeKey = 'theme_mode';

/// Hell, Dunkel oder Automatisch (folgt dem System). Pro Gerät gespeichert.
class ThemeModeChoice extends StateNotifier<ThemeMode> {
  final void Function(ThemeMode) onChange;
  ThemeModeChoice(this.onChange) : super(ThemeMode.system) {
    _load();
  }

  Future<void> _load() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_modeKey);
      final m = ThemeMode.values.where((m) => m.name == raw).firstOrNull;
      if (m != null && mounted) {
        state = m;
        onChange(m);
      }
    } catch (_) {
      // Standard: Automatisch
    }
  }

  Future<void> select(ThemeMode m) async {
    state = m;
    onChange(m);
    try {
      await (await SharedPreferences.getInstance()).setString(_modeKey, m.name);
    } catch (_) {}
  }
}

final themeModeProvider = StateNotifierProvider<ThemeModeChoice, ThemeMode>(
    (ref) => ThemeModeChoice((m) => ref.read(themeChoiceProvider.notifier).modeChanged(m)));

final themesProvider = FutureProvider.autoDispose<List<ThemeSpec>>(
    (ref) => ref.watch(apiClientProvider).themes());

final adminPluginsProvider = FutureProvider.autoDispose(
    (ref) => ref.watch(apiClientProvider).adminPlugins());

/// Sprache der App: `system` (Gerät), `de` oder `en`. Pro Gerät gespeichert.
class LanguageChoice extends StateNotifier<String> {
  LanguageChoice() : super('system') {
    _load();
  }

  Future<void> _load() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(languagePrefKey);
      if (raw != null && mounted) state = raw;
    } catch (_) {
      // Standard: wie das Gerät
    }
  }

  Future<void> select(String choice) async {
    state = choice;
    try {
      await (await SharedPreferences.getInstance()).setString(languagePrefKey, choice);
    } catch (_) {}
  }
}

final languageChoiceProvider = StateNotifierProvider<LanguageChoice, String>((ref) => LanguageChoice());
