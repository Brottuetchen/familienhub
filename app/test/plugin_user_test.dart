// Personal plugin settings (More → My connections) and plugin pages (More, notification route).
import 'package:familienhub/models/plugin_user.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/main_shell.dart';
import 'package:familienhub/screens/more/connections_screen.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:familienhub/screens/more/plugin_pages.dart';
import 'package:familienhub/screens/more/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

Map<String, dynamic> _form({bool tokenSet = false, String user = ''}) => {
      'id': 'recap',
      'name': 'Rückblick',
      'description': 'Dein monatlicher Rückblick',
      'has_test': true,
      'fields': [
        {
          'key': 'RECAP_USER', 'label': 'Benutzer', 'help': 'Dein Name dort', 'type': 'text', 'secret': false,
          'required': true, 'default': null, 'example': '', 'value': user, 'is_set': user.isNotEmpty,
        },
        {
          'key': 'RECAP_TOKEN', 'label': 'Zugangsschlüssel', 'help': '', 'type': 'password', 'secret': true,
          'required': true, 'default': null, 'example': '', 'value': '', 'is_set': tokenSet,
        },
        {
          'key': 'RECAP_DAYS', 'label': 'Tage', 'help': '', 'type': 'number', 'secret': false, 'required': false,
          'default': '30', 'example': '', 'value': '30', 'is_set': false,
        },
        {
          'key': 'RECAP_FLAG', 'label': 'Schalter', 'help': '', 'type': 'bool', 'secret': false, 'required': false,
          'default': null, 'example': '', 'value': 'false', 'is_set': false,
        },
      ],
    };

const _pages = {
  'items': [
    {'plugin': 'recap', 'plugin_name': 'Rückblick', 'id': 'monthly', 'title': 'Monatsrückblick', 'icon': 'star'},
  ]
};

FakeBackend _backend({bool tokenSet = false, String user = '', bool withPages = true}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/plugins/personal-settings', {'items': [_form(tokenSet: tokenSet, user: user)]});
  b.json('GET', '/api/plugin-pages', withPages ? _pages : {'items': []});
  b.json('POST', '/api/plugin-pages/recap/monthly/link', {'url': '/plugin-pages/TOKEN/', 'expires_in': 900});
  return b;
}

Widget _app(FakeBackend b, Widget home, {List<Uri>? opened}) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(b.api()),
        inAppPluginPagesProvider.overrideWithValue(false), // these tests cover the external opener
        pageOpenerProvider.overrideWithValue((uri) async {
          opened?.add(uri);
          return true;
        }),
      ],
      child: MaterialApp(locale: const Locale('de', 'DE'), home: home),
    );

