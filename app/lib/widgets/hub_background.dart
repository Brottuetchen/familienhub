import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import '../core/theme/hub_style.dart';

/// Hintergrund hinter allen Seiten: einfarbig, Verlauf (Warm) oder leuchtende Farbflecken (Liquid Glass).
class HubBackground extends StatelessWidget {
  final Widget child;
  const HubBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final style = HubStyle.of(context);
    if (!style.transparentPages) return child;
    final colors = style.backgroundColors;
    return Stack(
      fit: StackFit.expand,
      children: [
        ColoredBox(color: style.base),
        if (style.background == HubBackgroundType.gradient && colors.length >= 2)
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: colors),
            ),
          ),
        if (style.background == HubBackgroundType.glow)
          IgnorePointer(
            child: ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: 60, sigmaY: 60),
              child: Stack(
                children: [
                  // feste Plätze wie in der Vorlage: oben rechts, Mitte links, unten rechts
                  for (final (i, spot) in const [
                    (0, Alignment(1.1, -0.95)),
                    (1, Alignment(-1.2, 0.05)),
                    (2, Alignment(1.0, 0.75)),
                  ])
                    if (colors.isNotEmpty)
                      Align(
                        alignment: spot,
                        child: Container(
                          width: 260,
                          height: 260,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: colors[i % colors.length].withValues(alpha: 0.55),
                          ),
                        ),
                      ),
                ],
              ),
            ),
          ),
        child,
      ],
    );
  }
}

/// Kartenfläche in der Designsprache des Themes: Glas (Unschärfe), harter Schatten, weicher Schatten …
class HubSurface extends StatelessWidget {
  final Widget child;
  final double? radius;
  final VoidCallback? onTap;
  const HubSurface({super.key, required this.child, this.radius, this.onTap});

  @override
  Widget build(BuildContext context) {
    final style = HubStyle.of(context);
    final r = BorderRadius.circular(radius ?? style.radius);
    Widget content = Material(
      type: MaterialType.transparency,
      child: InkWell(borderRadius: r, onTap: onTap, child: child),
    );
    if (style.glass) {
      return ClipRRect(
        borderRadius: r,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          child: DecoratedBox(decoration: style.decoration(radius: radius), child: content),
        ),
      );
    }
    return DecoratedBox(
      decoration: style.decoration(radius: radius),
      child: ClipRRect(borderRadius: r, child: content),
    );
  }
}
