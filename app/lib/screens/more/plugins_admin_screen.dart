import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

String _status(AdminPlugin p) => p.disabled
    ? l10n.pluginDisabled
    : p.configured
        ? l10n.pluginActive
        : l10n.pluginNotConfigured;

/// Nur Admins: Plugins an-/abschalten und ihre Zugänge pflegen (`/api/admin/settings`).
class PluginsAdminScreen extends ConsumerWidget {
  const PluginsAdminScreen({super.key});

  Future<void> _toggle(BuildContext context, WidgetRef ref, AdminPlugin p, bool enabled) async {
    if (await runAction(context, () => ref.read(apiClientProvider).setPluginEnabled(p.id, enabled))) {
      ref.invalidate(adminPluginsProvider);
      ref.invalidate(modulesProvider); // Bereiche in der App sofort anpassen
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(adminPluginsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.pluginsAccess)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(adminPluginsProvider.future),
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminPluginsProvider)),
          data: (plugins) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              for (final p in plugins)
                ListTile(
                  key: Key('plugin-${p.id}'),
                  title: Text(p.name),
                  subtitle: Text('${_status(p)} · ${p.description}', maxLines: 2, overflow: TextOverflow.ellipsis),
                  trailing: Switch(
                    value: !p.disabled,
                    onChanged: (v) => _toggle(context, ref, p, v),
                  ),
                  onTap: () async {
                    final saved = await Navigator.of(context).push<bool>(
                        MaterialPageRoute(builder: (_) => PluginSettingsScreen(plugin: p)));
                    if (saved == true) {
                      ref.invalidate(adminPluginsProvider);
                      ref.invalidate(modulesProvider);
                    }
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Zugänge eines Plugins. Geheimnisse werden nie angezeigt; leer lassen = unverändert.
class PluginSettingsScreen extends ConsumerStatefulWidget {
  final AdminPlugin plugin;
  const PluginSettingsScreen({super.key, required this.plugin});

  @override
  ConsumerState<PluginSettingsScreen> createState() => _PluginSettingsScreenState();
}

class _PluginSettingsScreenState extends ConsumerState<PluginSettingsScreen> {
  late final Map<String, TextEditingController> _c = {
    for (final f in widget.plugin.fields) f.key: TextEditingController(text: f.secret ? '' : f.value),
  };
  bool _saving = false;
  bool _testing = false;
  ConnectionResult? _result;

  /// Echter Test mit den eingegebenen Werten, ohne zu speichern.
  Future<void> _test() async {
    setState(() {
      _testing = true;
      _result = null;
    });
    try {
      final values = {for (final f in widget.plugin.fields) f.key: _c[f.key]!.text.trim()};
      final r = await ref.read(apiClientProvider).testPlugin(widget.plugin.id, values);
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final values = <String, String>{};
    for (final f in widget.plugin.fields) {
      final v = _c[f.key]!.text.trim();
      if (f.secret && v.isEmpty) continue; // Geheimnis unverändert lassen
      if (!f.secret && v == f.value) continue;
      values[f.key] = v;
    }
    if (values.isEmpty) {
      Navigator.pop(context, false);
      return;
    }
    setState(() => _saving = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).saveAdminSettings(values));
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      showInfo(context, l10n.saved);
      Navigator.pop(context, true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.plugin;
    return Scaffold(
      appBar: AppBar(title: Text(p.name)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
        children: [
          if (p.description.isNotEmpty)
            Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(p.description)),
          for (final f in p.fields)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TextField(
                key: Key('field-${f.key}'),
                controller: _c[f.key],
                obscureText: f.secret,
                autocorrect: !f.secret,
                enableSuggestions: !f.secret,
                decoration: InputDecoration(
                  labelText: f.required ? '${f.label} *' : f.label,
                  helperText: f.secret && f.isSet
                      ? l10n.savedKeepEmpty
                      : (f.help.isEmpty ? null : f.help),
                  helperMaxLines: 3,
                ),
                onChanged: (_) {
                  if (_result != null) setState(() => _result = null); // altes Ergebnis passt nicht mehr
                },
              ),
            ),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              key: const Key('plugin-test'),
              onPressed: _testing ? null : _test,
              icon: _testing ? const HubLoader(size: 18) : const Icon(Icons.network_check),
              label: Text(l10n.testConnection),
            ),
          ),
          if (_result != null) ConnectionResultCard(result: _result!),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _saving ? null : _save,
        icon: const Icon(Icons.save_outlined),
        label: Text(l10n.save),
      ),
    );
  }
}


/// Ergebnis von „Verbindung testen“: grün (verbunden), blau (Hinweis), rot (Problem).
class ConnectionResultCard extends StatelessWidget {
  final ConnectionResult result;
  const ConnectionResultCard({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (IconData icon, Color color) = switch (result.level) {
      'ok' => (Icons.check_circle, Colors.green),
      'info' => (Icons.info_outline, scheme.primary),
      _ => (Icons.error_outline, scheme.error),
    };
    return Container(
      key: const Key('plugin-test-result'),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(children: [
        Icon(icon, color: color),
        const SizedBox(width: 10),
        Expanded(child: Text(result.message)),
      ]),
    );
  }
}
