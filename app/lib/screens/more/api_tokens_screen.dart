import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

final apiTokensProvider = FutureProvider.autoDispose<List<ApiTokenInfo>>(
    (ref) => ref.watch(apiClientProvider).apiTokens());

/// Persönliche Schlüssel für Assistenten (z. B. Sprachassistent). Ein Schlüssel handelt nur als du.
class ApiTokensScreen extends ConsumerWidget {
  const ApiTokensScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final ctrl = TextEditingController(text: l10n.voiceAssistant);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.newAccess),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: InputDecoration(labelText: l10n.whatFor, helperText: l10n.egVoiceAssistant),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: Text(l10n.create)),
        ],
      ),
    );
    if (name == null || name.isEmpty || !context.mounted) return;
    try {
      final created = await ref.read(apiClientProvider).createApiToken(name);
      ref.invalidate(apiTokensProvider);
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: Text(l10n.keyFor(created.name)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.tokenShownOnce),
              const SizedBox(height: 12),
              SelectableText(created.token ?? '', key: const Key('new-token'), style: const TextStyle(fontFamily: 'monospace')),
            ],
          ),
          actions: [
            TextButton.icon(
              icon: const Icon(Icons.copy),
              label: Text(l10n.copy),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: created.token ?? ''));
                showInfo(ctx, l10n.copied);
              },
            ),
            FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.finished)),
          ],
        ),
      );
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(apiTokensProvider);
    final fmt = localDate('d.M.yyyy HH:mm');
    return Scaffold(
      appBar: AppBar(title: Text(l10n.assistantAccess)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.key),
        label: Text(l10n.newAccess),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(apiTokensProvider)),
        data: (tokens) => ListView(
          children: [
            Padding(
              padding: EdgeInsets.all(16),
              child: Text(l10n.assistantAccessExplain),
            ),
            if (tokens.isEmpty) EmptyHint(icon: Icons.key_off, text: l10n.noAccessYet),
            for (final t in tokens)
              ListTile(
                leading: const Icon(Icons.key),
                title: Text(t.name),
                subtitle: Text([
                  '${t.hint}…',
                  if (t.lastUsedAt != null) l10n.lastUsed(fmt.format(t.lastUsedAt!)) else l10n.neverUsed,
                ].join(' · ')),
                trailing: IconButton(
                  tooltip: l10n.revoke,
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    if (await runAction(context, () => ref.read(apiClientProvider).revokeApiToken(t.id))) {
                      ref.invalidate(apiTokensProvider);
                    }
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
