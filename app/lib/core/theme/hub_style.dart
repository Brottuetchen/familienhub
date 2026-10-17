import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

import '../../models/themes.dart';
import '../constants/colors.dart';

enum HubBackgroundType { solid, gradient, glow }

enum HubShadow { none, soft, hard }

/// Designsprache eines Themes: Hintergrund, Karten, Navigation, Überschriften.
/// Farben allein reichen nicht – Liquid Glass, Neo-Brutalism usw. unterscheiden sich vor allem hier.
@immutable
class HubStyle extends ThemeExtension<HubStyle> {
  final HubBackgroundType background;
  final List<Color> backgroundColors;
  final Color base; // Grundfarbe hinter allem
  final Color surface; // Kartenfarbe (bei Glas: Tönung)
  final Color border;
  final double radius;
  final double borderWidth;
  final HubShadow shadow;
  final bool glass;
  final bool bandHeader; // farbiger Kartenkopf (Neo-Brutalism)
  final List<Color> accents;
  final bool floatingNav;
  final bool bento; // Kacheln nebeneinander (Clean Cards)
  final FontWeight titleWeight;
  final bool uppercaseTitles;
  /// Schriften aus dem Theme (Flutter-Familie oder null = Systemschrift): große Überschriften,
  /// Fließtext und kleine Versal-Titel/Labels.
  final String? titleFont;
  final String? bodyFont;
  final String? labelFont;

  const HubStyle({
    this.background = HubBackgroundType.solid,
    this.backgroundColors = const [],
    required this.base,
    required this.surface,
    required this.border,
    this.radius = 20,
    this.borderWidth = 1,
    this.shadow = HubShadow.none,
    this.glass = false,
    this.bandHeader = false,
    this.accents = const [],
    this.floatingNav = false,
    this.bento = false,
    this.titleWeight = FontWeight.w500,
    this.uppercaseTitles = false,
    this.titleFont,
    this.bodyFont,
    this.labelFont,
  });

  /// Erlaubte Schriften (mitgeliefert, SIL OFL). Gleiche Kennungen wie im Theme-Format des Servers.
  static const fonts = {'pixel': 'PixelifySans', 'mono': 'JetBrainsMono', 'grotesk': 'SpaceGrotesk'};

  /// Bisherige Darstellung (dunkel, violett).
  static const standard = HubStyle(base: AppColors.bg, surface: AppColors.surface, border: AppColors.border);

  factory HubStyle.fromSpec(ThemeSpec spec) {
    final s = spec.style;
    final bg = (s['background'] as Map?) ?? const {};
    final card = (s['card'] as Map?) ?? const {};
    List<Color> colors(Object? raw) =>
        raw is List ? raw.map(hexColor).whereType<Color>().toList() : const [];
    num n(Object? v, num d) => v is num ? v : d;
    final weight = n(s['titleWeight'], 500).toInt().clamp(400, 900);
    final font = (s['font'] as Map?) ?? const {};
    return HubStyle(
      titleFont: fonts[font['title']],
      bodyFont: fonts[font['body']],
      labelFont: fonts[font['label']],
      background: HubBackgroundType.values.firstWhere((t) => t.name == bg['type'], orElse: () => HubBackgroundType.solid),
      backgroundColors: colors(bg['colors']),
      base: spec.color('background') ?? AppColors.bg,
      surface: spec.color('surface') ?? AppColors.surface,
      border: spec.color('border') ?? AppColors.border,
      radius: n(card['radius'], 20).toDouble().clamp(0, 40),
      borderWidth: n(card['border'], 1).toDouble().clamp(0, 4),
      shadow: HubShadow.values.firstWhere((t) => t.name == card['shadow'], orElse: () => HubShadow.none),
      glass: card['glass'] == true,
      bandHeader: card['header'] == 'band',
      accents: colors(s['accents']),
      floatingNav: s['nav'] == 'floating',
      bento: s['layout'] == 'bento',
      titleWeight: FontWeight.values[(weight ~/ 100) - 1],
      uppercaseTitles: s['uppercaseTitles'] == true,
    );
  }

  static HubStyle of(BuildContext context) => Theme.of(context).extension<HubStyle>() ?? standard;

  bool get transparentPages => background != HubBackgroundType.solid;

  /// Stabile Akzentfarbe pro Bereich (gleicher Titel → gleiche Farbe).
  Color accentFor(String key, Color fallback) {
    if (accents.isEmpty) return fallback;
    final sum = key.codeUnits.fold<int>(0, (a, b) => a + b);
    return accents[sum % accents.length];
  }

  /// Kartenfläche bei Glas: durchscheinend, sonst deckend.
  Color get cardFill => glass ? surface.withValues(alpha: 0.42) : surface;

  BorderSide get borderSide => borderWidth == 0
      ? BorderSide.none
      : BorderSide(color: glass ? Colors.white.withValues(alpha: 0.16) : border, width: borderWidth);

  List<BoxShadow> get shadows => switch (shadow) {
        HubShadow.none => const [],
        HubShadow.soft => [
            BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 24, offset: const Offset(0, 8)),
          ],
        HubShadow.hard => [BoxShadow(color: border, offset: const Offset(4, 4))],
      };

  BoxDecoration decoration({double? radius}) => BoxDecoration(
        color: cardFill,
        borderRadius: BorderRadius.circular(radius ?? this.radius),
        border: borderWidth == 0 ? null : Border.fromBorderSide(borderSide),
        boxShadow: shadows,
      );

  @override
  HubStyle copyWith() => this;

  @override
  HubStyle lerp(HubStyle? other, double t) {
    if (other == null) return this;
    final base = t < 0.5 ? this : other;
    return HubStyle(
      background: base.background,
      backgroundColors: base.backgroundColors,
      base: Color.lerp(this.base, other.base, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      border: Color.lerp(border, other.border, t)!,
      radius: lerpDouble(radius, other.radius, t)!,
      borderWidth: lerpDouble(borderWidth, other.borderWidth, t)!,
      shadow: base.shadow,
      glass: base.glass,
      bandHeader: base.bandHeader,
      accents: base.accents,
      floatingNav: base.floatingNav,
      bento: base.bento,
      titleWeight: base.titleWeight,
      uppercaseTitles: base.uppercaseTitles,
      titleFont: base.titleFont,
      bodyFont: base.bodyFont,
      labelFont: base.labelFont,
    );
  }
}