void main() {
  setUp(setUpTestEnv);

  test('personal plugins and pages parse, garbage is dropped', () {
    final plugins = PersonalPlugin.listFromJson({
      'items': [_form(), 'junk', {'name': 'no id'}]
    });
    expect(plugins, hasLength(1));
    expect(plugins.first.hasTest, isTrue);
    expect(plugins.first.fields.map((f) => f.key), ['RECAP_USER', 'RECAP_TOKEN', 'RECAP_DAYS', 'RECAP_FLAG']);
    expect(plugins.first.needsSetup, isTrue);
    expect(PersonalPlugin.fromJson(_form(tokenSet: true, user: 'anna')).needsSetup, isFalse);
    expect(PersonalPlugin.listFromJson(null), isEmpty);
    final pages = PluginPageInfo.listFromJson(_pages);
    expect(pages.single.title, 'Monatsrückblick');
    expect(pages.single.icon, 'star');
    expect(PluginPageInfo.listFromJson({'items': [{'plugin': 'x'}]}), isEmpty);
  });

  test('a notification route to a plugin page is recognised', () {
    expect(pluginPageFromRoute('/plugin-page/recap/monthly'), const PluginPageRequest('recap', 'monthly'));
    expect(pluginPageFromRoute('/plugin-page/recap/monthly?path=2026-10%2Findex.html'),
        const PluginPageRequest('recap', 'monthly', '2026-10/index.html'));
    expect(pluginPageFromRoute('/shopping'), isNull);
    expect(pluginPageFromRoute('/plugin-page/recap'), isNull);
    expect(pluginPageFromRoute('/plugin-page/a/b/c'), isNull);
  });

  testWidgets('My connections lists the plugin and shows whether it is set up', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    await tester.pumpWidget(_app(_backend(), const ConnectionsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Rückblick'), findsOneWidget);
    expect(find.text('Noch nicht eingerichtet'), findsOneWidget);
  });

  testWidgets('without personal plugins the screen says so', (tester) async {
    final b = _backend();
    b.json('GET', '/api/plugins/personal-settings', {'items': []});
    await tester.pumpWidget(_app(b, const ConnectionsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('connections-empty')), findsOneWidget);
  });

  testWidgets('the form is rendered from the manifest and saves what was typed', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend(tokenSet: true, user: 'anna');
    b.json('PUT', '/api/plugins/recap/personal-settings', _form(tokenSet: true, user: 'anna2'));
    await tester.pumpWidget(_app(b, const ConnectionsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Eingerichtet'), findsOneWidget);
    await tester.tap(find.byKey(const Key('connection-recap')));
    await tester.pumpAndSettle();
    // all four widgets, the secret is empty and says it is kept
    expect(find.byKey(const Key('field-RECAP_USER')), findsOneWidget);
    expect(find.byKey(const Key('field-RECAP_FLAG')), findsOneWidget);
    expect(find.byType(SwitchListTile), findsOneWidget);
    expect(find.text('Gespeichert – leer lassen, um es zu behalten'), findsOneWidget);
    final secret = tester.widget<TextField>(find.descendant(of: find.byKey(const Key('field-RECAP_TOKEN')), matching: find.byType(TextField)));
    expect(secret.obscureText, isTrue);
    expect(secret.controller!.text, '');
    await tester.enterText(find.byKey(const Key('field-RECAP_USER')), 'anna2');
    await tester.tap(find.byType(SwitchListTile));
    await tester.pump();
    await tester.tap(find.byKey(const Key('connection-save')));
    await tester.pumpAndSettle();
    final sent = bodyOf(b.sent('PUT', '/api/plugins/recap/personal-settings').single)['values'] as Map;
    expect(sent, {'RECAP_USER': 'anna2', 'RECAP_TOKEN': '', 'RECAP_DAYS': '30', 'RECAP_FLAG': 'true'});
    expect(find.byKey(const Key('connection-save')), findsNothing); // went back
  });

  testWidgets('required and mistyped values are refused before anything is sent', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend();
    await tester.pumpWidget(_app(b, PersonalSettingsScreen(plugin: PersonalPlugin.fromJson(_form()))));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('field-RECAP_DAYS')), 'viele');
    await tester.tap(find.byKey(const Key('connection-save')));
    await tester.pumpAndSettle();
    expect(find.text('Pflichtfeld'), findsNWidgets(2)); // user and token
    expect(find.text('Bitte eine Zahl'), findsOneWidget);
    expect(b.sent('PUT', '/api/plugins/recap/personal-settings'), isEmpty);
  });

  testWidgets('the connection test sends the typed values and shows the result', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _backend();
    b.json('POST', '/api/plugins/recap/personal-settings/test', {'ok': true, 'level': 'ok', 'message': 'Verbunden als anna'});
    await tester.pumpWidget(_app(b, PersonalSettingsScreen(plugin: PersonalPlugin.fromJson(_form()))));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('field-RECAP_USER')), 'anna');
    await tester.tap(find.byKey(const Key('connection-test')));
    await tester.pumpAndSettle();
    expect(find.text('Verbunden als anna'), findsOneWidget);
    final sent = bodyOf(b.sent('POST', '/api/plugins/recap/personal-settings/test').single)['values'] as Map;
    expect(sent['RECAP_USER'], 'anna');
  });

  testWidgets('More lists plugin pages and My connections', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(_app(_backend(), const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-page-recap-monthly')), findsOneWidget);
    expect(find.text('Monatsrückblick'), findsOneWidget);
    expect(find.byKey(const Key('more-connections')), findsNothing, reason: 'moved to Settings');
  });

  testWidgets('Settings lists My connections', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(_app(_backend(), const SettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-connections')), findsOneWidget);
  });

  testWidgets('More shows nothing extra without pages and personal settings', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend(withPages: false);
    b.json('GET', '/api/plugins/personal-settings', {'items': []});
    await tester.pumpWidget(_app(b, const SettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-connections')), findsNothing);
    await tester.pumpWidget(_app(b, const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Seiten von Plugins'), findsNothing);
  });

  testWidgets('More still works when an older server does not know the new endpoints', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = FakeBackend();
    addDefaults(b);
    await tester.pumpWidget(_app(b, const SettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('more-connections')), findsNothing);
    await tester.pumpWidget(_app(b, const MoreScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Mehr'), findsOneWidget);
  });

  testWidgets('tapping a page asks for a fresh link and opens it with the hub address', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    final opened = <Uri>[];
    await tester.pumpWidget(_app(b, const MoreScreen(), opened: opened));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-page-recap-monthly')));
    await tester.pumpAndSettle();
    expect(opened, [Uri.parse('https://hub.test/plugin-pages/TOKEN/')]);
    expect(bodyOf(b.sent('POST', '/api/plugin-pages/recap/monthly/link').single), {'path': ''});
    await tester.tap(find.byKey(const Key('more-page-recap-monthly')));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), hasLength(2)); // every tap gets a new link
  });

  testWidgets('a failing link request is shown, nothing is opened', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('POST', '/api/plugin-pages/recap/monthly/link', {'detail': 'Seite nicht gefunden'}, status: 404);
    final opened = <Uri>[];
    await tester.pumpWidget(_app(b, const MoreScreen(), opened: opened));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-page-recap-monthly')));
    await tester.pumpAndSettle();
    expect(opened, isEmpty);
    expect(find.textContaining('Seite nicht gefunden'), findsOneWidget);
  });

  testWidgets('the notification route /plugin-page/<plugin>/<page>?path= opens the page', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final b = _backend();
    final opened = <Uri>[];
    late WidgetRef captured;
    await tester.pumpWidget(_app(
        b,
        Consumer(builder: (context, ref, _) {
          captured = ref;
          return const MainShell(startPush: false);
        }),
        opened: opened));
    await tester.pumpAndSettle();
    openRoute(captured, '/plugin-page/recap/monthly?path=2026-10');
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/plugin-pages/recap/monthly/link').single), {'path': '2026-10'});
    expect(opened, [Uri.parse('https://hub.test/plugin-pages/TOKEN/')]);
    // the request was consumed, a second identical notification opens it again
    openRoute(captured, '/plugin-page/recap/monthly?path=2026-10');
    await tester.pumpAndSettle();
    expect(opened, hasLength(2));
  });

  testWidgets('a route that was set before the main screen existed is picked up at start', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final b = _backend();
    final opened = <Uri>[];
    final container = ProviderContainer(overrides: [
      apiClientProvider.overrideWithValue(b.api()),
      inAppPluginPagesProvider.overrideWithValue(false),
      pageOpenerProvider.overrideWithValue((uri) async {
        opened.add(uri);
        return true;
      }),
    ]);
    addTearDown(container.dispose);
    container.read(pluginPageRequestProvider.notifier).state = const PluginPageRequest('recap', 'monthly');
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(locale: Locale('de', 'DE'), home: MainShell(startPush: false))));
    await tester.pumpAndSettle();
    expect(opened, hasLength(1));
    expect(container.read(pluginPageRequestProvider), isNull);
  });
}
