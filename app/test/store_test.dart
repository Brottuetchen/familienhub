import 'package:familienhub/l10n/l10n.dart';
import 'package:familienhub/models/store.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/admin/store_detail_screen.dart';
import 'package:familienhub/screens/admin/store_screen.dart';
import 'package:familienhub/screens/admin/store_sources_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

const _sha1 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha2 = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, dynamic> _item({
  String type = 'plugin',
  String id = 'demo_hub',
  String name = 'Demo-Plugin',
  String summary = 'Zeigt ein Beispiel',
  String source = 'official',
  bool verified = true,
  String state = 'available',
  String? installedVersion,
  String version = '1.0.0',
  String sha = _sha1,
  List<String> tags = const ['demo'],
}) =>
    {
      'source': source, 'verified': verified, 'type': type, 'id': id, 'name': name, 'summary': summary,
      'description': 'Eine längere Beschreibung von $name.', 'author': 'Acme', 'repo': 'https://github.com/acme/$id',
      'path': '', 'version': version, 'sha': sha, 'short_sha': sha.substring(0, 7), 'tags': tags,
      'min_hub_version': '', 'compatible': true,
      'screenshots': ['/api/admin/store/screenshot/$source/$type/$id/0', '/api/admin/store/screenshot/$source/$type/$id/1'],
      'state': state, 'installed_version': installedVersion,
    };

Map<String, dynamic> _source({String id = 'official', bool verified = true, String status = 'ok', int entries = 2}) => {
      'id': id, 'name': verified ? 'Familienhub' : 'Meine Extras', 'url': 'https://github.com/mine/extras',
      'verified': verified, 'removable': !verified, 'status': status, 'stale': false, 'entries': entries, 'skipped': [],
    };

Map<String, dynamic> _listing(List<Map<String, dynamic>> items, {List<Map<String, dynamic>>? sources}) =>
    {'installer_enabled': true, 'sources': sources ?? [_source()], 'items': items};

final _plugin = _item();
final _theme = _item(type: 'theme', id: 'waldgruen', name: 'Waldgrün', summary: 'Grüne Farben', tags: ['natur']);

Map<String, dynamic> _pluginPreview() => {
      'type': 'plugin', 'source': 'official', 'verified': true, 'sha': _sha1, 'short_sha': 'aaaaaaa',
      'url': 'https://github.com/acme/demo_hub',
      'repo': {'url': 'https://github.com/acme/demo_hub', 'owner': 'acme', 'repo': 'demo_hub', 'folder': ''},
      'manifest': {
        'id': 'demo_hub', 'name': 'Demo-Plugin', 'version': '1.0.0', 'description': 'Zeigt ein Beispiel',
        'author': 'Acme', 'homepage': '', 'license': 'MIT', 'min_hub_version': '', 'hosts': ['demo.example.org'],
        'capabilities': [
          {'id': 'documents', 'label': 'Dokumente (Paperless)'}
        ],
      },
      'settings': <Map<String, dynamic>>[],
      'installed': null, 'warnings': <String>[], 'install_enabled': true,
    };

FakeBackend _backend(Map<String, dynamic> listing) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/admin/store', listing);
  b.json('POST', '/api/admin/store/inspect', _pluginPreview());
  return b;
}

Widget _app(FakeBackend backend, Widget child, {double scale = 1.0}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(backend.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        builder: (context, w) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: w!),
        home: child,
      ),
    );

