import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/admin.dart' show ConnectionResult;
import '../../models/plugin_install.dart';
import '../../models/store.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';

/// Which plugins were installed from GitHub, and whether the operator allows installing at all.
final installedPluginsProvider = FutureProvider.autoDispose<PluginInstallState>(
    (ref) => ref.watch(apiClientProvider).pluginInstallState());

enum _Step { link, review, form, done }

/// Administration → Plugins & access → Install plugin: paste a link, review what the plugin is and what it
/// needs, fill in the settings the plugin asks for (generated from its manifest), install.
/// With [initialUrl] (update) the link is checked right away.
/// With [storeItem] the same review and form run for a store entry at the commit its index pins; the link step
/// is skipped ([acknowledgedUnverified]: the admin confirmed the warning of an unreviewed source).
class PluginInstallScreen extends ConsumerStatefulWidget {
  final String? initialUrl;
  final StoreItem? storeItem;
  final bool acknowledgedUnverified;
  const PluginInstallScreen({super.key, this.initialUrl, this.storeItem, this.acknowledgedUnverified = false});

  @override
  ConsumerState<PluginInstallScreen> createState() => _PluginInstallScreenState();
}

class _PluginInstallScreenState extends ConsumerState<PluginInstallScreen> {
  final _url = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  final Map<String, TextEditingController> _text = {};
  final Map<String, bool> _flags = {};
  _Step _step = _Step.link;
  PluginPreview? _preview;
  PluginInstallResult? _result;
  bool _busy = false;
  bool _trusted = false;
  String? _error;
  ConnectionResult? _test; // result of "Test connection" in the form (an installed plugin only)
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    final url = widget.initialUrl;
    if (widget.storeItem != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _inspect());
    } else if (url != null && url.isNotEmpty) {
      _url.text = url;
      WidgetsBinding.instance.addPostFrameCallback((_) => _inspect());
    }
  }

  @override
  void dispose() {
    _url.dispose();
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _inspect() async {
    final url = _url.text.trim();
    final item = widget.storeItem;
    if (url.isEmpty && item == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final preview = item != null ? await api.storeInspectPlugin(item) : await api.inspectPlugin(url);
      if (!mounted) return;
      for (final c in _text.values) {
        c.dispose();
      }
      _text.clear();
      _flags.clear();
      for (final s in preview.settings) {
        final initial = s.secret ? '' : (s.value.isNotEmpty ? s.value : (s.defaultValue ?? ''));
        if (s.type == 'bool') {
          _flags[s.key] = initial == 'true';
        } else {
          _text[s.key] = TextEditingController(text: initial);
        }
      }
      setState(() {
        _preview = preview;
        _trusted = false;
        _step = _Step.review;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _afterReview() {
    final p = _preview!;
    if (p.settings.isEmpty) {
      _install();
    } else {
      setState(() => _step = _Step.form);
    }
  }

  String? _validate(PluginSettingSpec s, String? raw) {
    final v = (raw ?? '').trim();
    if (v.isEmpty) {
      final hasValue = s.isSet || (s.defaultValue ?? '').isNotEmpty;
      return s.required && !hasValue ? l10n.pluginFieldRequired : null;
    }
    if (s.type == 'url' && !RegExp(r'^https?://\S+$').hasMatch(v)) return l10n.pluginFieldUrl;
    if (s.type == 'number' && double.tryParse(v) == null) return l10n.pluginFieldNumber;
    return null;
  }

  Map<String, String> _values(PluginPreview p) => {
        for (final s in p.settings)
          s.key: s.type == 'bool' ? ((_flags[s.key] ?? false) ? 'true' : 'false') : (_text[s.key]?.text.trim() ?? ''),
      };

  /// "Test connection" with the entered values, nothing saved. Only for a plugin that is already installed
  /// (an update): a new plugin's code is not loaded yet, so it is tested right after installing instead.
  Future<void> _testConnection() async {
    final p = _preview!;
    setState(() {
      _testing = true;
      _test = null;
    });
    try {
      final result = await ref.read(apiClientProvider).testPlugin(p.id, _values(p));
      if (mounted) setState(() => _test = result);
    } catch (e) {
      if (mounted) setState(() => _test = ConnectionResult(ok: false, level: 'error', message: errorText(e)));
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _install() async {
    final p = _preview!;
    if (_step == _Step.form && !(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final values = _values(p);
    try {
      final api = ref.read(apiClientProvider);
      final item = widget.storeItem;
      final result = item != null
          ? PluginInstallResult.fromJson(await api.storeInstall(item, p.sha,
              settings: values, acknowledgeUnverified: widget.acknowledgedUnverified))
          : await api.installPlugin(p.url, p.sha, values);
      if (!mounted) return;
      ref.invalidate(adminPluginsProvider);
      ref.invalidate(installedPluginsProvider);
      ref.invalidate(modulesProvider);
      setState(() {
        _result = result;
        _step = _Step.done;
      });
    } on OfflineException {
      // The connection (or a proxy in front of the hub) gave up; the server may still be installing
      ref.invalidate(installedPluginsProvider);
      if (mounted) setState(() => _error = l10n.pluginInstallNoAnswer);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(l10n.pluginInstall)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: switch (_step) {
          _Step.link => widget.storeItem != null ? _storeLoadingStep(context) : _linkStep(context),
          _Step.review => _reviewStep(context),
          _Step.form => _formStep(context),
          _Step.done => _doneStep(context),
        },
      ),
    );
  }

  Widget _errorBox(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      key: const Key('plugin-error'),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.error.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.error.withValues(alpha: 0.5)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.error_outline, color: scheme.error),
        const SizedBox(width: 10),
        Expanded(child: SelectableText(_error!)),
      ]),
    );
  }

  /// Outcome of a connection test: green when it worked, a hint (amber) or an error (red) otherwise.
  Widget _testBox(BuildContext context, ConnectionResult r) {
    final scheme = Theme.of(context).colorScheme;
    final color = r.ok ? (r.level == 'info' ? Colors.amber : Colors.green) : scheme.error;
    return Container(
      key: const Key('plugin-test-result'),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(r.ok ? Icons.check_circle_outline : Icons.error_outline, color: color),
        const SizedBox(width: 10),
        Expanded(child: SelectableText(r.message)),
      ]),
    );
  }

  Widget _busyBar() => const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Center(child: HubLoader()));

  /// Store entry: no link to paste; the pinned commit is being read (or reading it failed).
  List<Widget> _storeLoadingStep(BuildContext context) => [
        if (_error != null) ...[
          _errorBox(context),
          const SizedBox(height: 16),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.tonal(onPressed: _busy ? null : _inspect, child: Text(l10n.retry)),
          ),
        ] else
          _busyBar(),
      ];

  List<Widget> _linkStep(BuildContext context) => [
        Padding(padding: const EdgeInsets.only(top: 8, bottom: 16), child: Text(l10n.pluginLinkHint)),
        TextField(
          key: const Key('plugin-url'),
          controller: _url,
          autofocus: true,
          keyboardType: TextInputType.url,
          autocorrect: false,
          enabled: !_busy,
          decoration: InputDecoration(labelText: l10n.githubAddress, hintText: 'https://github.com/name/repo'),
          onSubmitted: (_) => _inspect(),
        ),
        if (_error != null) _errorBox(context),
        const SizedBox(height: 16),
        if (_busy)
          _busyBar()
        else
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.icon(
              key: const Key('plugin-inspect'),
              onPressed: _inspect,
              icon: const Icon(Icons.search),
              label: Text(l10n.pluginCheck),
            ),
          ),
      ];

  Widget _info(BuildContext context, IconData icon, String title, String body) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: Theme.of(context).textTheme.labelLarge),
            Text(body, style: muted),
          ]),
        ),
      ]),
    );
  }

  List<Widget> _reviewStep(BuildContext context) {
    final p = _preview!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final needsForm = p.settings.isNotEmpty;
    final Widget? installedNote = !p.isInstalled
        ? null
        : p.sameSha
            ? Text(l10n.pluginSameCommit, key: const Key('plugin-same-commit'))
            : Text(l10n.pluginUpdateFrom(p.installedVersion!, p.version), key: const Key('plugin-update-note'));
    return [
      Padding(
        key: const Key('plugin-review'),
        padding: const EdgeInsets.only(top: 8),
        child: Text(p.name, style: theme.textTheme.headlineSmall),
      ),
      Text(
        [
          if (p.author.isNotEmpty) l10n.pluginBy(p.author),
          l10n.pluginVersionCommit(p.version, p.shortSha),
          if (p.license.isNotEmpty) p.license,
        ].join(' · '),
        style: TextStyle(color: scheme.onSurfaceVariant),
      ),
      if (installedNote != null)
        Padding(padding: const EdgeInsets.only(top: 12), child: installedNote),
      if (p.description.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 12), child: Text(p.description)),
      const SizedBox(height: 8),
      _info(context, Icons.source_outlined, l10n.pluginRepository, '${p.repoUrl} · ${p.shortSha}'),
      _info(context, Icons.public, l10n.pluginHosts, p.hosts.isEmpty ? l10n.pluginNoHosts : p.hosts.join(', ')),
      if (p.capabilities.isNotEmpty) _info(context, Icons.extension_outlined, l10n.pluginProvides, p.capabilities.join(', ')),
      for (final w in p.warnings)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.info_outline, size: 20, color: Colors.amber),
            const SizedBox(width: 12),
            Expanded(child: Text(w)),
          ]),
        ),
      Container(
        key: const Key('plugin-warning'),
        margin: const EdgeInsets.only(top: 16),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: scheme.error.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.error.withValues(alpha: 0.5)),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.warning_amber_rounded, color: scheme.error),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(l10n.pluginWarningTitle, style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              Text(l10n.pluginWarningBody),
            ]),
          ),
        ]),
      ),
      CheckboxListTile(
        key: const Key('plugin-trust'),
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: _trusted,
        title: Text(l10n.pluginTrust),
        onChanged: _busy ? null : (v) => setState(() => _trusted = v == true),
      ),
      if (_error != null) _errorBox(context),
      const SizedBox(height: 12),
      if (_busy)
        Column(children: [_busyBar(), Text(l10n.pluginInstalling, textAlign: TextAlign.center)])
      else
        Row(children: [
          TextButton(
              onPressed: () =>
                  widget.storeItem != null ? Navigator.of(context).maybePop() : setState(() => _step = _Step.link),
              child: Text(l10n.back)),
          const Spacer(),
          if (!p.installEnabled)
            Flexible(child: Text(l10n.pluginInstallOff, textAlign: TextAlign.end))
          else
            FilledButton(
              key: const Key('plugin-continue'),
              onPressed: _trusted ? _afterReview : null,
              child: Text(needsForm ? l10n.next : l10n.install),
            ),
        ]),
    ];
  }

  Widget _field(PluginSettingSpec s) {
    final helper = [
      if (s.secret && s.isSet) l10n.savedKeepEmpty else if (s.help.isNotEmpty) s.help,
      if (s.example.isNotEmpty) l10n.pluginExample(s.example),
    ].join('\n');
    if (s.type == 'bool') {
      return SwitchListTile(
        key: Key('plugin-field-${s.key}'),
        contentPadding: EdgeInsets.zero,
        value: _flags[s.key] ?? false,
        title: Text(s.label),
        subtitle: helper.isEmpty ? null : Text(helper),
        onChanged: _busy ? null : (v) => setState(() => _flags[s.key] = v),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: Key('plugin-field-${s.key}'),
        controller: _text[s.key],
        enabled: !_busy,
        obscureText: s.secret,
        autocorrect: !s.secret && s.type == 'text',
        enableSuggestions: !s.secret,
        keyboardType: switch (s.type) {
          'url' => TextInputType.url,
          'number' => const TextInputType.numberWithOptions(decimal: true, signed: true),
          _ => TextInputType.text,
        },
        decoration: InputDecoration(
          labelText: s.required ? '${s.label} *' : s.label,
          helperText: helper.isEmpty ? null : helper,
          helperMaxLines: 4,
        ),
        validator: (v) => _validate(s, v),
      ),
    );
  }

  List<Widget> _formStep(BuildContext context) {
    final p = _preview!;
    return [
      Padding(
        key: const Key('plugin-form'),
        padding: const EdgeInsets.only(top: 8, bottom: 12),
        child: Text(l10n.pluginSettingsHeading(p.name), style: Theme.of(context).textTheme.titleMedium),
      ),
      Form(key: _formKey, child: Column(children: [for (final s in p.settings) _field(s)])),
      if (p.isInstalled)
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            key: const Key('plugin-test'),
            onPressed: _busy || _testing ? null : _testConnection,
            icon: _testing
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.network_check),
            label: Text(l10n.testConnection),
          ),
        ),
      if (_test != null) _testBox(context, _test!),
      if (_error != null) _errorBox(context),
      const SizedBox(height: 12),
      if (_busy)
        Column(children: [_busyBar(), Text(l10n.pluginInstalling, textAlign: TextAlign.center)])
      else
        Row(children: [
          TextButton(onPressed: () => setState(() => _step = _Step.review), child: Text(l10n.back)),
          const Spacer(),
          FilledButton.icon(
            key: const Key('plugin-install'),
            onPressed: _install,
            icon: const Icon(Icons.download_outlined),
            label: Text(l10n.install),
          ),
        ]),
    ];
  }

  List<Widget> _doneStep(BuildContext context) {
    final p = _preview!;
    final r = _result!;
    final theme = Theme.of(context);
    return [
      const SizedBox(height: 24),
      Icon(Icons.check_circle_outline, size: 56, color: theme.colorScheme.primary),
      const SizedBox(height: 12),
      Text(
        r.updated ? l10n.pluginUpdated(p.name) : l10n.pluginInstalled(p.name),
        key: const Key('plugin-result'),
        textAlign: TextAlign.center,
        style: theme.textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      Text(r.active ? l10n.pluginActiveNow : l10n.pluginNeedsSetup, textAlign: TextAlign.center),
      if (r.connectionTest != null) ...[
        _testBox(context, r.connectionTest!),
        if (!r.connectionTest!.ok)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(l10n.pluginTestFailedHint, key: const Key('plugin-test-hint'), textAlign: TextAlign.center),
          ),
      ],
      if (r.restartRequired)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(l10n.pluginRestartNeeded, key: const Key('plugin-restart'), textAlign: TextAlign.center),
        ),
      const SizedBox(height: 24),
      Center(
        child: FilledButton(
          key: const Key('plugin-done'),
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(l10n.close),
        ),
      ),
    ];
  }
}
