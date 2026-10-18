import 'package:familienhub/l10n/l10n.dart';
import 'package:familienhub/models/plugin_install.dart';
import 'package:familienhub/screens/more/plugin_install_screen.dart';
import 'package:familienhub/screens/more/plugins_admin_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

Map<String, dynamic> _preview({Map<String, dynamic>? installed, bool setSecret = false}) => {
      'url': 'https://github.com/acme/demo',
      'repo': {'url': 'https://github.com/acme/demo', 'owner': 'acme', 'repo': 'demo', 'folder': ''},
      'sha': _sha,
      'short_sha': 'aaaaaaa',
      'manifest': {
        'id': 'demo_hub',
        'name': 'Demo-Plugin',
        'version': '1.1.0',
        'description': 'Zeigt ein Beispiel',
        'author': 'Acme',
        'homepage': 'https://github.com/acme/demo',
        'license': 'MIT',
        'min_hub_version': '',
        'hosts': ['demo.example.org'],
        'capabilities': [
          {'id': 'documents', 'label': 'Dokumente (Paperless)'}
        ],
      },
      'settings': [
        {
          'key': 'DEMO_HUB_URL', 'label': 'Adresse', 'help': '', 'type': 'url', 'secret': false, 'required': true,
          'default': null, 'example': 'https://demo.example.org', 'is_set': setSecret, 'value': setSecret ? 'https://alt.example.org' : '',
        },
        {
          'key': 'DEMO_HUB_TOKEN', 'label': 'Token', 'help': 'Aus den Demo-Einstellungen', 'type': 'password',
          'secret': true, 'required': true, 'default': null, 'example': '', 'is_set': setSecret, 'value': '',
        },
        {
          'key': 'DEMO_HUB_LIMIT', 'label': 'Limit', 'help': '', 'type': 'number', 'secret': false, 'required': false,
          'default': '5', 'example': '', 'is_set': false, 'value': '',
        },
        {
          'key': 'DEMO_HUB_DEBUG', 'label': 'Debug', 'help': '', 'type': 'bool', 'secret': false, 'required': false,
          'default': null, 'example': '', 'is_set': false, 'value': '',
        },
      ],
      'installed': installed,
      'warnings': <String>[],
      'install_enabled': true,
    };

const _installedJson = {
  'id': 'demo_hub', 'name': 'Demo-Plugin', 'version': '1.0.0', 'short_sha': 'bbbbbbb',
  'repo_url': 'https://github.com/acme/demo', 'enabled': true, 'loaded': true, 'active': true, 'error': null,
};

const _plugin = {
  'id': 'demo_hub', 'name': 'Demo-Plugin', 'description': 'Zeigt ein Beispiel', 'configured': true,
  'disabled': false, 'active': true,
  'fields': [
    {'key': 'DEMO_HUB_URL', 'label': 'Adresse', 'secret': false, 'required': true, 'help': '', 'value': 'https://alt.example.org', 'is_set': true},
  ],
};

FakeBackend _backend({List<Object> installed = const [], bool enabled = true, List<Object> plugins = const []}) {
  final backend = FakeBackend();
  addDefaults(backend);
  backend.json('GET', '/api/admin/settings', plugins);
  backend.json('GET', '/api/plugins/installed', {'enabled': enabled, 'persistent': true, 'items': installed});
  return backend;
}

