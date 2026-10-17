import 'package:familienhub/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('maps backend oidc error codes to German messages', () {
    expect(oidcErrorText('unknown_user'), contains('nicht freigeschaltet'));
    expect(oidcErrorText('cancelled'), 'Anmeldung abgebrochen.');
    expect(oidcErrorText('expired'), contains('zu lange'));
    expect(oidcErrorText('irgendwas'), 'Anmeldung über Authentik fehlgeschlagen.');
  });
}
