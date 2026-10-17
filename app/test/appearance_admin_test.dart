import 'dart:convert';

import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/screens/more/appearance_screen.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:familienhub/screens/more/plugins_admin_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

const _cards = {
  'id': 'builtin:clean-cards',
  'name': 'Clean Cards',
  'builtin': true,
  'colors': {
    'primary': '#3B82F6', 'secondary': '#10B981', 'background': '#F8FAFC', 'surface': '#FFFFFF',
    'surfaceHigh': '#F1F5F9', 'border': '#E2E8F0',
  },
};
const _custom = {
  'id': 'custom:7',
  'name': 'Waldgrün',
  'builtin': false,
  'colors': {
    'primary': '#2E7D32', 'secondary': '#A5D6A7', 'background': '#0B1F0E', 'surface': '#13301A',
    'surfaceHigh': '#1C4224', 'border': '#2C5A35',
  },
};

void main() {
  setUp(setUpTestEnv);

  test('Theme aus Farbschema: hell/dunkel aus dem Hintergrund, Farben übernommen', () {
    final light = AppTheme.fromSpec(ThemeSpec.fromJson(_cards));
    expect(light.brightness, Brightness.light);
    expect(light.colorScheme.primary, const Color(0xFF3B82F6));
    expect(light.scaffoldBackgroundColor, const Color(0xFFF8FAFC));
    final dark = AppTheme.fromSpec(ThemeSpec.fromJson(_custom));
    expect(dark.brightness, Brightness.dark);
    // unvollständige Schemata fallen auf Standard zurück
    final broken = AppTheme.fromSpec(const ThemeSpec(id: 'x', name: 'x', colors: {'primary': 'rot'}));
    expect(broken.scaffoldBackgroundColor, AppTheme.dark.scaffoldBackgroundColor);
  });

  testWidgets('Theme wählen speichert es auf dem Gerät', (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/themes', {'items': [_cards, _custom]});
    await tester.pumpWidget(appWith(backend.api(), const AppearanceScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Standard'), findsOneWidget);
    expect(find.text('Clean Cards'), findsOneWidget);

    await tester.tap(find.text('Clean Cards'));
    await tester.pumpAndSettle();
    final saved = (await SharedPreferences.getInstance()).getString('theme_spec');
    expect(jsonDecode(saved!)['id'], 'builtin:clean-cards');
    expect(
      tester.widget<Icon>(find.descendant(of: find.byKey(const Key('theme-builtin:clean-cards')), matching: find.byIcon(Icons.check_circle))),
      isNotNull,
    );

    await tester.tap(find.text('Standard'));
    await tester.pumpAndSettle();
    expect((await SharedPreferences.getInstance()).getString('theme_spec'), isNull);
  });

  testWidgets('Admin installiert Theme aus GitHub und entfernt es', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/themes', {'items': [_cards, _custom]});
    backend.json('POST', '/api/themes', _custom, status: 201);
    backend.json('DELETE', '/api/themes/custom%3A7', {'deleted': true});
    await tester.pumpWidget(appWith(backend.api(), const AppearanceScreen()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Aus GitHub'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'https://github.com/familie/themes');
    await tester.tap(find.text('Installieren'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/themes').single), {'url': 'https://github.com/familie/themes'});

    // nur installierte Themes haben einen Löschen-Knopf
    expect(find.byTooltip('Theme entfernen'), findsOneWidget);
    await tester.tap(find.byTooltip('Theme entfernen'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Entfernen'));
    await tester.pumpAndSettle();
    expect(backend.requests.where((r) => r.method == 'DELETE'), hasLength(1));
  });

  testWidgets('ohne Admin: kein Installieren, kein Löschen, kein Plugin-Menü', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/auth/me', {...meJson, 'is_admin': false});
    backend.json('GET', '/api/themes', {'items': [_cards, _custom]});
    await tester.pumpWidget(appWith(backend.api(), const AppearanceScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Aus GitHub'), findsNothing);
    expect(find.byTooltip('Theme entfernen'), findsNothing);

    await tester.pumpWidget(appWith(backend.api(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Darstellung'), findsOneWidget);
    expect(find.text('Plugins & Zugänge'), findsNothing);
  });

  testWidgets('Plugins: abschalten und Zugänge speichern, Geheimnis bleibt leer = unverändert', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    final shelfarr = {
      'id': 'shelfarr', 'name': 'Shelfarr', 'description': 'Bücher wünschen', 'configured': true,
      'disabled': false, 'active': true,
      'fields': [
        {'key': 'SHELFARR_URL', 'label': 'Adresse', 'secret': false, 'required': true, 'help': '', 'value': 'https://alt', 'is_set': true},
        {'key': 'SHELFARR_TOKEN', 'label': 'API-Token', 'secret': true, 'required': true, 'help': '', 'value': '', 'is_set': true},
      ],
    };
    backend.json('GET', '/api/admin/settings', [shelfarr]);
    backend.json('PUT', '/api/admin/plugins/shelfarr', {...shelfarr, 'disabled': true, 'active': false});
    backend.json('PUT', '/api/admin/settings', {'saved': true, 'plugins': []});
    await tester.pumpWidget(appWith(backend.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Aktiv'), findsOneWidget);

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('PUT', '/api/admin/plugins/shelfarr').single), {'enabled': false});

    await tester.tap(find.text('Shelfarr'));
    await tester.pumpAndSettle();
    expect(find.text('Gespeichert – leer lassen, um es zu behalten'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('field-SHELFARR_URL')), 'https://neu');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('PUT', '/api/admin/settings').single), {
      'values': {'SHELFARR_URL': 'https://neu'},
    });
  });
}