void main() {
  setUp(setUpTestEnv);

  test('Modelle lesen die Antworten des Servers', () {
    final p = PluginPreview.fromJson(_preview(installed: {'version': '1.0.0', 'sha': 'x', 'short_sha': 'xxxxxxx', 'same_sha': false}));
    expect(p.name, 'Demo-Plugin');
    expect(p.isInstalled && !p.sameSha, isTrue);
    expect(p.capabilities, ['Dokumente (Paperless)']);
    expect(p.settings.map((s) => s.type), ['url', 'password', 'number', 'bool']);
    final state = PluginInstallState.fromJson({'enabled': false, 'items': [_installedJson]});
    expect(state.enabled, isFalse);
    expect(state.byId('demo_hub')!.shortSha, 'bbbbbbb');
    expect(state.byId('gibtsnicht'), isNull);
  });

  testWidgets('Link einfügen, prüfen, bestätigen, Formular aus dem Manifest ausfüllen, installieren', (tester) async {
    await setScreenSize(tester, const Size(420, 2200));
    final backend = _backend(plugins: [_plugin]);
    backend.json('POST', '/api/plugins/inspect', _preview());
    backend.json('POST', '/api/plugins/install', {
      'id': 'demo_hub', 'version': '1.1.0', 'sha': _sha, 'updated': false, 'restart_required': false, 'active': true,
      'plugin': _installedJson,
    });
    await tester.pumpWidget(appWith(backend.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('plugin-install-button')));
    await tester.pumpAndSettle();
    expect(find.text('Plugin installieren'), findsWidgets);
    await tester.enterText(find.byKey(const Key('plugin-url')), ' https://github.com/acme/demo ');
    await tester.tap(find.byKey(const Key('plugin-inspect')));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/plugins/inspect').single), {'url': 'https://github.com/acme/demo'});

    // review: what it is, where it comes from, what it contacts, and the warning
    expect(find.byKey(const Key('plugin-review')), findsOneWidget);
    expect(find.text('Demo-Plugin'), findsOneWidget);
    expect(find.text('von Acme · Version 1.1.0 · Commit aaaaaaa · MIT'), findsOneWidget);
    expect(find.text('Zeigt ein Beispiel'), findsOneWidget);
    expect(find.text('demo.example.org'), findsOneWidget);
    expect(find.text('Dokumente (Paperless)'), findsOneWidget);
    expect(find.text('https://github.com/acme/demo · aaaaaaa'), findsOneWidget);
    expect(find.byKey(const Key('plugin-warning')), findsOneWidget);
    expect(find.text('Nur aus vertrauenswürdigen Quellen'), findsOneWidget);
    // nothing proceeds before the admin confirms the source
    expect(tester.widget<FilledButton>(find.byKey(const Key('plugin-continue'))).onPressed, isNull);
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-continue')));
    await tester.pumpAndSettle();

    // the form: one field per setting, secrets hidden, defaults prefilled
    expect(find.byKey(const Key('plugin-form')), findsOneWidget);
    TextField field(String key) => tester.widget<TextField>(
        find.descendant(of: find.byKey(Key('plugin-field-$key')), matching: find.byType(TextField)));
    expect(field('DEMO_HUB_TOKEN').obscureText, isTrue);
    expect(field('DEMO_HUB_URL').obscureText, isFalse);
    expect(field('DEMO_HUB_LIMIT').controller!.text, '5');
    expect(find.text('Adresse *'), findsOneWidget);
    expect(find.text('Limit'), findsOneWidget);
    expect(find.textContaining('z. B. https://demo.example.org'), findsOneWidget);
    expect(find.textContaining('Aus den Demo-Einstellungen'), findsOneWidget);

    // validation: required, address, number
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.text('Pflichtfeld'), findsNWidgets(2));
    expect(backend.sent('POST', '/api/plugins/install'), isEmpty);
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'ftp://nein');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_TOKEN')), 'tok-123');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_LIMIT')), 'viele');
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.text('Bitte eine Adresse mit http:// oder https://'), findsOneWidget);
    expect(find.text('Bitte eine Zahl'), findsOneWidget);
    expect(backend.sent('POST', '/api/plugins/install'), isEmpty);

    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_URL')), 'https://demo.example.org');
    await tester.enterText(find.byKey(const Key('plugin-field-DEMO_HUB_LIMIT')), '7');
    await tester.tap(find.byKey(const Key('plugin-field-DEMO_HUB_DEBUG')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/plugins/install').single), {
      'url': 'https://github.com/acme/demo',
      'sha': _sha,
      'settings': {
        'DEMO_HUB_URL': 'https://demo.example.org',
        'DEMO_HUB_TOKEN': 'tok-123',
        'DEMO_HUB_LIMIT': '7',
        'DEMO_HUB_DEBUG': 'true',
      },
    });
    expect(find.text('Demo-Plugin ist installiert'), findsOneWidget);
    expect(find.text('Das Plugin ist aktiv.'), findsOneWidget);
    expect(find.byKey(const Key('plugin-restart')), findsNothing);

    await tester.tap(find.byKey(const Key('plugin-done')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-install-button')), findsOneWidget); // back in the list
  });

  testWidgets('Fehler vom Server und Wiederholung; Neustart-Hinweis', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final backend = _backend();
    var calls = 0;
    backend.on('POST', '/api/plugins/inspect', (_) {
      calls++;
      return calls == 1
          ? jsonResponse({'detail': 'Im Repository liegt keine familienhub-plugin.json'}, status: 422)
          : jsonResponse({..._preview(), 'settings': <Object>[]});
    });
    backend.json('POST', '/api/plugins/install', {
      'id': 'demo_hub', 'version': '1.1.0', 'sha': _sha, 'updated': true, 'restart_required': true, 'active': false,
    });
    await tester.pumpWidget(appWith(backend.api(), const PluginInstallScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('plugin-url')), 'https://github.com/acme/demo');
    await tester.tap(find.byKey(const Key('plugin-inspect')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-error')), findsOneWidget);
    expect(find.text('Im Repository liegt keine familienhub-plugin.json'), findsOneWidget);

    await tester.tap(find.byKey(const Key('plugin-inspect')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-error')), findsNothing);
    // no settings: the review step installs directly
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Installieren'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/plugins/install').single)['settings'], <String, dynamic>{});
    expect(find.text('Demo-Plugin ist aktualisiert'), findsOneWidget);
    expect(find.text('Trage noch die fehlenden Einstellungen ein, dann ist es aktiv.'), findsOneWidget);
    expect(find.byKey(const Key('plugin-restart')), findsOneWidget);
  });

  testWidgets('Update: Link wird sofort geprüft, vorhandene Werte stehen im Formular, Geheimnis bleibt leer', (tester) async {
    await setScreenSize(tester, const Size(420, 2200));
    final backend = _backend();
    backend.json('POST', '/api/plugins/inspect',
        _preview(setSecret: true, installed: {'version': '1.0.0', 'sha': 'b' * 40, 'short_sha': 'bbbbbbb', 'same_sha': false}));
    backend.json('POST', '/api/plugins/install',
        {'id': 'demo_hub', 'version': '1.1.0', 'sha': _sha, 'updated': true, 'restart_required': false, 'active': true});
    await tester.pumpWidget(appWith(backend.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await tester.pumpAndSettle();
    expect(backend.sent('POST', '/api/plugins/inspect'), hasLength(1));
    expect(find.text('Update von Version 1.0.0 auf 1.1.0'), findsOneWidget);
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-continue')));
    await tester.pumpAndSettle();
    expect(find.text('Gespeichert – leer lassen, um es zu behalten'), findsWidgets);
    await tester.tap(find.byKey(const Key('plugin-install'))); // required fields are satisfied by the stored values
    await tester.pumpAndSettle();
    final sent = bodyOf(backend.sent('POST', '/api/plugins/install').single)['settings'] as Map<String, dynamic>;
    expect(sent['DEMO_HUB_URL'], 'https://alt.example.org');
    expect(sent['DEMO_HUB_TOKEN'], ''); // empty secret = keep the stored one
    expect(find.text('Demo-Plugin ist aktualisiert'), findsOneWidget);
  });

  testWidgets('derselbe Stand: Hinweis auf Neuinstallation', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final backend = _backend();
    backend.json('POST', '/api/plugins/inspect',
        _preview(installed: {'version': '1.1.0', 'sha': _sha, 'short_sha': 'aaaaaaa', 'same_sha': true}));
    await tester.pumpWidget(appWith(backend.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-same-commit')), findsOneWidget);
  });

  testWidgets('Installierte Plugins sind markiert, lassen sich aktualisieren und entfernen', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final backend = _backend(plugins: [_plugin], installed: [
      _installedJson,
      {..._installedJson, 'id': 'kaputt', 'name': 'Kaputt', 'loaded': false, 'active': false, 'error': 'Das Plugin lässt sich nicht laden: ImportError: weg'},
    ]);
    backend.json('POST', '/api/plugins/inspect', _preview(installed: {'version': '1.0.0', 'sha': 'x', 'short_sha': 'xxxxxxx', 'same_sha': false}));
    backend.json('DELETE', '/api/plugins/demo_hub', {'removed': true, 'restart_required': false});
    await tester.pumpWidget(appWith(backend.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();

    expect(find.textContaining('Aus GitHub installiert · 1.0.0'), findsOneWidget);
    expect(find.text('Installiert, aber nicht geladen'), findsOneWidget);
    expect(find.text('Das Plugin lässt sich nicht laden: ImportError: weg'), findsOneWidget);

    // update: opens the install screen with the stored link and checks it right away
    await tester.tap(find.byKey(const Key('plugin-menu-demo_hub')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Auf Update prüfen'));
    await tester.pumpAndSettle();
    expect(bodyOf(backend.sent('POST', '/api/plugins/inspect').single), {'url': 'https://github.com/acme/demo'});
    expect(find.text('Update von Version 1.0.0 auf 1.1.0'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    // remove asks first
    await tester.tap(find.byKey(const Key('plugin-menu-demo_hub')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Entfernen'));
    await tester.pumpAndSettle();
    expect(find.text('Plugin entfernen?'), findsOneWidget);
    expect(backend.requests.where((r) => r.method == 'DELETE'), isEmpty);
    await tester.tap(find.byKey(const Key('plugin-remove-confirm')));
    await tester.pumpAndSettle();
    expect(backend.requests.where((r) => r.method == 'DELETE'), hasLength(1));
    expect(find.text('Plugin entfernt'), findsOneWidget);
  });

  testWidgets('Betreiber hat die Installation abgeschaltet: kein Installieren-Knopf', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final backend = _backend(enabled: false, plugins: [_plugin]);
    await tester.pumpWidget(appWith(backend.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plugin-install-button')), findsNothing);
    expect(find.byKey(const Key('plugin-install-off')), findsOneWidget);
  });

  testWidgets('ältere Server ohne /api/plugins: Liste funktioniert, Knopf bleibt', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/admin/settings', [_plugin]);
    await tester.pumpWidget(appWith(backend.api(), const PluginsAdminScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Demo-Plugin'), findsOneWidget);
    expect(find.byKey(const Key('plugin-install-button')), findsOneWidget);
  });

  testWidgets('Englische Fassung', (tester) async {
    setAppLanguage('en');
    addTearDown(() => setAppLanguage('de'));
    await setScreenSize(tester, const Size(420, 2200));
    final backend = _backend();
    backend.json('POST', '/api/plugins/inspect', _preview());
    await tester.pumpWidget(appWith(backend.api(), const PluginInstallScreen(initialUrl: 'https://github.com/acme/demo')));
    await tester.pumpAndSettle();
    expect(find.text('Install plugin'), findsOneWidget);
    expect(find.text('by Acme · Version 1.1.0 · commit aaaaaaa · MIT'), findsOneWidget);
    expect(find.text('Only from trusted sources'), findsOneWidget);
    expect(find.text('I know the source and trust it'), findsOneWidget);
    expect(find.text('Connects to'), findsOneWidget);
    await tester.tap(find.byKey(const Key('plugin-trust')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-continue')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plugin-install')));
    await tester.pumpAndSettle();
    expect(find.text('Required'), findsNWidgets(2));
  });
}
