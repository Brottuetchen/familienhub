import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Calendar colours: the server's colour (Nextcloud) wins, the palette only fills in when there is none (#47).
void main() {
  setUp(setUpTestEnv);

  Future<Map<String, Color>> colorsFor(List<Map<String, Object?>> calendars) async {
    final backend = FakeBackend()..json('GET', '/api/calendar/calendars', calendars);
    final container = ProviderContainer(overrides: [apiClientProvider.overrideWithValue(backend.api())]);
    addTearDown(container.dispose);
    container.listen(calendarColorsProvider, (_, __) {});
    await container.read(calendarsProvider.future);
    return container.read(calendarColorsProvider);
  }

  Map<String, Object?> cal(String id, String? color) =>
      {'id': id, 'name': id, 'source': 'caldav', 'color': color, 'writable': true, 'family': false};

  test('server colour wins over the palette, also in #RRGGBBAA and #RGB form', () async {
    final colors = await colorsFor([
      cal('a', '#BC5C91'),
      cal('b', '#bc5c91ff'),
      cal('c', '#0a0'),
    ]);
    expect(colors['a'], const Color(0xFFBC5C91));
    expect(colors['b'], const Color(0xFFBC5C91));
    expect(colors['c'], const Color(0xFF00AA00));
  });

  test('palette colour only when the server has none (or sends garbage)', () async {
    final colors = await colorsFor([
      cal('a', '#BC5C91'),
      cal('b', null),
      cal('c', 'None'),
    ]);
    expect(colors['a'], const Color(0xFFBC5C91));
    // palette index follows the list position: second and third entries
    expect(colors['b'], const Color(0xFFE07A5F));
    expect(colors['c'], const Color(0xFF81B29A));
  });
}
