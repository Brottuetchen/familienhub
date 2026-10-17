import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/core/theme/hub_style.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

ThemeSpec _spec(Map<String, dynamic> font) => ThemeSpec.fromJson({
      'id': 'x', 'name': 'Pixel',
      'colors': {'primary': '#D9762B', 'secondary': '#6B8E4E', 'background': '#F3E4C8', 'surface': '#FFF4DF',
        'surfaceHigh': '#F6E0B8', 'border': '#4A2F22'},
      'style': {'uppercaseTitles': true, 'font': font},
    });

void main() {
  test('Theme-Schriften: Überschriften, Fließtext und Labels getrennt', () {
    final t = AppTheme.fromSpec(_spec({'title': 'pixel', 'body': 'system', 'label': 'mono'}));
    expect(t.textTheme.titleLarge!.fontFamily, 'PixelifySans');
    expect(t.textTheme.headlineMedium!.fontFamily, 'PixelifySans');
    expect(t.textTheme.labelSmall!.fontFamily, 'JetBrainsMono');
    expect(t.textTheme.bodyMedium!.fontFamily, isNot(anyOf('PixelifySans', 'JetBrainsMono')));
  });

  test('Unbekannte Schrift fällt auf die Systemschrift zurück', () {
    final s = HubStyle.fromSpec(_spec({'title': 'Comic Sans'}));
    expect(s.titleFont, isNull);
  });

  testWidgets('Karten-Überschriften in Versal nutzen die Label-Schrift', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.fromSpec(_spec({'title': 'pixel', 'label': 'pixel'})),
      home: const Scaffold(body: SectionCard(icon: Icons.home, title: 'Haus', child: SizedBox())),
    ));
    final title = tester.widget<Text>(find.text('HAUS'));
    expect(title.style!.fontFamily, 'PixelifySans');
  });
}
