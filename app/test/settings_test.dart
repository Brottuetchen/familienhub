import 'package:familienhub/screens/admin/admin_screen.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:familienhub/screens/more/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  testWidgets('a normal user sees the personal groups, logout and version', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', {...meJson, 'is_admin': false});
    await tester.pumpWidget(appWith(b.api(), const SettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Ich'), findsOneWidget);
    expect(find.text('Konten & Verbindungen'), findsOneWidget);
    for (final k in ['settings-profile', 'settings-notifications', 'settings-appearance', 'settings-api-tokens', 'settings-logout', 'settings-version']) {
      expect(find.byKey(Key(k)), findsOneWidget, reason: k);
    }
    expect(find.byKey(const Key('more-admin')), findsNothing);
    expect(find.byKey(const Key('admin-themes')), findsNothing);
  });

  testWidgets('logout asks for confirmation and can be cancelled', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = FakeBackend();
    addDefaults(b);
    await tester.pumpWidget(appWith(b.api(), const SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-logout')));
    await tester.pumpAndSettle();
    expect(find.text('Abmelden?'), findsOneWidget);
    await tester.tap(find.text('Abbrechen'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/auth/logout'), isEmpty);
  });

  testWidgets('the task place tile opens its screen when the server knows the setting', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/tasks/me/place', {'place': 'hub', 'explicit': null, 'auto': 'hub', 'options': []});
    await tester.pumpWidget(appWith(b.api(), const SettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('settings-task-place')), findsOneWidget);
  });

  testWidgets('personal appearance has no theme install button', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/themes', {'items': []});
    await tester.pumpWidget(appWith(b.api(), const SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-appearance')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('theme-install')), findsNothing);
    expect(find.text('Aus GitHub'), findsNothing);
  });

  testWidgets('More keeps only content plus Settings and Feedback at the bottom', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', {...meJson, 'is_admin': false});
    await tester.pumpWidget(appWith(b.api(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-settings')), findsOneWidget);
    expect(find.byKey(const Key('more-feedback')), findsOneWidget);
    expect(find.byKey(const Key('more-admin')), findsNothing);
    expect(find.text('Abmelden'), findsNothing);
  });

  testWidgets('Administration groups the areas and has the themes and server rows', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/admin/overview', {'server': {'version': '1'}, 'plugins': [], 'push': {}, 'users': {'active': 1}});
    await tester.pumpWidget(appWith(b.api(), const AdminScreen()));
    await tester.pumpAndSettle();
    for (final h in ['Familie', 'Daten', 'Erweiterungen', 'System']) {
      expect(find.text(h), findsOneWidget, reason: h);
    }
    expect(find.byKey(const Key('admin-themes')), findsOneWidget);
    expect(find.byKey(const Key('admin-server')), findsOneWidget);
  });
}
