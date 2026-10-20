import 'package:flutter/material.dart';

/// Bottom navigation bar whose labels always stay on one line.
///
/// [NavigationDestination] only takes a plain string and lets it wrap, so a
/// wide label font (mono) or a large text scale breaks words mid-letter
/// ("Calenda/r"). This bar measures the labels with the themed label style and,
/// if the longest one does not fit into its slot, shrinks the label font size
/// just enough.
class HubNavBar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final List<NavigationDestination> destinations;

  const HubNavBar({
    super.key,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.destinations,
  });

  /// Material clamps the label text scale to this value.
  static const _maxLabelScale = 1.3;

  /// Horizontal space the label may use inside one destination slot.
  static const _slotPadding = 4.0;

  @override
  Widget build(BuildContext context) {
    final bar = NavigationBar(
      selectedIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      destinations: destinations,
    );
    if (destinations.isEmpty) return bar;
    return LayoutBuilder(builder: (context, constraints) {
      if (!constraints.hasBoundedWidth) return bar;
      final navTheme = NavigationBarTheme.of(context);
      final fallback = Theme.of(context).textTheme.labelMedium ?? const TextStyle(fontSize: 12);
      final selected = navTheme.labelTextStyle?.resolve({WidgetState.selected}) ?? fallback;
      final unselected = navTheme.labelTextStyle?.resolve({}) ?? fallback;
      final scaler = MediaQuery.textScalerOf(context).clamp(maxScaleFactor: _maxLabelScale);
      final dir = Directionality.of(context);

      double widest(TextStyle style) {
        var w = 0.0;
        for (final d in destinations) {
          final p = TextPainter(
            text: TextSpan(text: d.label, style: style),
            textDirection: dir,
            textScaler: scaler,
            maxLines: 1,
          )..layout();
          if (p.width > w) w = p.width;
          p.dispose();
        }
        return w;
      }

      final avail = constraints.maxWidth / destinations.length - _slotPadding;
      final needed = widest(selected) > widest(unselected) ? widest(selected) : widest(unselected);
      if (avail <= 0 || needed <= avail) return bar;
      final factor = avail / needed;
      TextStyle shrink(TextStyle s) => s.copyWith(fontSize: (s.fontSize ?? 12) * factor);
      return NavigationBarTheme(
        data: navTheme.copyWith(
          labelTextStyle: WidgetStateProperty.resolveWith(
            (states) => shrink(states.contains(WidgetState.selected) ? selected : unselected),
          ),
        ),
        child: bar,
      );
    });
  }
}
