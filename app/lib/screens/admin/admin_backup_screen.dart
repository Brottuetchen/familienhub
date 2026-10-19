import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/backup.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final backupInfoProvider = FutureProvider.autoDispose<BackupInfo>((ref) => ref.watch(apiClientProvider).backupInfo());

String backupDate(DateTime d) => localDate('d.M.y HH:mm').format(d.toLocal());

/// Translated text for a failed backup action (the server sends a stable code).
String backupErrorText(BackupResult r) => switch (r.code) {
      'newer_version' => l10n.backupErrNewer,
      'older_schema' => l10n.backupErrOlder,
      'not_a_backup' || 'unsafe' || 'corrupt' || 'bad_name' || 'not_found' => l10n.backupErrInvalid,
      'busy' => l10n.backupErrBusy,
      'dir_not_writable' => l10n.backupErrDir,
      'safety_backup_failed' => l10n.backupErrSafety,
      _ => l10n.backupErrFailed,
    };

String _kindLabel(String kind) => switch (kind) {
      'auto' => l10n.backupKindAuto,
      'safety' => l10n.backupKindSafety,
      'uploaded' => l10n.backupKindUploaded,
      _ => l10n.backupKindManual,
    };

String _size(int bytes) {
  if (bytes >= 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  return '${(bytes / 1024).ceil()} KB';
}

/// Administration → Backup: download, store on the hub, nightly backups, restore (with a clear warning).
class AdminBackupScreen extends ConsumerStatefulWidget {
  /// Opens the one-time download address; replaced in tests.
  final Future<void> Function(Uri uri)? openUrl;
  const AdminBackupScreen({super.key, this.openUrl});

  @override
  ConsumerState<AdminBackupScreen> createState() => _AdminBackupScreenState();
}

class _AdminBackupScreenState extends ConsumerState<AdminBackupScreen> {
  bool _busy = false;
  int? _keepDraft;

  Future<void> _download() async {
    setState(() => _busy = true);
    try {
      final uri = await ref.read(apiClientProvider).backupDownloadUri();
      await (widget.openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication))(uri);
      if (mounted) showInfo(context, l10n.backupDownloadStarted);
      await Future<void>.delayed(const Duration(seconds: 2)); // the file is made while the download starts
      ref.invalidate(backupInfoProvider);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _createOnHub() async {
    setState(() => _busy = true);
    try {
      final r = await ref.read(apiClientProvider).createBackup();
      if (!mounted) return;
      showInfo(context, r.ok ? l10n.backupCreated : backupErrorText(r));
      ref.invalidate(backupInfoProvider);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _saveSettings(bool auto, int keep) async {
    if (await runAction(context, () => ref.read(apiClientProvider).saveBackupSettings(auto: auto, keep: keep))) {
      ref.invalidate(backupInfoProvider);
    }
  }

  Future<void> _delete(BackupItem item) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(l10n.backupDeleteQuestion),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    await runAction(context, () => ref.read(apiClientProvider).deleteBackup(item.name));
    ref.invalidate(backupInfoProvider);
  }

  Future<void> _restore(BackupItem item) async {
    final api = ref.read(apiClientProvider);
    final check = await api.inspectBackup(item.name);
    if (!mounted) return;
    if (!check.ok) {
      showInfo(context, backupErrorText(check));
      return;
    }
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('restore-dialog'),
        icon: Icon(Icons.warning_amber_rounded, color: Theme.of(ctx).colorScheme.error),
        title: Text(l10n.backupRestoreTitle),
        content: SingleChildScrollView(
          child: Text(l10n.backupRestoreWarning(item.createdAt == null ? '?' : backupDate(item.createdAt!))),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(
            key: const Key('restore-confirm'),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(ctx).colorScheme.error),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l10n.backupRestoreConfirm),
          ),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final r = await api.restoreBackup(item.name);
      if (!mounted) return;
      if (!r.ok) {
        showInfo(context, backupErrorText(r));
        return;
      }
      setState(() => _busy = false);
      ref.invalidate(backupInfoProvider);
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          key: const Key('restart-dialog'),
          icon: const Icon(Icons.restart_alt),
          title: Text(l10n.backupRestoreDone),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(l10n.backupRestartNeeded),
              if (r.warnings.contains('secret_key_env')) ...[
                const SizedBox(height: 12),
                Text(l10n.backupWarnSecretEnv),
              ],
            ]),
          ),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.close))],
        ),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
      ref.invalidate(backupInfoProvider);
    }
  }

  @override
  Widget build(BuildContext context) {
    final info = ref.watch(backupInfoProvider);
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.backupTitle)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(backupInfoProvider.future),
        child: info.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(backupInfoProvider)),
          data: (b) {
            final keep = _keepDraft ?? b.keep;
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
              children: [
                Text(
                  b.lastOk == false
                      ? l10n.backupLastFailed
                      : b.lastAt == null
                          ? l10n.backupNoneYet
                          : l10n.backupLastLine(backupDate(b.lastAt!)),
                  key: const Key('backup-last'),
                  style: theme.textTheme.titleMedium?.copyWith(color: b.lastOk == false ? theme.colorScheme.error : null),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  key: const Key('backup-download'),
                  onPressed: _busy ? null : _download,
                  icon: const Icon(Icons.download),
                  label: Text(l10n.backupDownload),
                ),
                const SizedBox(height: 8),
                Text(l10n.backupDownloadHint, style: muted),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  key: const Key('backup-create'),
                  onPressed: _busy ? null : _createOnHub,
                  icon: const Icon(Icons.save_alt),
                  label: Text(l10n.backupCreateOnHub),
                ),
                if (_busy) const Padding(padding: EdgeInsets.only(top: 12), child: LinearProgressIndicator()),
                const Divider(height: 32),
                SwitchListTile(
                  key: const Key('backup-auto'),
                  contentPadding: EdgeInsets.zero,
                  title: Text(l10n.backupAuto),
                  subtitle: Text(l10n.backupAutoHint(b.autoTime)),
                  value: b.auto,
                  onChanged: (v) => _saveSettings(v, keep),
                ),
                Text(l10n.backupKeep(keep)),
                Slider(
                  key: const Key('backup-keep'),
                  min: 1,
                  max: 30,
                  divisions: 29,
                  value: keep.clamp(1, 30).toDouble(),
                  label: '$keep',
                  onChanged: (v) => setState(() => _keepDraft = v.round()),
                  onChangeEnd: (v) async {
                    await _saveSettings(b.auto, v.round());
                    if (mounted) setState(() => _keepDraft = null);
                  },
                ),
                const Divider(height: 32),
                Text(l10n.backupStored, style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                if (b.backups.isEmpty)
                  Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Text(l10n.backupNoneStored, style: muted)),
                for (final item in b.backups)
                  Card(
                    key: ValueKey('backup-${item.name}'),
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(
                          '${_kindLabel(item.kind)} · ${item.createdAt == null ? '?' : backupDate(item.createdAt!)}',
                          style: theme.textTheme.titleSmall,
                        ),
                        Text([_size(item.size), if (item.hubVersion != null) item.hubVersion!].join(' · '), style: muted),
                        const SizedBox(height: 4),
                        Wrap(spacing: 8, children: [
                          TextButton.icon(
                            key: ValueKey('restore-${item.name}'),
                            onPressed: _busy || !item.valid ? null : () => _restore(item),
                            icon: const Icon(Icons.settings_backup_restore),
                            label: Text(l10n.backupRestore),
                          ),
                          TextButton.icon(
                            key: ValueKey('delete-${item.name}'),
                            onPressed: _busy ? null : () => _delete(item),
                            icon: const Icon(Icons.delete_outline),
                            label: Text(l10n.delete),
                          ),
                        ]),
                      ]),
                    ),
                  ),
                const SizedBox(height: 12),
                Text(l10n.backupUploadHint, style: muted),
              ],
            );
          },
        ),
      ),
    );
  }
}
