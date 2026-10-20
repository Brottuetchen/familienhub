import 'package:flutter_test/flutter_test.dart';
import 'package:familienhub/services/page_base_url.dart';

void main() {
  test('root deployment keeps just the origin', () {
    expect(serverBaseFromPage('https://hub.example.org/'), 'https://hub.example.org');
    expect(serverBaseFromPage('http://192.168.1.5:8000/'), 'http://192.168.1.5:8000');
  });

  test('sub-path prefix (Home Assistant ingress) is kept without trailing slash', () {
    expect(serverBaseFromPage('http://homeassistant.local:8123/api/hassio_ingress/AbC-1_x/'),
        'http://homeassistant.local:8123/api/hassio_ingress/AbC-1_x');
  });

  test('query and fragment never end up in the server address', () {
    expect(serverBaseFromPage('https://hub.example.org/hub/?route=/tasks#/x'), 'https://hub.example.org/hub');
  });
}
