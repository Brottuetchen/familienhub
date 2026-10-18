import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

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
        title: Text(l10n.newServiceKey),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: InputDecoration(labelText: l10n.service, helperText: l10n.serviceSenderHint),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: Text(l10n.create)),
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
          title: Text(l10n.keyFor(created.name)),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(l10n.serviceKeyShownOnce),
                const SizedBox(height: 8),
                SelectableText(created.key ?? '', key: const Key('new-service-key'),
                    style: const TextStyle(fontFamily: 'monospace')),
                const SizedBox(height: 16),
                Text(l10n.haExample),
                const SizedBox(height: 4),
                SelectableText(example, style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: example));
                showInfo(ctx, l10n.exampleCopied);
              },
              child: Text(l10n.copyExample),
            ),
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: created.key ?? ''));
                showInfo(ctx, l10n.keyCopied);
              },
              child: Text(l10n.copyKey),
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
    final async = ref.watch(serviceKeysProvider);
    final fmt = localDate('d.M.yyyy HH:mm');
    return Scaffold(
      appBar: AppBar(title: Text(l10n.serviceKeys)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.vpn_key_outlined),
        label: Text(l10n.newKey),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(serviceKeysProvider)),
        data: (keys) => ListView(
          children: [
            Padding(
              padding: EdgeInsets.all(16),
              child: Text(l10n.serviceKeysExplain),
            ),
            if (keys.isEmpty) EmptyHint(icon: Icons.vpn_key_off_outlined, text: l10n.noServiceKeys),
            for (final k in keys)
              ListTile(
                leading: const Icon(Icons.vpn_key_outlined),
                title: Text(k.name),
                subtitle: Text('${k.hint}… · ${k.lastUsedAt != null ? 'zuletzt ${fmt.format(k.lastUsedAt!)}' : 'noch nie benutzt'}'),
                trailing: IconButton(
                  tooltip: l10n.revoke,
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
