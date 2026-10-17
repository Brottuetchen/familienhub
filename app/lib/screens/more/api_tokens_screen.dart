import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final apiTokensProvider = FutureProvider.autoDispose<List<ApiTokenInfo>>(
    (ref) => ref.watch(apiClientProvider).apiTokens());

/// Persönliche Schlüssel für Assistenten (z. B. Sprachassistent). Ein Schlüssel handelt nur als du.
class ApiTokensScreen extends ConsumerWidget {
  const ApiTokensScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final ctrl = TextEditingController(text: 'Sprachassistent');
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Neuer Zugang'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Wofür?', helperText: 'z. B. Sprachassistent'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('Anlegen')),
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
          title: Text('Schlüssel für „${created.name}“'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Wird nur jetzt angezeigt. Im Assistenten bei der Familienhub-Anbindung eintragen.'),
              const SizedBox(height: 12),
              SelectableText(created.token ?? '', key: const Key('new-token'), style: const TextStyle(fontFamily: 'monospace')),
            ],
          ),
          actions: [
            TextButton.icon(
              icon: const Icon(Icons.copy),
              label: const Text('Kopieren'),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: created.token ?? ''));
                showInfo(ctx, 'Kopiert');
              },
            ),
            FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Fertig')),
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
    final fmt = DateFormat('d.M.yyyy HH:mm', 'de_DE');
    return Scaffold(
      appBar: AppBar(title: const Text('Zugänge für Assistenten')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.key),
        label: const Text('Neuer Zugang'),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(apiTokensProvider)),
        data: (tokens) => ListView(
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Mit einem Zugang kann z. B. ein Sprachassistent deine Aufgaben, Einkäufe und Termine lesen und anlegen – '
                  'immer nur als du. Widerrufen geht jederzeit.'),
            ),
            if (tokens.isEmpty) const EmptyHint(icon: Icons.key_off, text: 'Noch kein Zugang angelegt'),
            for (final t in tokens)
              ListTile(
                leading: const Icon(Icons.key),
                title: Text(t.name),
                subtitle: Text([
                  '${t.hint}…',
                  if (t.lastUsedAt != null) 'zuletzt ${fmt.format(t.lastUsedAt!)}' else 'noch nie benutzt',
                ].join(' · ')),
                trailing: IconButton(
                  tooltip: 'Widerrufen',
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
