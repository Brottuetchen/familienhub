import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/admin.dart' show ConnectionResult;
import '../../models/plugin_install.dart' show PluginSettingSpec;
import '../../models/plugin_user.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'plugins_admin_screen.dart' show ConnectionResultCard;

/// Active plugins that need settings of their own for each person (`/api/plugins/personal-settings`).
/// Errors (older server, offline) leave the list empty, so *More* simply shows no entry.
final personalPluginsProvider = FutureProvider.autoDispose<List<PersonalPlugin>>((ref) async {
  ref.watch(sessionScopeProvider);
  try {
    return await ref.watch(apiClientProvider).personalPlugins();
  } catch (_) {
    return const [];
  }
});

/// *More → My connections*: one entry per plugin, each opens its form.
class ConnectionsScreen extends ConsumerWidget {
  const ConnectionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(personalPluginsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.myConnections)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(personalPluginsProvider.future),
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(personalPluginsProvider)),
          data: (plugins) => plugins.isEmpty
              ? ListView(physics: const AlwaysScrollableScrollPhysics(), children: [
                  Padding(padding: const EdgeInsets.all(24), child: Text(l10n.myConnectionsEmpty, key: const Key('connections-empty'))),
                ])
              : ListView(physics: const AlwaysScrollableScrollPhysics(), children: [
                  for (final p in plugins)
                    ListTile(
                      key: Key('connection-${p.id}'),
                      leading: Icon(p.needsSetup ? Icons.link_off : Icons.link),
                      title: Text(p.name),
                      subtitle: Text(p.needsSetup ? l10n.myConnectionNotSet : l10n.myConnectionSet),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () async {
                        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PersonalSettingsScreen(plugin: p)));
                        ref.invalidate(personalPluginsProvider);
                      },
                    ),
                ]),
        ),
      ),
    );
  }
}

/// One field of a plugin's settings form, built from the manifest's spec. The same widgets as the install form
/// (text, address, number, secret, switch).
class PluginSettingField extends StatelessWidget {
  final PluginSettingSpec spec;
  final TextEditingController? controller;
  final bool flag;
  final ValueChanged<bool>? onFlag;
  final VoidCallback? onChanged;

  const PluginSettingField({super.key, required this.spec, this.controller, this.flag = false, this.onFlag, this.onChanged});

  String get _helper => [
        if (spec.secret && spec.isSet) l10n.savedKeepEmpty else if (spec.help.isNotEmpty) spec.help,
        if (spec.example.isNotEmpty) l10n.pluginExample(spec.example),
      ].join('\n');

  /// Error text for the typed value, or null.
  static String? validate(PluginSettingSpec s, String? raw) {
    final v = (raw ?? '').trim();
    if (v.isEmpty) {
      final hasValue = s.isSet || (s.defaultValue ?? '').isNotEmpty;
      return s.required && !hasValue ? l10n.pluginFieldRequired : null;
    }
    if (s.type == 'url' && !RegExp(r'^https?://\S+$').hasMatch(v)) return l10n.pluginFieldUrl;
    if (s.type == 'number' && double.tryParse(v) == null) return l10n.pluginFieldNumber;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    if (spec.type == 'bool') {
      return SwitchListTile(
        key: Key('field-${spec.key}'),
        contentPadding: EdgeInsets.zero,
        value: flag,
        title: Text(spec.label),
        subtitle: _helper.isEmpty ? null : Text(_helper),
        onChanged: onFlag,
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: Key('field-${spec.key}'),
        controller: controller,
        obscureText: spec.secret,
        autocorrect: !spec.secret && spec.type == 'text',
        enableSuggestions: !spec.secret,
        keyboardType: switch (spec.type) {
          'url' => TextInputType.url,
          'number' => const TextInputType.numberWithOptions(decimal: true, signed: true),
          _ => TextInputType.text,
        },
        decoration: InputDecoration(
          labelText: spec.required ? '${spec.label} *' : spec.label,
          helperText: _helper.isEmpty ? null : _helper,
          helperMaxLines: 4,
        ),
        validator: (v) => validate(spec, v),
        onChanged: (_) => onChanged?.call(),
      ),
    );
  }
}

/// A person's own settings of one plugin. Secrets are never shown; leave empty to keep the stored one.
class PersonalSettingsScreen extends ConsumerStatefulWidget {
  final PersonalPlugin plugin;
  const PersonalSettingsScreen({super.key, required this.plugin});

  @override
  ConsumerState<PersonalSettingsScreen> createState() => _PersonalSettingsScreenState();
}

class _PersonalSettingsScreenState extends ConsumerState<PersonalSettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _text = {
    for (final f in widget.plugin.fields)
      if (f.type != 'bool') f.key: TextEditingController(text: f.secret ? '' : f.value),
  };
  late final Map<String, bool> _flags = {
    for (final f in widget.plugin.fields)
      if (f.type == 'bool') f.key: f.value == 'true',
  };
  bool _saving = false;
  bool _testing = false;
  ConnectionResult? _result;

  @override
  void dispose() {
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, String> _values() => {
        for (final f in widget.plugin.fields)
          f.key: f.type == 'bool' ? ((_flags[f.key] ?? false) ? 'true' : 'false') : _text[f.key]!.text.trim(),
      };

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).savePersonalSettings(widget.plugin.id, _values()));
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      showInfo(context, l10n.saved);
      Navigator.pop(context, true);
    }
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _result = null;
    });
    try {
      final r = await ref.read(apiClientProvider).testPersonalSettings(widget.plugin.id, _values());
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.plugin;
    return Scaffold(
      appBar: AppBar(title: Text(p.name)),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
          children: [
            if (p.description.isNotEmpty) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(p.description)),
            for (final f in p.fields)
              PluginSettingField(
                spec: f,
                controller: _text[f.key],
                flag: _flags[f.key] ?? false,
                onFlag: (v) => setState(() => _flags[f.key] = v),
                onChanged: () {
                  if (_result != null) setState(() => _result = null); // an old result no longer fits
                },
              ),
            if (p.hasTest)
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  key: const Key('connection-test'),
                  onPressed: _testing ? null : _test,
                  icon: _testing ? const HubLoader(size: 18) : const Icon(Icons.network_check),
                  label: Text(l10n.testConnection),
                ),
              ),
            if (_result != null) ConnectionResultCard(result: _result!),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('connection-save'),
        onPressed: _saving ? null : _save,
        icon: const Icon(Icons.save_outlined),
        label: Text(l10n.save),
      ),
    );
  }
}
