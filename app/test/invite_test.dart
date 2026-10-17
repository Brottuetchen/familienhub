import 'package:familienhub/models/admin.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/admin/admin_users_screen.dart';
import 'package:familienhub/screens/auth/login_screen.dart';
import 'package:familienhub/screens/invite/invite_widgets.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

Map<String, dynamic> _invite({int id = 5, String? code = 'ABCD-EFGH-JKLM', bool oidc = false}) => {
      'id': id, 'user_id': 9, 'display_name': 'Oma', 'email': 'oma@example.org', 'username': 'oma', 'role': 'guest',
      'expires_at': '2026-10-24T20:00:00', 'expired': false, 'code': code, 'oidc': oidc,
    };

FakeBackend _backend() {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/admin/users', [
    {'id': 1, 'username': 'alex', 'display_name': 'Alex', 'role': 'admin', 'is_active': true, 'links': {}},
  ]);
  b.json('GET', '/api/admin/invites', {'items': [_invite(code: null)]});
  b.json('POST', '/api/admin/invites', _invite(), status: 201);
  b.json('POST', '/api/admin/invites/5/renew', _invite(id: 6, code: 'NEUE-CODE-WXYZ'));
  b.json('DELETE', '/api/admin/invites/5', {'revoked': true, 'deactivated': true});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  test('Einladungstext: ohne Anmeldedienst mit Code, mit Authentik mit E-Mail', () {
    final plain = inviteText(invite: InviteInfo.fromJson(_invite()), server: 'https://hub.test');
    expect(plain, contains('https://hub.test/downloads/'));
    expect(plain, contains('Server-Adresse in der App: https://hub.test'));
    expect(plain, contains('Code ABCD-EFGH-JKLM'));
    expect(plain, isNot(contains('Authentik')));
    final sso = inviteText(invite: InviteInfo.fromJson(_invite(oidc: true)), server: 'https://hub.test');
    expect(sso, contains('Mit Authentik anmelden'));
    expect(sso, contains('oma@example.org'));
  });

  testWidgets('Person einladen: Daten senden, Code und Text zum Kopieren zeigen', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const AdminUsersScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('admin-user-invite')));
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(find.byKey(const Key('invite-send'))).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('invite-name')), 'Oma');
    await tester.enterText(find.byKey(const Key('invite-email')), 'oma@example.org');
    await tester.pump();
    await tester.tap(find.byKey(const Key('invite-send')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/admin/invites').single), {'display_name': 'Oma', 'email': 'oma@example.org', 'role': 'partner'});
    expect(find.byKey(const Key('invite-code')), findsOneWidget);
    expect(tester.widget<SelectableText>(find.byKey(const Key('invite-text'))).data, contains('https://hub.test'));
  });

  testWidgets('Offene Einladungen: neuer Code und zurückziehen', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const AdminUsersScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Offene Einladungen'), findsOneWidget);
    await tester.tap(find.byTooltip('Neuen Code erzeugen'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/admin/invites/5/renew'), hasLength(1));
    expect(find.text('NEUE-CODE-WXYZ'), findsOneWidget);
    Navigator.of(tester.element(find.byKey(const Key('invite-code')))).pop();
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Einladung zurückziehen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/admin/invites/5'), hasLength(1));
  });

  testWidgets('Einladung einlösen: Code und eigenes Passwort, danach angemeldet', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend();
    b.json('GET', '/api/health', {'status': 'ok', 'oidc': false});
    b.json('GET', '/api/setup/status', {'needs_setup': false});
    b.on('POST', '/api/invites/accept', (r) => bodyOf(r)['code'] == 'ABCD-EFGH-JKLM'
        ? jsonResponse({'access_token': 'a9', 'refresh_token': 'r9', 'user': {...meJson, 'username': 'oma'}})
        : jsonResponse({'detail': 'Einladungscode ungültig oder abgelaufen – bitte um einen neuen'}, status: 403));
    final api = b.api(store: MemorySessionStore(url: 'https://hub.test'));
    await tester.pumpWidget(appWith(api, const LoginScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('login-accept-invite')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('accept-code')), 'ABCD');
    await tester.enterText(find.byKey(const Key('accept-password')), 'mein-eigenes-pw');
    await tester.enterText(find.byKey(const Key('accept-repeat')), 'mein-eigenes-pw');
    await tester.tap(find.byKey(const Key('accept-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('12 Zeichen'), findsOneWidget);
    expect(b.sent('POST', '/api/invites/accept'), isEmpty);
    await tester.enterText(find.byKey(const Key('accept-code')), 'WXYZ-WXYZ-WXYZ');
    await tester.tap(find.byKey(const Key('accept-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('ungültig oder abgelaufen'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('accept-code')), 'ABCD-EFGH-JKLM');
    await tester.tap(find.byKey(const Key('accept-submit')));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(LoginScreen)));
    expect(container.read(sessionProvider).phase, SessionPhase.loggedIn);
    expect(await api.store.accessToken(), 'a9');
    expect(bodyOf(b.sent('POST', '/api/invites/accept').last),
        {'code': 'ABCD-EFGH-JKLM', 'password': 'mein-eigenes-pw', 'client': 'app'});
  });
}
