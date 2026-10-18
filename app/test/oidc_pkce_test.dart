import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  test('Authentik-Anmeldung: Hash beim Start, Geheimnis beim Einlösen, danach vergessen', () async {
    final b = FakeBackend();
    b.json('GET', '/api/auth/oidc/start', {'url': 'https://auth.example/authorize?x=1'});
    b.json('POST', '/api/auth/oidc/exchange', {'access_token': 'a1', 'refresh_token': 'r1', 'user': meJson});
    final api = b.api();
    await api.oidcStartUrl();
    final challenge = b.sent('GET', '/api/auth/oidc/start').single.url.queryParameters['challenge']!;
    expect(challenge, hasLength(43));
    await api.exchangeOidcCode('code-1');
    final verifier = bodyOf(b.sent('POST', '/api/auth/oidc/exchange').single)['verifier'] as String;
    expect(base64Url.encode(sha256.convert(utf8.encode(verifier)).bytes).replaceAll('=', ''), challenge);
    await api.exchangeOidcCode('code-2');
    expect(bodyOf(b.sent('POST', '/api/auth/oidc/exchange').last).containsKey('verifier'), isFalse,
        reason: 'Geheimnis nur einmal verwendbar');
  });
}
