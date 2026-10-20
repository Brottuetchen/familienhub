import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/widgets/hub_nav_bar.dart';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

ThemeSpec _spec(String label, {String nav = 'floating'}) => ThemeSpec.fromJson({
      'id': 'x', 'name': 'Mono',
      'colors': {'primary': '#D9762B', 'secondary': '#6B8E4E', 'background': '#F3E4C8', 'surface': '#FFF4DF',
        'surfaceHigh': '#F6E0B8', 'border': '#4A2F22'},
      'style': {'nav': nav, 'font': {'label': label}},
    });

const _labels = ['Today', 'Calendar', 'Tasks', 'Shopping', 'Meals', 'More'];

/// Phone viewport: 390 x 844 dp.
void _phone(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

Widget _app(ThemeData theme, {double scale = 1.0, double width = 390, EdgeInsets margin = EdgeInsets.zero}) =>
    MaterialApp(
      theme: theme,
      home: MediaQuery(
        data: MediaQueryData(size: Size(width, 844), textScaler: TextScaler.linear(scale)),
        child: Scaffold(
          bottomNavigationBar: Padding(
            padding: margin,
            child: HubNavBar(
              selectedIndex: 0,
              onDestinationSelected: (_) {},
              destinations: [for (final l in _labels) NavigationDestination(icon: const Icon(Icons.home), label: l)],
            ),
          ),
        ),
      ),
    );

/// Every label must render on a single line and inside its slot (no clipping).
void _expectSingleLines(WidgetTester tester, {double width = 390}) {
  for (final l in _labels) {
    final render = tester.renderObject<RenderParagraph>(find.text(l));
    final metrics = render.getBoxesForSelection(TextSelection(baseOffset: 0, extentOffset: l.length));
    expect(render.size.width, lessThanOrEqualTo(width / _labels.length), reason: '$l overflows its slot');
    expect(metrics.map((b) => b.top).toSet().length, 1, reason: '$l wraps');
  }
}

void main() {
  setUpAll(() async {
    // Real mono font, otherwise the test font (Ahem) hides the width problem.
    final loader = FontLoader('JetBrainsMono')
      ..addFont(Future.value(ByteData.sublistView(File('assets/fonts/JetBrainsMono/JetBrainsMono-Regular.ttf').readAsBytesSync())))
      ..addFont(Future.value(ByteData.sublistView(File('assets/fonts/JetBrainsMono/JetBrainsMono-Bold.ttf').readAsBytesSync())));
    await loader.load();
  });

  for (final (name, scale, margin) in [
    ('mono, 390 dp', 1.0, EdgeInsets.zero),
    ('mono, floating margins', 1.0, const EdgeInsets.symmetric(horizontal: 16)),
    ('mono, text scale 2.0', 2.0, const EdgeInsets.symmetric(horizontal: 16)),
  ]) {
    testWidgets('labels stay on one line: $name', (tester) async {
      _phone(tester);
      await tester.pumpWidget(_app(AppTheme.fromSpec(_spec('mono')), scale: scale, margin: margin));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      _expectSingleLines(tester);
    });
  }

  testWidgets('regular theme (non-floating) keeps labels on one line at scale 2.0', (tester) async {
    _phone(tester);
    await tester.pumpWidget(_app(AppTheme.fromSpec(_spec('system', nav: 'bar')), scale: 2.0));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    _expectSingleLines(tester);
  });
}
