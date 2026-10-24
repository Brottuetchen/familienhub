// Plugin extension points in the app: Today cards, the layout editor, reward actions, the connection test.
import 'dart:convert';

import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/account.dart';
import 'package:familienhub/models/plugin_card.dart';
import 'package:familienhub/models/today.dart';
import 'package:familienhub/models/today_layout.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/more/plugin_install_screen.dart';
import 'package:familienhub/screens/stars/stars_screen.dart';
import 'package:familienhub/screens/today/plugin_card.dart';
import 'package:familienhub/screens/today/today_layout_editor.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'helpers.dart';

// A 1x1 PNG
final _png = base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');

const _cardJson = {
  'key': 'plugin:demo:garbage', 'plugin': 'demo', 'plugin_name': 'Demo', 'id': 'garbage', 'title': 'Müllabfuhr',
  'icon': 'delete_outline', 'badge': '2', 'image': null, 'link': null,
  'lines': [
    {'text': 'Papier morgen', 'secondary': 'ab 6 Uhr'},
    {'text': 'Gelber Sack', 'secondary': null},
  ],
};

PluginCardData _card([Map<String, dynamic> extra = const {}]) => PluginCardData.fromJson({..._cardJson, ...extra});

Widget _cardApp(FakeBackend b, Widget child, {double scale = 1.0}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        builder: (context, w) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
        home: Scaffold(body: SingleChildScrollView(child: Padding(padding: const EdgeInsets.all(16), child: child))),
      ),
    );

FakeBackend _backend({List<Object> pluginCards = const [], Object? layout}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/modules', {
    'modules': {for (final m in ['today', 'meals', 'tasks', 'calendar', 'shopping']) m: {'enabled': true}},
    'plugins': [],
  });
  b.json('GET', '/api/today', {
    'date': '2026-10-19',
    'events': [],
    'tasks': {'status': 'ok', 'error': null, 'items': []},
    'meals': [],
    'shopping_open': 0,
    'reminders': [],
    'plugin_cards': pluginCards,
  });
  if (layout != null) b.json('GET', '/api/me/today-layout', layout);
  b.json('PUT', '/api/me/today-layout', {'cards': [], 'source': 'user'});
  return b;
}

Widget _todayApp(FakeBackend b, {Widget? home}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(locale: const Locale('de', 'DE'), theme: AppTheme.dark, home: home ?? const TodayScreen()),
    );

Map<String, dynamic> _other(String key, String title) => {
      ..._cardJson, 'key': key, 'title': title, 'id': key.split(':').last, 'badge': null,
    };

double _y(WidgetTester t, String key) => t.getTopLeft(find.byKey(Key(key))).dy;

