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
    final name = await showDialog<String>(context: context, builder: (_) => const _NameDialog());
    if (name == null || name.isEmpty || !context.mounted) return;
    // Take everything we need from `ref` before the first await: the screen may be gone when the answer arrives.
    final api = ref.read(apiClientProvider);
    final container = ProviderScope.containerOf(context, listen: false);
    try {
      final created = await api.createApiToken(name, scopes: const ['voice']); // least privilege: voice endpoints only
      container.invalidate(apiTokensProvider);
      if (!context.mounted) return;
      final plain = created.token;
      if (plain == null || plain.isEmpty) {
        // The key exists on the server but its plaintext did not arrive: tell the user instead of crashing.
        showInfo(context, l10n.tokenNotReturned);
        return;
      }
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
              SelectableText(plain, key: const Key('new-token'), style: const TextStyle(fontFamily: 'monospace')),
            ],
          ),
          actions: [
            TextButton.icon(
              icon: const Icon(Icons.copy),
              label: Text(l10n.copy),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: plain));
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

/// Asks for the name of the new key. Owns its controller and accepts only one submit, so a double tap on
/// "Create" cannot pop the (already closing) route twice.
class _NameDialog extends StatefulWidget {
  const _NameDialog();

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  final _ctrl = TextEditingController(text: l10n.voiceAssistant);
  bool _done = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _close([String? result]) {
    if (_done) return;
    _done = true;
    Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(l10n.newAccess),
        content: TextField(
          controller: _ctrl,
          autofocus: true,
          decoration: InputDecoration(labelText: l10n.whatFor, helperText: l10n.egVoiceAssistant),
        ),
        actions: [
          TextButton(onPressed: _close, child: Text(l10n.cancel)),
          FilledButton(onPressed: () => _close(_ctrl.text.trim()), child: Text(l10n.create)),
        ],
      );
}
