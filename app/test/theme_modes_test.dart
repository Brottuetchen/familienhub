import 'dart:convert';

import 'package:familienhub/main.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/providers/theme_provider.dart';
import 'package:familienhub/screens/more/appearance_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

const _light = {'primary': '#C8381B', 'secondary': '#141414', 'background': '#EFECE6', 'surface': '#F5F3EE',
  'surfaceHigh': '#E5E1D8', 'border': '#D3CEC3'};
const _dark = {'primary': '#E0482A', 'secondary': '#EDEAE3', 'background': '#121212', 'surface': '#1A1A1A',
  'surfaceHigh': '#242424', 'border': '#2E2E2E'};

final _both = {
  'id': 'custom:1', 'name': 'Präzision', 'builtin': false, 'colors': _light, 'style': {'layout': 'bento'},
  'variants': {'dark': {'colors': _dark, 'style': {'layout': 'bento'}}},
};

void main() {
  setUp(setUpTestEnv);

  test('Fassung nach Hell/Dunkel, ohne Variante bleibt die Grundfassung', () {
    final t = ThemeSpec.fromJson(_both);
    expect(t.brightness, Brightness.light);
    expect(t.hasBothModes, isTrue);
    expect(t.forBrightness(Brightness.light).color('background'), const Color(0xFFEFECE6));
    expect(t.forBrightness(Brightness.dark).color('background'), const Color(0xFF121212));
    final only = ThemeSpec.fromJson({'id': 'x', 'name': 'Alt', 'colors': _light});
    expect(only.hasBothModes, isFalse);
    expect(only.forBrightness(Brightness.dark).color('background'), const Color(0xFFEFECE6));
  });

  test('Gespeichertes Theme behält beide Fassungen (Start ohne Netz)', () {
    final again = ThemeSpec.fromJson(jsonDecode(jsonEncode(ThemeSpec.fromJson(_both).toJson())) as Map<String, dynamic>);
    expect(again.forBrightness(Brightness.dark).color('background'), const Color(0xFF121212));
  });

  testWidgets('Darstellung: Automatisch/Hell/Dunkel wählen und merken; Themes zeigen ihre Fassungen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/themes', {'items': [_both, {'id': 'custom:2', 'name': 'Alt', 'builtin': false, 'colors': _light}]});
    await tester.pumpWidget(appWith(b.api(), const AppearanceScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Hell + Dunkel'), findsOneWidget);
    expect(find.textContaining('nur Hell'), findsOneWidget);
    await tester.tap(find.text('Dunkel'));
    await tester.pumpAndSettle();
    expect((await SharedPreferences.getInstance()).getString('theme_mode'), 'dark');
  });

  testWidgets('App nutzt die passende Fassung als hell/dunkel und folgt dem Modus', (tester) async {
    SharedPreferences.setMockInitialValues({'theme_spec': jsonEncode(_both), 'theme_mode': 'dark'});
    final b = FakeBackend();
    addDefaults(b);
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: const FamilienhubApp(),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.themeMode, ThemeMode.dark);
    expect(app.theme!.scaffoldBackgroundColor, const Color(0xFFEFECE6));
    expect(app.darkTheme!.scaffoldBackgroundColor, const Color(0xFF121212));
    expect(Theme.of(tester.element(find.byType(Scaffold).first)).brightness, Brightness.dark);
    final container = ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));
    await container.read(themeModeProvider.notifier).select(ThemeMode.light);
    await tester.pump();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode, ThemeMode.light);
  });
}