void main() {
  setUp(setUpTestEnv);

  test('cards parse and garbage is dropped', () {
    final list = PluginCardData.listFromJson([
      _cardJson,
      {'key': 'tasks', 'title': 'not a plugin card'},
      'junk',
      {'key': 'plugin:demo:x', 'title': 'No lines', 'lines': 'nope', 'icon': 5},
    ]);
    expect(list.map((c) => c.key), ['plugin:demo:garbage', 'plugin:demo:x']);
    expect(list.first.lines.map((l) => (l.text, l.secondary)), [('Papier morgen', 'ab 6 Uhr'), ('Gelber Sack', null)]);
    expect(list.first.badge, '2');
    expect(PluginCardData.listFromJson(null), isEmpty);
    expect(TodayData.fromJson({'date': '2026-10-19', 'plugin_cards': [_cardJson]}).pluginCards, hasLength(1));
    expect(TodayData.fromJson({'date': '2026-10-19'}).pluginCards, isEmpty);
    expect(pluginCardIcon('does_not_exist'), Icons.extension_outlined);
    expect(pluginCardIcon('delete_outline'), Icons.delete_outline);
  });

  test('the layout keeps plugin cards and appends new ones at the end', () {
    final l = TodayLayout.fromJson({
      'source': 'user',
      'cards': [
        {'id': 'plugin:demo:garbage', 'visible': false, 'size': 'half'},
        {'id': 'plugin:broken', 'visible': true},
        {'id': 'tasks', 'visible': true},
        {'id': 'nonsense', 'visible': true},
      ],
    });
    expect(l.cards.first.id, 'plugin:demo:garbage');
    expect(l.cards.first.visible, isFalse);
    expect(l.cards.first.half, isTrue);
    expect(l.cards.any((c) => c.id == 'plugin:broken' || c.id == 'nonsense'), isFalse);
    final more = l.withPluginCards(['plugin:demo:garbage', 'plugin:demo:new']);
    expect(more.cards.last.id, 'plugin:demo:new');
    expect(more.cards.last.visible, isTrue);
    expect(more.cards.where((c) => c.id == 'plugin:demo:garbage'), hasLength(1));
    expect(identical(l.withPluginCards(['plugin:demo:garbage']), l), isTrue);
  });

  test('notification settings offer the category of plugins', () {
    expect(notificationCategories.keys, contains('plugins'));
  });

  testWidgets('a plugin card shows title, icon, lines and badge', (tester) async {
    final b = FakeBackend();
    await tester.pumpWidget(_cardApp(b, PluginCard(card: _card())));
    expect(find.text('Müllabfuhr'), findsOneWidget);
    expect(find.byIcon(Icons.delete_outline), findsOneWidget);
    expect(find.text('Papier morgen'), findsOneWidget);
    expect(find.text('ab 6 Uhr'), findsOneWidget);
    expect(find.text('Gelber Sack'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(b.requests, isEmpty, reason: 'no image, nothing to load');
  });

  testWidgets('a link opens outside the app, only https', (tester) async {
    final opened = <Uri>[];
    final b = FakeBackend();
    await tester.pumpWidget(_cardApp(
        b, PluginCard(card: _card({'link': 'https://example.org/muell'}), openUrl: (u) async => opened.add(u))));
    expect(find.text('Öffnet example.org'), findsOneWidget);
    await tester.tap(find.text('Müllabfuhr'));
    expect(opened, [Uri.parse('https://example.org/muell')]);

    opened.clear();
    await tester.pumpWidget(_cardApp(
        b, PluginCard(card: _card({'link': 'javascript:alert(1)'}), openUrl: (u) async => opened.add(u))));
    await tester.tap(find.text('Müllabfuhr'));
    expect(opened, isEmpty);
    expect(find.textContaining('Öffnet'), findsNothing);
  });

  testWidgets('the picture is loaded with the login, and only from the plugin namespace', (tester) async {
    final b = FakeBackend();
    b.on('GET', '/api/plugins/demo/img/1.png', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    await tester.pumpWidget(_cardApp(b, PluginCard(card: _card({'image': '/api/plugins/demo/img/1.png'}))));
    await tester.pump();
    await tester.pump();
    final request = b.sent('GET', '/api/plugins/demo/img/1.png').single;
    expect(request.headers['Authorization'], 'Bearer token-1');
    expect(find.byKey(const Key('plugin-card-image')), findsOneWidget);

    // an address outside /api/plugins/ is never requested, whatever the server said
    final other = FakeBackend();
    other.json('GET', '/api/auth/me', {'secret': true});
    await tester.pumpWidget(_cardApp(other, PluginCard(card: _card({'image': '/api/auth/me'}))));
    await tester.pump();
    await tester.pump();
    expect(other.requests, isEmpty);
    expect(find.byKey(const Key('plugin-card-image')), findsNothing);
  });

  testWidgets('a picture that cannot be loaded leaves the card intact', (tester) async {
    final b = FakeBackend();
    b.json('GET', '/api/plugins/demo/img/1.png', {'detail': 'nope'}, status: 500);
    await tester.pumpWidget(_cardApp(b, PluginCard(card: _card({'image': '/api/plugins/demo/img/1.png'}))));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('plugin-card-image')), findsNothing);
    expect(find.text('Papier morgen'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('several pictures are one swipeable card with captions, dots and their own links', (tester) async {
    final b = FakeBackend();
    for (final n in [1, 2, 3]) {
      b.on('GET', '/api/plugins/demo/img/$n.png', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    }
    final opened = <Uri>[];
    final card = _card({
      'lines': <Object>[],
      'image': '/api/plugins/demo/img/1.png',
      'slides': [
        {'image': '/api/plugins/demo/img/1.png', 'caption': 'vor 1 Jahr', 'secondary': '24.10.2025',
         'link': 'https://photos.example.org/photos/1'},
        {'image': '/api/plugins/demo/img/2.png', 'caption': 'vor 3 Jahren', 'secondary': '24.10.2023',
         'link': 'https://photos.example.org/photos/2'},
        {'image': '/api/plugins/demo/img/3.png', 'caption': 'vor 5 Jahren', 'link': 'javascript:alert(1)'},
      ],
    });
    await tester.pumpWidget(_cardApp(b, PluginCard(card: card, openUrl: (u) async => opened.add(u))));
    await tester.pump();
    await tester.pump();
    expect(find.byType(PluginCard), findsOneWidget);
    expect(find.byKey(const Key('plugin-card-slides')), findsOneWidget);
    expect(find.byKey(const Key('plugin-card-slide-dot-2')), findsOneWidget);
    expect(find.text('vor 1 Jahr'), findsOneWidget);
    expect(find.text('24.10.2025'), findsOneWidget);

    await tester.tap(find.byKey(const Key('plugin-card-image')).first);
    expect(opened.single.toString(), 'https://photos.example.org/photos/1');

    await tester.drag(find.byKey(const Key('plugin-card-slides')), const Offset(-400, 0));
    await tester.pumpAndSettle();
    expect(find.text('vor 3 Jahren'), findsOneWidget);
    expect(find.text('vor 1 Jahr'), findsNothing);

    await tester.drag(find.byKey(const Key('plugin-card-slides')), const Offset(-400, 0));
    await tester.pumpAndSettle();
    expect(find.text('vor 5 Jahren'), findsOneWidget);
    await tester.tap(find.byKey(const Key('plugin-card-image')).last);
    expect(opened, hasLength(1)); // not https: nothing opens
    expect(tester.takeException(), isNull);
  });

  testWidgets('a single slide is shown as a normal picture', (tester) async {
    final b = FakeBackend();
    b.on('GET', '/api/plugins/demo/img/1.png', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
    final card = _card({
      'image': '/api/plugins/demo/img/1.png',
      'slides': [{'image': '/api/plugins/demo/img/1.png', 'caption': 'vor 1 Jahr'}],
    });
    await tester.pumpWidget(_cardApp(b, PluginCard(card: card)));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('plugin-card-slides')), findsNothing);
    expect(find.byKey(const Key('plugin-card-image')), findsOneWidget);
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('a plugin card with long texts fits 360 dp at text scale $scale', (tester) async {
      await setScreenSize(tester, const Size(360, 1600));
      final b = FakeBackend();
      b.on('GET', '/api/plugins/demo/img/1.png', (_) => http.Response.bytes(_png, 200, headers: {'content-type': 'image/png'}));
      final long = 'Sehr langer Text ohne Ende ' * 6;
      final card = _card({
        'title': 'Ein ziemlich langer Titel der Karte, der umbrechen muss',
        'badge': 'Ein langes Abzeichen',
        'image': '/api/plugins/demo/img/1.png',
        'link': 'https://sehr-lange-adresse-fuer-einen-test.example.org/pfad',
        'lines': [for (var i = 0; i < 6; i++) {'text': long, 'secondary': 'Zweiter Teil $long'}],
      });
      await tester.pumpWidget(_cardApp(b, PluginCard(card: card), scale: scale));
      await tester.pump();
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.byType(PluginCard), findsOneWidget);
    });
  }

  testWidgets('Today shows plugin cards in the saved order and appends new ones', (tester) async {
    await setScreenSize(tester, const Size(420, 2600));
    final b = _backend(pluginCards: [
      _cardJson,
      _other('plugin:demo:news', 'Nachrichten'),
    ], layout: {
      'source': 'user',
      'cards': [
        {'id': 'plugin:demo:garbage', 'visible': true, 'size': 'full'},
        {'id': 'tasks', 'visible': true, 'size': 'full'},
      ],
    });
    await tester.pumpWidget(_todayApp(b));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-card-plugin:demo:garbage')), findsOneWidget);
    expect(find.byKey(const Key('plugin-card-plugin:demo:news')), findsOneWidget);
    expect(_y(tester, 'plugin-card-plugin:demo:garbage'), lessThan(_y(tester, 'today-tasks')),
        reason: 'the saved order puts it first');
    expect(_y(tester, 'plugin-card-plugin:demo:news'), greaterThan(_y(tester, 'today-tasks')),
        reason: 'unknown cards come at the end');
  });

  testWidgets('a hidden plugin card is not shown, and without cards nothing changes', (tester) async {
    await setScreenSize(tester, const Size(420, 2600));
    final hidden = _backend(pluginCards: [_cardJson], layout: {
      'source': 'user',
      'cards': [
        {'id': 'plugin:demo:garbage', 'visible': false, 'size': 'full'},
        {'id': 'tasks', 'visible': true, 'size': 'full'},
      ],
    });
    await tester.pumpWidget(_todayApp(hidden));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-card-plugin:demo:garbage')), findsNothing);
    expect(find.byKey(const Key('today-tasks')), findsOneWidget);

    await tester.pumpWidget(_todayApp(_backend()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-tasks')), findsOneWidget);
    expect(find.textContaining('plugin-card'), findsNothing);
  });

  testWidgets('the layout editor lists plugin cards by title and saves their ids', (tester) async {
    await setScreenSize(tester, const Size(420, 2600));
    final b = _backend(pluginCards: [_cardJson]);
    await tester.pumpWidget(_todayApp(b));
    await tester.pumpAndSettle();
    final element = tester.element(find.byType(TodayScreen));
    Navigator.of(element).push(MaterialPageRoute<void>(builder: (_) => const TodayLayoutEditor()));
    await tester.pumpAndSettle();
    expect(find.text('Müllabfuhr'), findsWidgets);
    expect(find.text('Vom Plugin Demo'), findsOneWidget);
    await tester.tap(find.byKey(const Key('layout-visible-plugin:demo:garbage')));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const Key('today-layout-save')));
    await tester.tap(find.byKey(const Key('today-layout-save')));
    await tester.pumpAndSettle();
    final saved = bodyOf(b.sent('PUT', '/api/me/today-layout').single)['cards'] as List;
    final card = saved.cast<Map>().firstWhere((c) => c['id'] == 'plugin:demo:garbage');
    expect(card['visible'], isFalse);
    final ids = [for (final c in saved.cast<Map>()) c['id']];
    expect(ids.indexOf('plugin:demo:garbage'), greaterThan(ids.indexOf('timetable')),
        reason: 'a new card starts after the built-in ones');
  });

  // ── Reward actions ──────────────────────────────────────────────────────

  FakeBackend parent({List<Object> choices = const [], Map<String, dynamic>? action, Object? approve}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', {'id': 1, 'username': 'mia', 'role': 'partner', 'is_admin': false});
    b.json('GET', '/api/stars/me', {'enabled': true, 'balance': 0, 'reserved': 0, 'available': 0,
        'next_reward': null, 'pending': {'requests': 1, 'awards': 0, 'total': 1}});
    b.json('GET', '/api/stars/rewards', {'items': [
      {'id': 1, 'title': 'Tablet-Zeit', 'price': 10, 'active': true, if (action != null) 'action': action},
    ]});
    b.json('GET', '/api/stars/settings', {'confirm_tasks': false});
    b.json('GET', '/api/stars/pending', {
      'requests': [{'id': 7, 'user_id': 3, 'user_name': 'Kim', 'title': 'Tablet-Zeit', 'price': 10, 'status': 'pending'}],
      'awards': [],
    });
    b.json('GET', '/api/stars/people', {'items': []});
    b.json('GET', '/api/stars/reward-actions', {'items': choices});
    b.json('POST', '/api/stars/rewards', {'id': 2});
    b.json('PATCH', '/api/stars/rewards/1', {'id': 1});
    b.json('POST', '/api/stars/requests/7/approve', approve ?? {'id': 7, 'status': 'approved'});
    return b;
  }

  const unlock = {
    'plugin': 'kidsync', 'plugin_name': 'Kid sync', 'id': 'unlock', 'label': 'Tablet freischalten',
    'params': [
      {'key': 'minutes', 'label': 'Minuten', 'type': 'number', 'required': true},
      {'key': 'device', 'label': 'Gerät', 'type': 'select', 'required': true, 'default': 'tab',
        'options': [{'value': 'tab', 'label': 'Tablet'}, {'value': 'tv', 'label': 'Fernseher'}]},
      {'key': 'note', 'label': 'Notiz', 'type': 'text', 'required': false},
    ],
  };

  testWidgets('a parent attaches a plugin action with its parameters to a new reward', (tester) async {
    await setScreenSize(tester, const Size(420, 2000));
    final b = parent(choices: [unlock]);
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('reward-add')));
    await tester.tap(find.byKey(const Key('reward-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('reward-title')), 'Mehr Tablet');
    await tester.enterText(find.byKey(const Key('reward-price')), '20');
    await tester.tap(find.byKey(const Key('reward-action')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tablet freischalten · Kid sync').last);
    await tester.pumpAndSettle();

    // a required parameter is missing: nothing is sent
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('reward-action-error')), findsOneWidget);
    expect(b.sent('POST', '/api/stars/rewards'), isEmpty);

    await tester.enterText(find.byKey(const Key('reward-param-minutes')), '30');
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/stars/rewards').single), {
      'title': 'Mehr Tablet',
      'price': 20,
      'action': {'plugin': 'kidsync', 'action': 'unlock', 'params': {'minutes': '30', 'device': 'tab'}},
    });
  });

  testWidgets('without plugin actions the reward form has no action field', (tester) async {
    await setScreenSize(tester, const Size(420, 2000));
    final b = parent();
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('reward-add')));
    await tester.tap(find.byKey(const Key('reward-add')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('reward-action')), findsNothing);
    await tester.enterText(find.byKey(const Key('reward-title')), 'Eis');
    await tester.enterText(find.byKey(const Key('reward-price')), '5');
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/stars/rewards').single), {'title': 'Eis', 'price': 5});
  });

  testWidgets('editing keeps the action unless the parent changes it, and can remove it', (tester) async {
    await setScreenSize(tester, const Size(420, 2000));
    final current = {
      'plugin': 'kidsync', 'action': 'unlock', 'label': 'Tablet freischalten', 'plugin_name': 'Kid sync',
      'available': true, 'params': {'minutes': '30', 'device': 'tv'},
    };
    final b = parent(choices: [unlock], action: current);
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('reward-1')));
    await tester.tap(find.byKey(const Key('reward-1')));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byKey(const Key('reward-param-minutes'))).controller!.text, '30');
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/stars/rewards/1').single).containsKey('action'), isFalse,
        reason: 'untouched: the server keeps the action');

    await tester.ensureVisible(find.byKey(const Key('reward-1')));
    await tester.tap(find.byKey(const Key('reward-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reward-action')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Keine Aktion').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('PATCH', '/api/stars/rewards/1').last);
    expect(body.containsKey('action') && body['action'] == null, isTrue, reason: 'null removes the action');
  });

  testWidgets('an action whose plugin is off is shown as unavailable and left alone', (tester) async {
    await setScreenSize(tester, const Size(420, 2000));
    final b = parent(choices: [], action: {
      'plugin': 'kidsync', 'action': 'unlock', 'label': 'Tablet freischalten', 'plugin_name': 'Kid sync',
      'available': false, 'params': {'minutes': '30'},
    });
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('reward-1')));
    await tester.tap(find.byKey(const Key('reward-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('reward-action-off')), findsOneWidget);
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PATCH', '/api/stars/rewards/1').single).containsKey('action'), isFalse);
  });

  for (final ok in [true, false]) {
    testWidgets('approving shows what the action did (${ok ? 'worked' : 'failed'}) and the approval stands', (tester) async {
      await setScreenSize(tester, const Size(420, 2000));
      final b = parent(approve: {
        'id': 7, 'status': 'approved',
        'action_result': {'plugin': 'kidsync', 'action': 'unlock', 'ok': ok, 'message': ok ? 'Tablet frei' : 'Tablet offline'},
      });
      await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.descendant(of: find.byKey(const Key('decide-request-7')), matching: find.text('Bewilligen')));
      await tester.pump();
      await tester.pump();
      expect(b.sent('POST', '/api/stars/requests/7/approve'), hasLength(1));
      expect(find.text(ok ? 'Bewilligt. Aktion ausgeführt: Tablet frei' : 'Bewilligt, aber die Aktion ist fehlgeschlagen: Tablet offline'),
          findsOneWidget);
    });
  }

  // ── Install flow: credentials and connection test ───────────────────────

  Map<String, dynamic> preview({Map<String, dynamic>? installed}) => {
        'url': 'https://github.com/acme/demo',
        'repo': {'url': 'https://github.com/acme/demo', 'owner': 'acme', 'repo': 'demo', 'folder': ''},
        'sha': 'a' * 40,
        'short_sha': 'aaaaaaa',
        'manifest': {
          'id': 'demo_hub', 'name': 'Demo-Plugin', 'version': '1.1.0', 'description': 'Zeigt ein Beispiel',
          'author': 'Acme', 'homepage': '', 'license': 'MIT', 'min_hub_version': '', 'hosts': ['demo.example.org'],
          'capabilities': [],
        },
        'settings': [
          {'key': 'DEMO_HUB_URL', 'label': 'Adresse', 'help': '', 'type': 'url', 'secret': false, 'required': true,
            'default': null, 'example': '', 'is_set': false, 'value': ''},
          {'key': 'DEMO_HUB_TOKEN', 'label': 'Token', 'help': '', 'type': 'password', 'secret': true,
            'required': true, 'default': null, 'example': '', 'is_set': installed != null, 'value': ''},
        ],
        'installed': installed,
        'warnings': <String>[],
        'install_enabled': true,
      };

  FakeBackend installBackend({Map<String, dynamic>? installed, Map<String, dynamic>? testResult}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/admin/settings', []);
    b.json('GET', '/api/plugins/installed', {'enabled': true, 'persistent': true, 'items': []});
    b.json('POST', '/api/plugins/inspect', preview(installed: installed));
    b.json('POST', '/api/plugins/install', {
      'id': 'demo_hub', 'version': '1.1.0', 'sha': 'a' * 40, 'updated': installed != null, 'restart_required': false,
      'active': true, 'connection_test': testResult,
      'plugin': {'id': 'demo_hub', 'name': 'Demo-Plugin', 'version': '1.1.0'},
    });
    b.json('POST', '/api/admin/plugins/demo_hub/test', {'ok': false, 'level': 'error', 'message': 'Token abgelehnt'});
    return b;
  }

  Future<void> toForm(WidgetTester tester) async {
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('plugin-continue')));
    await tester.pumpAndSettle();
  }

  testWidgets('install asks for the address and the secret, then shows the plugin\'s connection test', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = installBackend(testResult: {'ok': true, 'level': 'ok', 'message': 'Verbunden, Token gültig'});
    await tester.pumpWidget(appWith(b.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await toForm(tester);
    expect(find.byKey(const Key('plugin-form')), findsOneWidget);
    final secret = find.descendant(of: find.byKey(const Key('plugin-field-DEMO_HUB_TOKEN')), matching: find.byType(EditableText));
    expect(tester.widget<EditableText>(secret).obscureText, isTrue);
    expect(find.byKey(const Key('plugin-test')), findsNothing, reason: 'a new plugin is tested right after installing');

    // required values are asked for before anything is sent
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.text('Pflichtfeld'), findsWidgets);
    expect(b.sent('POST', '/api/plugins/install'), isEmpty);

    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'https://demo.example.org');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_TOKEN')), 'geheim-123');
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/plugins/install').single)['settings'],
        {'DEMO_HUB_URL': 'https://demo.example.org', 'DEMO_HUB_TOKEN': 'geheim-123'});
    expect(find.byKey(const Key('plugin-result')), findsOneWidget);
    expect(find.byKey(const Key('plugin-test-result')), findsOneWidget);
    expect(find.text('Verbunden, Token gültig'), findsOneWidget);
    expect(find.byKey(const Key('plugin-test-hint')), findsNothing);
  });

  testWidgets('a failing connection test is shown, with a hint where to fix it', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = installBackend(testResult: {'ok': false, 'level': 'error', 'message': 'Token abgelehnt'});
    await tester.pumpWidget(appWith(b.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await toForm(tester);
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'https://demo.example.org');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_TOKEN')), 'falsch');
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.text('Token abgelehnt'), findsOneWidget);
    expect(find.byKey(const Key('plugin-test-hint')), findsOneWidget);
  });

  testWidgets('a plugin without its own test shows no test result', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = installBackend();
    await tester.pumpWidget(appWith(b.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await toForm(tester);
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'https://demo.example.org');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_TOKEN')), 'x');
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-result')), findsOneWidget);
    expect(find.byKey(const Key('plugin-test-result')), findsNothing);
  });

  testWidgets('updating an installed plugin: test the entered values before installing, empty secret keeps the stored one',
      (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = installBackend(installed: {'version': '1.0.0', 'sha': 'b' * 40, 'short_sha': 'bbbbbbb', 'same_sha': false});
    await tester.pumpWidget(appWith(b.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await toForm(tester);
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'https://neu.example.org');
    await tester.ensureVisible(find.byKey(const Key('plugin-test')));
    await tester.tap(find.byKey(const Key('plugin-test')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/admin/plugins/demo_hub/test').single),
        {'values': {'DEMO_HUB_URL': 'https://neu.example.org', 'DEMO_HUB_TOKEN': ''}});
    expect(find.text('Token abgelehnt'), findsOneWidget);
    expect(b.sent('POST', '/api/plugins/install'), isEmpty, reason: 'testing installs nothing');
  });
}
