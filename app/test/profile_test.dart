import 'dart:convert';
import 'dart:typed_data';

import 'package:familienhub/screens/more/avatar_crop_screen.dart';
import 'package:familienhub/screens/more/profile_screen.dart';
import 'package:familienhub/screens/today/today_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

import 'helpers.dart';

// 1×1 PNG
final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==');

Map<String, dynamic> _me({String? name, String? color, String? avatar}) => {
      ...meJson,
      'display_name': name ?? 'Alex',
      'avatar_color': color,
      'avatar_url': avatar,
    };

void main() {
  setUp(setUpTestEnv);

  test('Initialen unterscheiden Personen mit gleichem Anfangsbuchstaben', () {
    expect(initialsOf('Christian'), 'Ch');
    expect(initialsOf('Clara'), 'Cl');
    expect(initialsOf('Anna Beispiel'), 'AB');
    expect(initialsOf(' '), '?');
  });

  testWidgets('Name und Farbe speichern und sofort übernehmen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', _me());
    b.on('PATCH', '/api/me/profile', (r) {
      final body = jsonDecode(r.body) as Map<String, dynamic>;
      return jsonResponse(_me(name: body['display_name'] as String, color: body['avatar_color'] as String?));
    });
    await tester.pumpWidget(appWith(b.api(), const ProfileScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('profile-name')), 'Alexander');
    await tester.tap(find.byKey(const Key('profile-color-#10B981')));
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/me/profile').single), {'display_name': 'Alexander', 'avatar_color': '#10B981'});
    expect(find.text('Profil gespeichert'), findsOneWidget);
    final avatar = tester.widget<PersonAvatar>(find.byKey(const Key('profile-avatar')));
    expect(avatar.name, 'Alexander');
    expect(avatar.color, '#10B981');
  });

  testWidgets('Foto hochladen, anzeigen und wieder entfernen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', _me());
    b.json('PUT', '/api/me/avatar', _me(avatar: '/api/users/1/avatar?v=1'));
    b.json('DELETE', '/api/me/avatar', _me());
    b.on('GET', '/api/users/1/avatar', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    await tester.pumpWidget(appWith(b.api(), ProfileScreen(pickImage: (_) async => Uint8List.fromList(_png), cropImage: (_, b) async => b)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('profile-photo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aus der Galerie'));
    await tester.pumpAndSettle();
    expect(base64Decode(bodyOf(b.sent('PUT', '/api/me/avatar').single)['image'] as String), _png);
    expect(find.descendant(of: find.byKey(const Key('profile-avatar')), matching: find.byType(Image)), findsOneWidget);

    await tester.tap(find.byKey(const Key('profile-photo-remove')));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/me/avatar'), hasLength(1));
    expect(find.byKey(const Key('profile-photo-remove')), findsNothing);
  });

  testWidgets('Zu großes Foto wird nicht hochgeladen', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', _me());
    await tester.pumpWidget(appWith(b.api(), ProfileScreen(pickImage: (_) async => Uint8List(600 * 1024), cropImage: (_, b) async => b)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('profile-photo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aus der Galerie'));
    await tester.pumpAndSettle();
    expect(b.sent('PUT', '/api/me/avatar'), isEmpty);
    expect(find.textContaining('zu groß'), findsOneWidget);
  });

  test('Zuschnitt wird quadratisch, höchstens 512 px und JPEG', () {
    final wide = Uint8List.fromList(img.encodePng(img.Image(width: 1200, height: 800)));
    final out = img.decodeJpg(prepareAvatar(wide))!;
    expect([out.width, out.height], [512, 512]);
    final small = img.decodeJpg(prepareAvatar(Uint8List.fromList(img.encodePng(img.Image(width: 100, height: 100)))))!;
    expect([small.width, small.height], [100, 100]); // kleine Bilder nicht hochskalieren
    expect(() => prepareAvatar(Uint8List.fromList([1, 2, 3])), throwsFormatException);
  });

  testWidgets('Gewähltes Bild geht erst durchs Zuschneiden; Abbrechen lädt nichts hoch', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', _me());
    b.json('PUT', '/api/me/avatar', _me(avatar: '/api/users/1/avatar?v=2'));
    b.on('GET', '/api/users/1/avatar', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    final picked = Uint8List.fromList([9, 9, 9]);
    final cropped = Uint8List.fromList(_png);
    Uint8List? seen;
    var cancel = true;
    await tester.pumpWidget(appWith(
        b.api(),
        ProfileScreen(
          pickImage: (_) async => picked,
          cropImage: (_, image) async {
            seen = image;
            return cancel ? null : cropped;
          },
        )));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('profile-photo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aus der Galerie'));
    await tester.pumpAndSettle();
    expect(seen, picked);
    expect(b.sent('PUT', '/api/me/avatar'), isEmpty);

    cancel = false;
    await tester.tap(find.byKey(const Key('profile-photo')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aus der Galerie'));
    await tester.pumpAndSettle();
    expect(base64Decode(bodyOf(b.sent('PUT', '/api/me/avatar').single)['image'] as String), cropped);
  });

  testWidgets('Mit Foto ist die gewählte Farbe der Rahmen', (tester) async {
    final b = FakeBackend();
    b.on('GET', '/api/users/1/avatar', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    await tester.pumpWidget(appWith(
        b.api(), const Center(child: PersonAvatar(name: 'Alex', id: 1, size: 112, color: '#10B981', imageUrl: '/api/users/1/avatar?v=1'))));
    await tester.pumpAndSettle();
    final ring = tester.widget<Container>(find.byKey(const Key('avatar-ring')));
    expect((ring.decoration! as BoxDecoration).color, const Color(0xFF10B981));
    expect(find.descendant(of: find.byKey(const Key('avatar-ring')), matching: find.byType(Image)), findsOneWidget);
  });

  testWidgets('Zuschneide-Bildschirm liefert ein fertiges Profilbild', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final source = Uint8List.fromList(img.encodePng(img.Image(width: 900, height: 600)));
    Uint8List? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () async => result = await Navigator.push<Uint8List>(
              context, MaterialPageRoute(builder: (_) => AvatarCropScreen(image: source))),
          child: const Text('los'),
        ),
      ),
    ));
    await tester.tap(find.text('los'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500)); // Seitenübergang
    // Bild wird asynchron dekodiert
    for (var i = 0; i < 50 && tester.widget<FilledButton>(find.byKey(const Key('crop-done'))).onPressed == null; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pump();
    }
    await tester.tap(find.byKey(const Key('crop-done')));
    for (var i = 0; i < 50 && result == null; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pump();
    }
    final out = img.decodeJpg(result!)!;
    expect(out.width, out.height);
    expect(out.width, lessThanOrEqualTo(avatarPixels));
  });
}
