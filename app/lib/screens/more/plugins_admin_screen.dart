import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../models/plugin_install.dart';
import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';
import '../admin/admin_screen.dart' show adminOverviewProvider;
import '../admin/ics_feeds_screen.dart';
import 'plugin_install_screen.dart';

String _status(AdminPlugin p) => p.disabled
    ? l10n.pluginDisabled
    : p.configured
        ? l10n.pluginActive
        : l10n.pluginNotConfigured;

/// Nur Admins: Plugins an-/abschalten und ihre Zugänge pflegen (`/api/admin/settings`).
/// Plugins können aus GitHub installiert, aktualisiert und entfernt werden (`/api/plugins/*`).
class PluginsAdminScreen extends ConsumerWidget {
  const PluginsAdminScreen({super.key});

  Future<void> _toggle(BuildContext context, WidgetRef ref, AdminPlugin p, bool enabled) async {
    if (await runAction(context, () => ref.read(apiClientProvider).setPluginEnabled(p.id, enabled))) {
      ref.invalidate(adminPluginsProvider);
      ref.invalidate(adminOverviewProvider);
      ref.invalidate(modulesProvider); // Bereiche in der App sofort anpassen
    }
  }

  void _refresh(WidgetRef ref) {
    ref.invalidate(adminPluginsProvider);
    ref.invalidate(installedPluginsProvider);
    ref.invalidate(modulesProvider);
  }

  Future<void> _install(BuildContext context, WidgetRef ref, {String? url}) async {
    await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => PluginInstallScreen(initialUrl: url)));
    _refresh(ref);
  }

  Future<void> _remove(BuildContext context, WidgetRef ref, InstalledPluginInfo p) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.pluginRemoveQuestion),
        content: Text(l10n.pluginRemoveHint(p.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(key: const Key('plugin-remove-confirm'), onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.remove)),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    var restart = false;
    if (await runAction(context, () async => restart = await ref.read(apiClientProvider).removePlugin(p.id))) {
      _refresh(ref);
      if (context.mounted) showInfo(context, restart ? l10n.pluginRemovedRestart : l10n.pluginRemoved);
    }
  }

  Widget _installedMenu(BuildContext context, WidgetRef ref, InstalledPluginInfo p) => PopupMenuButton<String>(
        key: Key('plugin-menu-${p.id}'),
        onSelected: (v) => v == 'update' ? _install(context, ref, url: p.repoUrl) : _remove(context, ref, p),
        itemBuilder: (_) => [
          PopupMenuItem(value: 'update', child: Text(l10n.pluginCheckUpdate)),
          PopupMenuItem(value: 'remove', child: Text(l10n.remove)),
        ],
      );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(adminPluginsProvider);
    final state = ref.watch(installedPluginsProvider).valueOrNull; // the list works without it (older servers)
    final shown = {for (final p in async.valueOrNull ?? const <AdminPlugin>[]) p.id};
    final broken = [for (final i in state?.items ?? const <InstalledPluginInfo>[]) if (!shown.contains(i.id)) i];
    return Scaffold(
      appBar: AppBar(title: Text(l10n.pluginsAccess)),
      floatingActionButton: state != null && !state.enabled
          ? null
          : FloatingActionButton.extended(
              key: const Key('plugin-install-button'),
              onPressed: () => _install(context, ref),
              icon: const Icon(Icons.download_outlined),
              label: Text(l10n.pluginInstall),
            ),
      body: HubRefresh(
        onRefresh: () {
          ref.invalidate(installedPluginsProvider);
          return ref.refresh(adminPluginsProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminPluginsProvider)),
          data: (plugins) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              for (final p in plugins)
                ListTile(
                  key: Key('plugin-${p.id}'),
                  title: Text(p.name),
                  subtitle: Text(
                      [
                        if (state?.byId(p.id) != null) l10n.pluginFromGithub(state!.byId(p.id)!.version),
                        '${_status(p)} · ${p.description}',
                      ].join('\n'),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    Switch(
                      value: !p.disabled,
                      onChanged: (v) => _toggle(context, ref, p, v),
                    ),
                    if (state?.byId(p.id) != null) _installedMenu(context, ref, state!.byId(p.id)!),
                  ]),
                  onTap: () async {
                    final saved = await Navigator.of(context).push<bool>(
                        MaterialPageRoute(builder: (_) => pluginSettingsPage(p)));
                    if (saved == true) {
                      ref.invalidate(adminPluginsProvider);
                      ref.invalidate(adminOverviewProvider);
                      ref.invalidate(modulesProvider);
                    }
                  },
                ),
              if (broken.isNotEmpty) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
                  child: Text(l10n.pluginsNotLoaded, style: Theme.of(context).textTheme.titleSmall),
                ),
                for (final i in broken)
                  ListTile(
                    key: Key('plugin-broken-${i.id}'),
                    leading: Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
                    title: Text(i.name),
                    subtitle: Text(i.error ?? l10n.pluginFromGithub(i.version), maxLines: 4, overflow: TextOverflow.ellipsis),
                    trailing: _installedMenu(context, ref, i),
                  ),
              ],
              if (state != null && !state.enabled)
                Padding(
                  key: const Key('plugin-install-off'),
                  padding: const EdgeInsets.all(16),
                  child: Text(l10n.pluginInstallOff, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Settings page of a plugin; calendar subscriptions get their own list instead of a text field.
Widget pluginSettingsPage(AdminPlugin p) => p.id == 'ics' ? const IcsFeedsScreen() : PluginSettingsScreen(plugin: p);

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
