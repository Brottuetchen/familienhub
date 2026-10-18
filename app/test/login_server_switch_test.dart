import 'package:familienhub/main.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Server A has no Authentik, server B has: after switching the server the login screen must offer the
/// Authentik button right away (it used to keep the capabilities of server A until the app restarted).
void main() {
  setUp(setUpTestEnv);

  testWidgets('switching from a server without OIDC to one with OIDC shows the Authentik button', (tester) async {
    await setScreenSize(tester, const Size(420, 1000));
    final b = FakeBackend();
    bool oidc(Uri u) => u.host == 'b.test';
    b.on('GET', '/api/health', (r) => jsonResponse({
          'status': 'online',
          'features': {'oidc': oidc(r.url), 'push': false},
        }));
    b.on('GET', '/api/setup/status', (r) => jsonResponse({
          'needs_setup': false,
          'app_name': 'Familienhub',
          'oidc': oidc(r.url),
          'code_required': true,
        }));
    final api = b.api(store: MemorySessionStore(url: 'https://a.test'));

    await tester.pumpWidget(appWith(api, const AuthGate()));
    await tester.pumpAndSettle();
    expect(find.text('https://a.test'), findsOneWidget);
    expect(find.text('Mit Authentik anmelden'), findsNothing);

    await tester.tap(find.text('Anderen Server wählen'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'https://b.test');
    await tester.tap(find.text('Verbinden'));
    await tester.pumpAndSettle();

    expect(find.text('https://b.test'), findsOneWidget);
    expect(find.text('Mit Authentik anmelden'), findsOneWidget);
  });
}
