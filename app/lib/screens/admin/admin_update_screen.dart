import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/backup.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final updateInfoProvider = FutureProvider.autoDispose<UpdateInfo>((ref) => ref.watch(apiClientProvider).updateInfo());

/// Text under the title: what the check found, or why there is nothing to say.
String updateStatusText(UpdateInfo u) {
  if (u.available) return l10n.updateAvailable(u.latest ?? '?');
  return switch (u.status) {
    'off' => l10n.updateOff,
    'unavailable' => l10n.updateUnavailable,
    'unknown_version' => l10n.updateUnknownVersion,
    'bad_repo' => l10n.updateBadRepo,
    _ => l10n.updateUpToDate,
  };
}

/// Administration → Updates: newer release (version, notes link, Docker command) and the on/off switch.
class AdminUpdateScreen extends ConsumerStatefulWidget {
  final Future<void> Function(Uri uri)? openUrl;
  const AdminUpdateScreen({super.key, this.openUrl});

  @override
  ConsumerState<AdminUpdateScreen> createState() => _AdminUpdateScreenState();
}

class _AdminUpdateScreenState extends ConsumerState<AdminUpdateScreen> {
  final _repo = TextEditingController();
  String? _loadedRepo;

  @override
  void dispose() {
    _repo.dispose();
    super.dispose();
  }

  Future<void> _save(bool enabled, String repo) async {
    if (await runAction(context, () => ref.read(apiClientProvider).saveUpdateSettings(enabled: enabled, repo: repo))) {
      _loadedRepo = null;
      ref.invalidate(updateInfoProvider);
    }
  }

  @override
  Widget build(BuildContext context) {
    final info = ref.watch(updateInfoProvider);
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.updateTitle)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(updateInfoProvider.future),
        child: info.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(updateInfoProvider)),
          data: (u) {
            if (_loadedRepo != u.repo) {
              _loadedRepo = u.repo;
              _repo.text = u.repo;
            }
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
              children: [
                Text(updateStatusText(u),
                    key: const Key('update-status'),
                    style: theme.textTheme.titleMedium?.copyWith(color: u.available ? theme.colorScheme.primary : null)),
                const SizedBox(height: 4),
                Text(
                  [l10n.updateCurrent(u.current), if (u.available && u.prerelease) l10n.updatePrerelease].join(' · '),
                  style: muted,
                ),
                if (u.available) ...[
                  const SizedBox(height: 12),
                  if (u.url != null)
                    OutlinedButton.icon(
                      key: const Key('update-notes'),
                      onPressed: () => (widget.openUrl ?? (x) => launchUrl(x, mode: LaunchMode.externalApplication))(
                          Uri.parse(u.url!)),
                      icon: const Icon(Icons.open_in_new),
                      label: Text(l10n.updateReleaseNotes),
                    ),
                  const SizedBox(height: 16),
                  Text(l10n.updateCommand, style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: SelectableText(u.dockerCommand,
                        key: const Key('update-command'), style: const TextStyle(fontFamily: 'monospace')),
                  ),
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: TextButton.icon(
                      onPressed: () async {
                        await Clipboard.setData(ClipboardData(text: u.dockerCommand));
                        if (context.mounted) showInfo(context, l10n.copied);
                      },
                      icon: const Icon(Icons.copy),
                      label: Text(l10n.copy),
                    ),
                  ),
                ],
                const Divider(height: 32),
                SwitchListTile(
                  key: const Key('update-switch'),
                  contentPadding: EdgeInsets.zero,
                  title: Text(l10n.updateCheckSwitch),
                  subtitle: Text(l10n.updateCheckHint),
                  value: u.enabled,
                  onChanged: (v) => _save(v, _repo.text.trim()),
                ),
                const SizedBox(height: 8),
                TextField(
                  key: const Key('update-repo'),
                  controller: _repo,
                  decoration: InputDecoration(labelText: l10n.updateRepo, border: const OutlineInputBorder()),
                  autocorrect: false,
                  onSubmitted: (v) => _save(u.enabled, v.trim()),
                ),
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: TextButton(
                    key: const Key('update-save'),
                    onPressed: () => _save(u.enabled, _repo.text.trim()),
                    child: Text(l10n.save),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