Future<void> _openDetail(WidgetTester tester, FakeBackend backend, Map<String, dynamic> item) async {
  await tester.pumpWidget(_app(backend, StoreDetailScreen(item: StoreItem.fromJson(item))));
  await tester.pumpAndSettle();
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Store list shows cards with badges and loads screenshots through the hub', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final backend = _backend(_listing([
      _plugin,
      _theme,
      _item(id: 'mine_x', name: 'Eigenes', source: 'custom-1', verified: false),
    ], sources: [
      _source(),
      _source(id: 'custom-1', verified: false, entries: 1)
    ]));
    await tester.pumpWidget(_app(backend, const StoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-item-official/plugin/demo_hub')), findsOneWidget);
    expect(find.byKey(const Key('store-item-official/theme/waldgruen')), findsOneWidget);
    expect(find.text('Demo-Plugin'), findsOneWidget);
    expect(find.text('von Acme'), findsNWidgets(3));
    expect(find.byKey(const Key('store-badge-verified')), findsNWidgets(2));
    expect(find.byKey(const Key('store-badge-unverified')), findsOneWidget);
    expect(find.text('Theme'), findsOneWidget);
    // Screenshots come from the hub (never from GitHub directly)
    final shots = backend.requests.where((r) => r.url.path.startsWith('/api/admin/store/screenshot/')).toList();
    expect(shots, isNotEmpty);
    expect(backend.requests.every((r) => r.url.host == 'hub.test'), isTrue);
  });

  testWidgets('Filter by type and search', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final backend = _backend(_listing([_plugin, _theme]));
    await tester.pumpWidget(_app(backend, const StoreScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('store-filter-themes')));
    await tester.pumpAndSettle();
    expect(find.text('Waldgrün'), findsOneWidget);
    expect(find.text('Demo-Plugin'), findsNothing);
    await tester.tap(find.byKey(const Key('store-filter-plugins')));
    await tester.pumpAndSettle();
    expect(find.text('Waldgrün'), findsNothing);
    expect(find.text('Demo-Plugin'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-filter-all')));
    await tester.enterText(find.byKey(const Key('store-search')), 'natur'); // tag
    await tester.pumpAndSettle();
    expect(find.text('Waldgrün'), findsOneWidget);
    expect(find.text('Demo-Plugin'), findsNothing);
    await tester.enterText(find.byKey(const Key('store-search')), 'nichts dergleichen');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-empty')), findsOneWidget);
    expect(find.text('Keine passenden Einträge'), findsOneWidget);
  });

  test('filterStore matches name, summary, author and tags case-insensitively', () {
    final items = [StoreItem.fromJson(_plugin), StoreItem.fromJson(_theme)];
    expect(filterStore(items, StoreFilter.all, 'ACME').length, 2);
    expect(filterStore(items, StoreFilter.themes, '').single.id, 'waldgruen');
    expect(filterStore(items, StoreFilter.plugins, 'beispiel').single.id, 'demo_hub');
  });

  testWidgets('Unreachable store shows a soft status, not an error', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = _backend(_listing([], sources: [_source(status: 'unreachable', entries: 0)]));
    await tester.pumpWidget(_app(backend, const StoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-status-official')), findsOneWidget);
    expect(find.textContaining('gerade nicht erreichbar'), findsOneWidget);
    expect(find.text('Im Store gibt es noch keine Einträge'), findsOneWidget);
    expect(find.text(l10n.retry), findsNothing); // no error page
  });

  testWidgets('Plugin detail: requirements, full-access warning, install via review at the pinned commit',
      (tester) async {
    await setScreenSize(tester, const Size(420, 2600));
    final backend = _backend(_listing([_plugin]));
    backend.json('POST', '/api/admin/store/install',
        {'id': 'demo_hub', 'version': '1.0.0', 'sha': _sha1, 'updated': false, 'active': true, 'type': 'plugin'});
    await _openDetail(tester, backend, _plugin);
    expect(find.byKey(const Key('store-detail-name')), findsOneWidget);
    expect(find.byKey(const Key('store-carousel')), findsOneWidget);
    expect(find.byKey(const Key('store-plugin-warning')), findsOneWidget);
    expect(find.text('demo.example.org'), findsOneWidget);
    expect(find.text('Dokumente (Paperless)'), findsOneWidget);
    expect(find.text('Version 1.0.0 · Commit aaaaaaa'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-action')));
    await tester.pumpAndSettle();
    // The plugin review screen with the trust checkbox
    expect(find.byKey(const Key('plugin-review')), findsOneWidget);
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-continue')));
    await tester.pumpAndSettle();
    final sent = backend.sent('POST', '/api/admin/store/install');
    expect(sent, hasLength(1));
    expect(bodyOf(sent.single), {
      'source': 'official', 'type': 'plugin', 'id': 'demo_hub', 'sha': _sha1, 'settings': <String, dynamic>{},
      'acknowledge_unverified': false,
    });
    await tester.tap(find.byKey(const Key('plugin-done')));
    await tester.pumpAndSettle();
    expect(find.text('Installiert'), findsWidgets);
    expect(tester.widget<FilledButton>(find.byKey(const Key('store-action'))).onPressed, isNull);
  });

  testWidgets('Theme detail installs directly with the pinned commit', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final backend = _backend(_listing([_theme]));
    backend.json('POST', '/api/admin/store/inspect', {
      'type': 'theme', 'sha': _sha1,
      'theme': {
        'name': 'Waldgrün',
        'colors': {'primary': '#2E7D32', 'secondary': '#A5D6A7', 'background': '#0B1F0E'}
      },
    });
    backend.json('POST', '/api/admin/store/install', {
      'type': 'theme', 'id': 'waldgruen', 'version': '1.0.0', 'sha': _sha1, 'updated': false,
      'theme': {'id': 'custom:1', 'name': 'Waldgrün', 'builtin': false, 'colors': {}},
    });
    await _openDetail(tester, backend, _theme);
    expect(find.byKey(const Key('store-plugin-warning')), findsNothing);
    expect(find.text('Farben'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-action')));
    await tester.pumpAndSettle();
    final sent = backend.sent('POST', '/api/admin/store/install').single;
    expect(bodyOf(sent)['sha'], _sha1);
    expect(bodyOf(sent)['type'], 'theme');
    expect(find.text('Theme „Waldgrün“ installiert'), findsOneWidget);
  });

  testWidgets('Update available: badge in the list, update button and note on the detail page', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final updatable = _item(state: 'update', installedVersion: '1.0.0', version: '2.0.0', sha: _sha2);
    final backend = _backend(_listing([updatable]));
    await tester.pumpWidget(_app(backend, const StoreScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-badge-update')), findsOneWidget);
    expect(find.text('Update verfügbar'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-item-official/plugin/demo_hub')));
    await tester.pumpAndSettle();
    expect(find.text('Installiert: 1.0.0 · neu: 2.0.0'), findsOneWidget);
    expect(find.text('Aktualisieren'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('store-action'))).onPressed, isNotNull);
  });

  testWidgets('Unverified entry: warning on the page and a dialog before installing', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final custom = _item(type: 'theme', id: 'bunt', name: 'Bunt', source: 'custom-1', verified: false);
    final backend = _backend(_listing([custom]));
    backend.json('POST', '/api/admin/store/inspect', {'type': 'theme', 'theme': {'colors': {}}});
    backend.json('POST', '/api/admin/store/install',
        {'type': 'theme', 'id': 'bunt', 'updated': false, 'theme': {'name': 'Bunt'}});
    await _openDetail(tester, backend, custom);
    expect(find.byKey(const Key('store-unverified-warning')), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-action')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-unverified-dialog')), findsOneWidget);
    await tester.tap(find.text(l10n.cancel));
    await tester.pumpAndSettle();
    expect(backend.sent('POST', '/api/admin/store/install'), isEmpty);
    await tester.tap(find.byKey(const Key('store-action')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('store-unverified-confirm')));
    await tester.pumpAndSettle();
    final sent = backend.sent('POST', '/api/admin/store/install').single;
    expect(bodyOf(sent)['acknowledge_unverified'], isTrue);
    expect(bodyOf(sent)['source'], 'custom-1');
  });

  testWidgets('Adding a custom source needs the warning acknowledged', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = _backend(_listing([], sources: [_source()]));
    backend.json('POST', '/api/admin/store/sources', _source(id: 'custom-1', verified: false), status: 201);
    await tester.pumpWidget(_app(backend, const StoreSourcesScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Offizieller Store'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-source-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('store-source-url')), 'https://github.com/mine/extras');
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(find.byKey(const Key('store-source-save'))).onPressed, isNull);
    expect(find.text('Nicht geprüfte Quelle'), findsOneWidget);
    await tester.tap(find.byKey(const Key('store-source-understand')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('store-source-save')));
    await tester.pumpAndSettle();
    final sent = backend.sent('POST', '/api/admin/store/sources').single;
    expect(bodyOf(sent), {'url': 'https://github.com/mine/extras', 'acknowledge': true});
  });

  testWidgets('Removing a custom source asks first', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final backend = _backend(_listing([], sources: [_source(), _source(id: 'custom-3', verified: false)]));
    backend.json('DELETE', '/api/admin/store/sources/3', {'deleted': true});
    await tester.pumpWidget(_app(backend, const StoreSourcesScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('store-source-remove-official')), findsNothing);
    await tester.tap(find.byKey(const Key('store-source-remove-custom-3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('store-source-remove-confirm')));
    await tester.pumpAndSettle();
    expect(backend.sent('DELETE', '/api/admin/store/sources/3'), hasLength(1));
  });

  testWidgets('No overflow at text scale 2.0 on a 360 dp phone (list and detail)', (tester) async {
    await setScreenSize(tester, const Size(360, 740));
    final backend = _backend(_listing([
      _item(state: 'update', installedVersion: '1.0.0', version: '2.0.0', sha: _sha2),
      _item(type: 'theme', id: 'lang', name: 'Ein sehr langer Theme-Name, der umbrechen muss', source: 'custom-1',
          verified: false, state: 'installed'),
    ], sources: [
      _source(),
      _source(id: 'custom-1', verified: false, status: 'unreachable')
    ]));
    await tester.pumpWidget(_app(backend, const StoreScreen(), scale: 2.0));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -2000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(_app(backend,
        StoreDetailScreen(item: StoreItem.fromJson(_item(state: 'update', installedVersion: '1.0.0', sha: _sha2))),
        scale: 2.0));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.drag(find.byType(ListView).first, const Offset(0, -3000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('English texts', (tester) async {
    setAppLanguage('en');
    addTearDown(() => setAppLanguage('de'));
    await setScreenSize(tester, const Size(420, 2400));
    final backend = _backend(_listing([_item(state: 'update', installedVersion: '1.0.0', version: '2.0.0')]));
    await tester.pumpWidget(_app(backend, const StoreScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Update available'), findsOneWidget);
    expect(find.text('Reviewed'), findsOneWidget);
    expect(find.text('All'), findsOneWidget);
  });
}

