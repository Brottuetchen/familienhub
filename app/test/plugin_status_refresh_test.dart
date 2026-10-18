import 'package:familienhub/screens/more/plugins_admin_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// After saving a plugin's settings the list must show the new state right away (no stale provider).
void main() {
  setUp(setUpTestEnv);

  testWidgets('saving weather coordinates flips the plugin to active in the list', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final b = FakeBackend();
    addDefaults(b);
    var set = false;
    Map<String, dynamic> weather() => {
          'id': 'weather', 'name': 'Wetter (Open-Meteo)', 'description': 'Aktuelles Wetter', 'configured': set,
          'disabled': false, 'active': set,
          'fields': [
            {'key': 'WEATHER_LATITUDE', 'label': 'Breitengrad', 'secret': false, 'required': false, 'help': '',
              'value': set ? '48.14' : '', 'is_set': set},
          ],
        };
    b.on('GET', '/api/admin/settings', (_) => jsonResponse([weather()]));
    b.on('PUT', '/api/admin/settings', (_) {
      set = true;
      return jsonResponse({'saved': true, 'plugins': [weather()]});
    });
    b.json('GET', '/api/modules', {'modules': {}});

    await tester.pumpWidget(appWith(b.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Nicht eingerichtet'), findsOneWidget);

    await tester.tap(find.byKey(const Key('plugin-weather')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('field-WEATHER_LATITUDE')), '48.14');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Aktiv'), findsOneWidget);
    expect(find.textContaining('Nicht eingerichtet'), findsNothing);
  });
}
