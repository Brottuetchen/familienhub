import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final ntfyProvider = FutureProvider.autoDispose<NtfySettings>((ref) => ref.watch(apiClientProvider).ntfySettings());

/// Push via ntfy (#23): the way for iPhones without an App Store app. Hidden when the hub has no ntfy server.
class NtfyCard extends ConsumerWidget {
  const NtfyCard({super.key});

  Future<void> _change(BuildContext context, WidgetRef ref, Future<NtfySettings> Function() call) async {
    if (await runAction(context, call)) ref.invalidate(ntfyProvider);
  }

  Future<void> _newTopic(BuildContext context, WidgetRef ref) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.ntfyNewTopicQuestion),
        content: Text(l10n.ntfyNewTopicHint),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.ntfyNewTopic)),
        ],
      ),
    );
    if (sure == true && context.mounted) await _change(context, ref, () => ref.read(apiClientProvider).newNtfyTopic());
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(ntfyProvider).valueOrNull;
    if (s == null || !s.available) return const SizedBox.shrink();
    final api = ref.read(apiClientProvider);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SwitchListTile(
        key: const Key('ntfy-enabled'),
        secondary: const Icon(Icons.campaign_outlined),
        title: Text(l10n.ntfyTitle),
        subtitle: Text(l10n.ntfySubtitle),
        value: s.enabled,
        onChanged: (v) => _change(context, ref, () => api.setNtfy(enabled: v)),
      ),
      if (s.enabled && s.topic != null)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(l10n.ntfySteps(s.server ?? ''), style: muted),
            const SizedBox(height: 8),
            SelectableText(s.topic!, key: const Key('ntfy-topic'), style: const TextStyle(fontFamily: 'monospace')),
            const SizedBox(height: 4),
            Wrap(spacing: 8, children: [
              TextButton.icon(
                icon: const Icon(Icons.copy, size: 18),
                label: Text(l10n.ntfyCopyTopic),
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: s.topic!));
                  if (context.mounted) showInfo(context, l10n.copied);
                },
              ),
              if (s.subscribeUrl != null)
                TextButton.icon(
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: Text(l10n.ntfyOpen),
                  onPressed: () => launchUrl(Uri.parse(s.subscribeUrl!), mode: LaunchMode.externalApplication),
                ),
              TextButton.icon(
                key: const Key('ntfy-new-topic'),
                icon: const Icon(Icons.refresh, size: 18),
                label: Text(l10n.ntfyNewTopic),
                onPressed: () => _newTopic(context, ref),
              ),
            ]),
          ]),
        ),
    ]);
  }
}
