import 'package:familienhub/screens/admin/admin_backup_screen.dart';
import 'package:familienhub/screens/admin/admin_screen.dart';
import 'package:familienhub/screens/admin/admin_update_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

const _manual = 'familienhub-backup-20261018-120000.zip';
const _auto = 'familienhub-auto-20261019-033000.zip';

Map<String, dynamic> _overview({String? lastBackup}) => {
      'server': {'version': '1.0.0', 'environment': 'production'},
      'plugins': [],
      'push': {'fcm': false, 'webpush': false, 'devices': {}},
      'users': {'active': 2, 'total': 2},
      'backup': {'last_at': lastBackup, 'last_ok': lastBackup != null, 'auto': true},
    };

Map<String, dynamic> _backupInfo({bool auto = true}) => {
      'last': {'at': '2026-10-19T03:30:00+00:00', 'ok': true, 'kind': 'auto', 'name': _auto},
      'auto': auto,
      'keep': 7,
      'auto_time': '03:30',
      'dialect': 'postgresql',
      'version': '1.0.0',
      'backups': [
        {'name': _auto, 'size': 2 * 1024 * 1024, 'kind': 'auto', 'created_at': '2026-10-19T03:30:00+00:00', 'hub_version': '1.0.0', 'includes_keys': true, 'valid': true},
        {'name': _manual, 'size': 4096, 'kind': 'manual', 'created_at': '2026-10-18T12:00:00+00:00', 'hub_version': '1.0.0', 'includes_keys': false, 'valid': true},
      ],
    };

Map<String, dynamic> _update({bool available = true}) => {
      'enabled': true,
      'repo': 'owner/repo',
      'current': '1.0.0',
      'available': available,
      'latest': available ? '1.1.0' : null,
      'url': available ? 'https://github.com/owner/repo/releases/tag/v1.1.0' : null,
      'name': 'Familienhub 1.1.0',
      'prerelease': false,
      'docker_command': 'docker compose pull && docker compose up -d',
      'status': 'ok',
    };

FakeBackend _backend({bool update = true}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/admin/overview', _overview(lastBackup: '2026-10-19T03:30:00+00:00'));
  b.json('GET', '/api/admin/backup', _backupInfo());
  b.json('GET', '/api/admin/update', _update(available: update));
  return b;
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Administration shows the last backup and the update notice', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(appWith(_backend().api(), const AdminScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('admin-update-banner')), findsOneWidget);
    expect(find.text('Version 1.1.0 ist verfügbar'), findsWidgets);
    expect(find.textContaining('Letztes Backup: '), findsOneWidget);
  });

  testWidgets('a failed update check shows no notice and no error', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.on('GET', '/api/admin/update', (_) => jsonResponse({'detail': 'boom'}, status: 500));
    await tester.pumpWidget(appWith(b.api(), const AdminScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('admin-update-banner')), findsNothing);
    expect(find.byKey(const Key('admin-overview')), findsOneWidget);
  });

  testWidgets('no notice when the hub is up to date', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    await tester.pumpWidget(appWith(_backend(update: false).api(), const AdminScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('admin-update-banner')), findsNothing);
    expect(find.text('Der Hub ist auf dem neuesten Stand'), findsOneWidget);
  });

  testWidgets('download opens the one-time link', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('POST', '/api/admin/backup/download-link', {'path': '/api/admin/backup/download?token=abc', 'expires_in': 120});
    Uri? opened;
    await tester.pumpWidget(appWith(b.api(), AdminBackupScreen(openUrl: (u) async => opened = u)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('backup-download')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    expect(opened.toString(), 'https://hub.test/api/admin/backup/download?token=abc');
  });

  testWidgets('create a backup on the hub', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('POST', '/api/admin/backup', {'ok': true, 'name': _manual});
    await tester.pumpWidget(appWith(b.api(), const AdminBackupScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('backup-create')));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/admin/backup'), hasLength(1));
    expect(find.text('Backup erstellt'), findsOneWidget);
  });

  testWidgets('nightly backup switch saves the setting', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('PUT', '/api/admin/backup/settings', _backupInfo(auto: false));
    await tester.pumpWidget(appWith(b.api(), const AdminBackupScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('backup-auto')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/backup/settings').single), {'auto': false, 'keep': 7});
  });

  testWidgets('restore warns, needs confirmation and tells to restart', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('POST', '/api/admin/backup/$_manual/inspect', {'ok': true});
    b.json('POST', '/api/admin/backup/$_manual/restore', {'ok': true, 'restart_required': true, 'warnings': []});
    await tester.pumpWidget(appWith(b.api(), const AdminBackupScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('restore-$_manual')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('restore-dialog')), findsOneWidget);
    expect(find.textContaining('ACHTUNG'), findsOneWidget);
    expect(b.sent('POST', '/api/admin/backup/$_manual/restore'), isEmpty); // nothing happens before confirming
    await tester.tap(find.byKey(const Key('restore-confirm')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/admin/backup/$_manual/restore').single), {'confirm': true});
    expect(find.byKey(const Key('restart-dialog')), findsOneWidget);
    expect(find.textContaining('neu starten'), findsOneWidget);
  });

  testWidgets('a backup from a newer hub is refused before any warning', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('POST', '/api/admin/backup/$_manual/inspect', {'ok': false, 'code': 'newer_version', 'message': 'newer'});
    await tester.pumpWidget(appWith(b.api(), const AdminBackupScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('restore-$_manual')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('restore-dialog')), findsNothing);
    expect(find.textContaining('neueren Familienhub-Version'), findsOneWidget);
    expect(b.sent('POST', '/api/admin/backup/$_manual/restore'), isEmpty);
  });

  testWidgets('deleting a stored backup asks first', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('DELETE', '/api/admin/backup/$_manual', {'ok': true});
    await tester.pumpWidget(appWith(b.api(), const AdminBackupScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('delete-$_manual')));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/admin/backup/$_manual'), isEmpty);
    await tester.tap(find.widgetWithText(FilledButton, 'Löschen'));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/admin/backup/$_manual'), hasLength(1));
  });

  testWidgets('update screen: notes link, command and switch', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _backend();
    b.json('PUT', '/api/admin/update/settings', {..._update(available: false), 'enabled': false, 'status': 'off'});
    Uri? opened;
    await tester.pumpWidget(appWith(b.api(), AdminUpdateScreen(openUrl: (u) async => opened = u)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('update-status')), findsOneWidget);
    expect(find.text('docker compose pull && docker compose up -d'), findsOneWidget);
    await tester.tap(find.byKey(const Key('update-notes')));
    expect(opened.toString(), 'https://github.com/owner/repo/releases/tag/v1.1.0');
    await tester.tap(find.byKey(const Key('update-switch')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/update/settings').single), {'enabled': false, 'repo': 'owner/repo'});
  });

  for (final screen in <String, Widget>{
    'backup': const AdminBackupScreen(),
    'update': const AdminUpdateScreen(),
    'admin': const AdminScreen(),
  }.entries) {
    testWidgets('${screen.key} screen does not overflow at text scale 2.0 on 360 dp', (tester) async {
      await setScreenSize(tester, const Size(360, 800));
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(appWith(_backend().api(), screen.value));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
