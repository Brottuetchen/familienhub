import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final serviceKeysProvider = FutureProvider.autoDispose<List<ServiceKeyInfo>>(
    (ref) => ref.watch(apiClientProvider).serviceKeys());

/// Beispiel für Home Assistant (configuration.yaml → rest_command), damit HA über den Hub benachrichtigt.
String haExample(String baseUrl, String key) => '''rest_command:
  familienhub:
    url: "$baseUrl/api/notify"
    method: POST
    headers:
      Authorization: "Bearer $key"
    content_type: "application/json"
    payload: >
      {"title": "{{ title }}", "body": "{{ body | default('') }}",
       "to": "{{ to | default('family') }}", "category": "{{ category | default('house') }}"}''';

/// Admin: Schlüssel, mit denen andere Systeme Mitteilungen über den Hub schicken.
class ServiceKeysScreen extends ConsumerWidget {
  const ServiceKeysScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final ctrl = TextEditingController(text: 'Home Assistant');
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Neuer Dienst-Schlüssel'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Dienst', helperText: 'Erscheint als Absender im Verlauf'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('Anlegen')),
        ],
      ),
    );
    if (name == null || name.isEmpty || !context.mounted) return;
    try {
      final api = ref.read(apiClientProvider);
      final created = await api.createServiceKey(name);
      final base = await api.store.baseUrl() ?? '';
      ref.invalidate(serviceKeysProvider);
      if (!context.mounted) return;
      final example = haExample(base, created.key ?? '');
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: Text('Schlüssel für „${created.name}“'),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Wird nur jetzt angezeigt. Er darf nur Mitteilungen einliefern.'),
                const SizedBox(height: 8),
                SelectableText(created.key ?? '', key: const Key('new-service-key'),
                    style: const TextStyle(fontFamily: 'monospace')),
                const SizedBox(height: 16),
                const Text('Beispiel für Home Assistant:'),
                const SizedBox(height: 4),
                SelectableText(example, style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: example));
                showInfo(ctx, 'Beispiel kopiert');
              },
              child: const Text('Beispiel kopieren'),
            ),
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: created.key ?? ''));
                showInfo(ctx, 'Schlüssel kopiert');
              },
              child: const Text('Schlüssel kopieren'),
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
    final async = ref.watch(serviceKeysProvider);
    final fmt = DateFormat('d.M.yyyy HH:mm', 'de_DE');
    return Scaffold(
      appBar: AppBar(title: const Text('Dienst-Schlüssel')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.vpn_key_outlined),
        label: const Text('Neuer Schlüssel'),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(serviceKeysProvider)),
        data: (keys) => ListView(
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Home Assistant, Shelfarr, Paperless & Co. schicken damit Mitteilungen an die Familie '
                  '(POST /api/notify). Ruhezeiten und Einstellungen jeder Person gelten.'),
            ),
            if (keys.isEmpty) const EmptyHint(icon: Icons.vpn_key_off_outlined, text: 'Noch keine Dienst-Schlüssel'),
            for (final k in keys)
              ListTile(
                leading: const Icon(Icons.vpn_key_outlined),
                title: Text(k.name),
                subtitle: Text('${k.hint}… · ${k.lastUsedAt != null ? 'zuletzt ${fmt.format(k.lastUsedAt!)}' : 'noch nie benutzt'}'),
                trailing: IconButton(
                  tooltip: 'Widerrufen',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    if (await runAction(context, () => ref.read(apiClientProvider).revokeServiceKey(k.id))) {
                      ref.invalidate(serviceKeysProvider);
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
