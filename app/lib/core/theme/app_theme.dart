import 'package:flutter/material.dart';

import '../../models/themes.dart';
import '../constants/colors.dart';
import 'hub_style.dart';

class AppTheme {
  AppTheme._();

  /// Standard-Darstellung (dunkel, violett).
  static ThemeData get dark => _build(
        seed: AppColors.violet,
        primary: const Color(0xFFA78BFA),
        secondary: AppColors.cyan,
        background: AppColors.bg,
        surface: AppColors.surface,
        surfaceHigh: AppColors.surfaceHigh,
        border: AppColors.border,
        style: HubStyle.standard,
      );

  /// Darstellung aus einem Farbschema vom Server. Hell oder dunkel ergibt sich aus dem Hintergrund.
  static ThemeData fromSpec(ThemeSpec spec) {
    if (!spec.usable) return dark;
    return _build(
      primary: spec.color('primary')!,
      secondary: spec.color('secondary')!,
      background: spec.color('background')!,
      surface: spec.color('surface')!,
      surfaceHigh: spec.color('surfaceHigh')!,
      border: spec.color('border')!,
      onPrimary: spec.color('onPrimary'),
      onSurface: spec.color('onSurface') ?? spec.color('onBackground'),
      outline: true,
      style: HubStyle.fromSpec(spec),
    );
  }

  static ThemeData _build({
    Color? seed,
    bool outline = false,
    required Color primary,
    required Color secondary,
    required Color background,
    required Color surface,
    required Color surfaceHigh,
    required Color border,
    Color? onPrimary,
    Color? onSurface,
    required HubStyle style,
  }) {
    final brightness = ThemeData.estimateBrightnessForColor(background);
    var scheme = ColorScheme.fromSeed(seedColor: seed ?? primary, brightness: brightness).copyWith(
      primary: primary,
      secondary: secondary,
      surface: background,
      surfaceContainer: surface,
      surfaceContainerHigh: surfaceHigh,
    );
    if (outline) scheme = scheme.copyWith(outlineVariant: border);
    if (onPrimary != null) scheme = scheme.copyWith(onPrimary: onPrimary);
    if (onSurface != null) scheme = scheme.copyWith(onSurface: onSurface);
    final pageColor = style.transparentPages ? Colors.transparent : background;
    final base = ThemeData(useMaterial3: true, brightness: brightness, colorScheme: scheme);
    final custom = !identical(style, HubStyle.standard); // Standard bleibt exakt wie bisher
    final text = !custom ? base.textTheme : base.textTheme.copyWith(
      headlineSmall: base.textTheme.headlineSmall?.copyWith(fontWeight: style.titleWeight),
      titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: style.titleWeight),
      titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: style.titleWeight),
    );
    final cardShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.all(Radius.circular(style.radius)),
      side: style.borderSide,
    );
    final chipSide = style.borderWidth >= 2 ? BorderSide(color: border, width: 2) : BorderSide(color: border);
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      textTheme: custom ? text : null,
      extensions: [style],
      scaffoldBackgroundColor: pageColor,
      cardTheme: CardThemeData(
        color: style.cardFill,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: cardShape,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: pageColor,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: custom ? text.titleLarge?.copyWith(color: scheme.onSurface) : null,
      ),
      chipTheme: custom ? ChipThemeData(shape: StadiumBorder(side: chipSide)) : null,
      segmentedButtonTheme: !custom ? null : SegmentedButtonThemeData(
        style: ButtonStyle(
          side: WidgetStatePropertyAll(chipSide),
          backgroundColor: WidgetStateProperty.resolveWith((states) => states.contains(WidgetState.selected)
              ? (style.accents.isNotEmpty && style.bandHeader ? style.accents.first : scheme.secondaryContainer)
              : (style.glass ? Colors.white.withValues(alpha: 0.06) : surface)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: style.floatingNav ? Colors.transparent : surface,
        elevation: custom ? 0 : null,
        indicatorColor: !custom
            ? null
            : style.bandHeader && style.accents.isNotEmpty
                ? style.accents.first
                : style.glass
                    ? primary.withValues(alpha: 0.38)
                    : Color.lerp(surface, primary, 0.2),
        indicatorShape: custom && style.borderWidth >= 2
            ? StadiumBorder(side: BorderSide(color: border, width: 2))
            : null,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: surface,
        labelType: NavigationRailLabelType.all,
      ),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(14))),
      ),
      snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    );
  }
}
