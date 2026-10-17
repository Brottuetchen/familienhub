import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/theme/app_theme.dart';
import '../models/themes.dart';
import '../services/home_widgets.dart';
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

  /// Widgets auf dem Startbildschirm im gleichen Stil wie die App.
  Future<void> _publishStyle() =>
      HomeWidgets.updateStyle(state == null ? AppTheme.dark : AppTheme.fromSpec(state!));

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

final themesProvider = FutureProvider.autoDispose<List<ThemeSpec>>(
    (ref) => ref.watch(apiClientProvider).themes());

final adminPluginsProvider = FutureProvider.autoDispose(
    (ref) => ref.watch(apiClientProvider).adminPlugins());
