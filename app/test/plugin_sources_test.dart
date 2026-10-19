import 'dart:convert';

import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/widgets/hub_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'helpers.dart';

// A 1x1 PNG
final _png = base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');

/// Plugins as data sources: recipe sources from a plugin (named by the plugin, images from a hub route).
void main() {
  setUp(setUpTestEnv);

  String day(int add) => DateTime.now().add(Duration(days: add)).toIso8601String().substring(0, 10);

  FakeBackend backend() {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/modules', {'modules': {'today': {'enabled': true}, 'meals': {'enabled': true},
      'meal_planning': {'enabled': true, 'plugin': 'fakecook'}}, 'plugins': []});
    b.json('GET', '/api/recipe-sources', [{'id': 'fakecook', 'name': 'Fake Cook'}]);
    b.json('GET', '/api/recipe-sources/fakecook/search', {'status': 'ok', 'error': null, 'total': 1,
      'items': [{'id': '7', 'name': 'Kartoffelauflauf', 'thumbnail': '/api/plugins/fakecook/img/7', 'image': '/api/plugins/fakecook/img/7',
        'url': 'https://x.test/7', 'minutes': 40}]});
    b.json('GET', '/api/recipe-sources/fakecook/recipes/7', {'status': 'ok', 'error': null, 'id': '7', 'source': 'fakecook',
      'title': 'Kartoffelauflauf', 'image': '/api/plugins/fakecook/img/7', 'minutes': 40, 'servings': 4,
      'ingredients': ['500 g Kartoffeln'], 'steps': ['Backen'], 'url': 'https://x.test/7'});
    b.json('POST', '/api/recipe-sources/fakecook/plan', {'date': day(0), 'recipe_id': '7'});
    b.json('POST', '/api/recipe-sources/fakecook/shopping', {'added': 1});
    b.json('DELETE', '/api/recipe-sources/fakecook/plan/${day(0)}/7', {'removed': true});
    b.on('GET', '/api/plugins/fakecook/img/7', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    b.json('GET', '/api/meals', {'status': 'ok', 'error': null, 'days': [
      for (var i = 0; i < 7; i++)
        {'date': day(i), 'entries': [
          if (i == 0)
            {'title': 'Kartoffelauflauf', 'source': 'fakecook', 'source_name': 'Fake Cook', 'recipe_id': '7', 'minutes': 40,
              'image': '/api/plugins/fakecook/img/7', 'url': 'https://x.test/7'},
        ]},
    ]});
    return b;
  }

  testWidgets('add meal offers "Recipe from <plugin>", search, quick view, plan and ingredients', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Essen eintragen').first);
    await tester.pumpAndSettle();
    expect(find.text('Rezept aus Fake Cook'), findsOneWidget);
    await tester.tap(find.text('Rezept aus Fake Cook'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'kart');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/recipe-sources/fakecook/search').single.url.queryParameters['q'], 'kart');
    // The thumbnail is a hub route: loaded with the login
    expect(b.sent('GET', '/api/plugins/fakecook/img/7').first.headers['Authorization'], 'Bearer token-1');
    await tester.tap(find.text('Kartoffelauflauf').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('500 g Kartoffeln'), findsOneWidget);
    expect(find.text('Fake Cook'), findsWidgets); // the quick view names the source
    await tester.tap(find.byKey(const Key('recipe-shopping')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipe-sources/fakecook/shopping').single)['recipe_ids'], ['7']);
    await tester.tap(find.byKey(const Key('recipe-plan')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/recipe-sources/fakecook/plan').single)['recipe_id'], '7');
  });

  testWidgets('plugin entry in the week is labelled with the plugin and can be removed via the source', (tester) async {
    final b = backend();
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const MealsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Rezept-Aktionen'));
    await tester.pumpAndSettle();
    expect(find.text('In Fake Cook öffnen'), findsOneWidget);
    await tester.tap(find.text('Aus dem Plan nehmen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/recipe-sources/fakecook/plan/${day(0)}/7'), hasLength(1));
  });

  testWidgets('HubImage: hub routes load with the login and are cached, other addresses load directly', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    b.on('GET', '/api/plugins/photos/thumb/1', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    b.on('GET', '/api/plugins/photos/thumb/2', (_) => http.Response('nope', 404));
    expect(isHubImageUrl('/api/plugins/photos/thumb/1'), isTrue);
    expect(isHubImageUrl('https://mealie.test/a.png'), isFalse);
    expect(isHubImageUrl('//evil.test/a.png'), isFalse);
    expect(isHubImageUrl(null), isFalse);

    const placeholder = SizedBox(key: Key('placeholder'), width: 10, height: 10);
    Widget image(String? url) => HubImage(url: url, width: 40, height: 40, placeholder: placeholder);
    await tester.pumpWidget(appWith(b.api(), Column(children: [
      image('/api/plugins/photos/thumb/1'),
      image('/api/plugins/photos/thumb/2'),
      image(null),
    ])));
    await tester.pumpAndSettle();
    expect(b.sent('GET', '/api/plugins/photos/thumb/1').single.headers['Authorization'], 'Bearer token-1');
    expect(find.byType(Image), findsOneWidget); // only the first one loaded
    expect(find.byKey(const Key('placeholder')), findsNWidgets(2)); // 404 and no URL
    // An absolute address never goes through the hub
    await tester.pumpWidget(appWith(b.api(), image('https://mealie.test/a.png')));
    await tester.pumpAndSettle();
    expect(b.requests.where((r) => r.url.host == 'mealie.test'), isEmpty);
  });
}
