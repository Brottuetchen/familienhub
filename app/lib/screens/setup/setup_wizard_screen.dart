import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../admin/admin_users_screen.dart' show adminUsersProvider, inviteFlow;
import '../more/plugins_admin_screen.dart' show pluginSettingsPage;
import '../../l10n/l10n.dart';
import '../admin/sources_screen.dart';

/// Häufige Zeitzonen; andere lassen sich frei eintragen.
const commonTimezones = [
  'Europe/Berlin', 'Europe/Vienna', 'Europe/Zurich', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Luxembourg',
  'Europe/Paris', 'Europe/London', 'Europe/Rome', 'Europe/Madrid', 'Europe/Warsaw', 'Europe/Stockholm',
];

/// Setup wizard: basics → areas (where data lives) → services → family → done.
/// Nach dem ersten Admin automatisch; später unter Verwaltung erneut aufrufbar ([standalone]).
class SetupWizardScreen extends ConsumerStatefulWidget {
  final bool standalone;
  const SetupWizardScreen({super.key, this.standalone = false});

  @override
  ConsumerState<SetupWizardScreen> createState() => _SetupWizardScreenState();
}

class _SetupWizardScreenState extends ConsumerState<SetupWizardScreen> {
  static List<String> get steps => [l10n.stepBasics, l10n.stepAreas, l10n.stepServices, l10n.family, l10n.finished];
  int _step = 0;

  /// Per area: ids of the chosen sources ('hub' stands for the hub's own source). Saved after the services step.
  Map<String, Set<String>>? _wanted;
  final _appName = TextEditingController();
  final _timezone = TextEditingController();
  bool _loaded = false;
  bool _saving = false;

  /// Services ticked in the services step (null until it has loaded): they stay on when the wizard ends.
  Set<String>? _use;

  Set<String> get _wantedIds => {for (final ids in (_wanted ?? const <String, Set<String>>{}).values) ...ids};

  @override
  void initState() {
    super.initState();
    ref.read(apiClientProvider).coreSettings().then((c) {
      if (!mounted) return;
      setState(() {
        _appName.text = c.appName;
        _timezone.text = c.timezone;
        _loaded = true;
      });
    }).catchError((Object _) {
      if (mounted) setState(() => _loaded = true);
    });
  }

  @override
  void dispose() {
    _appName.dispose();
    _timezone.dispose();
    super.dispose();
  }

  Future<void> _next() async {
    if (_step == 0) {
      setState(() => _saving = true);
      final ok = await runAction(context, () => ref.read(apiClientProvider).saveCoreSettings(
            appName: _appName.text.trim().isEmpty ? 'Familienhub' : _appName.text.trim(),
            timezone: _timezone.text.trim(),
          ));
      if (!mounted) return;
      setState(() => _saving = false);
      if (!ok) return;
    }
    if (_step == 2 && !await _applySources()) return;
    if (_step == steps.length - 1) {
      await _applyResult();
      if (mounted) _finish();
      return;
    }
    setState(() => _step++);
  }

  /// After the services step: chosen sources that are now set up, otherwise the hub.
  Future<bool> _applySources() async {
    final wanted = _wanted;
    if (wanted == null) return true;
    final api = ref.read(apiClientProvider);
    setState(() => _saving = true);
    try {
      ref.invalidate(adminSourcesProvider);
      final areas = await ref.read(adminSourcesProvider.future);
      final missing = <String>{};
      for (final area in areas) {
        final want = wanted[area.area] ?? const {'hub'};
        final hub = area.sources.where((s) => s.fallback).map((s) => s.id).firstOrNull;
        final ready = [for (final s in area.sources) if (!s.fallback && want.contains(s.id) && s.configured && s.active) s.id];
        missing.addAll([for (final s in area.sources) if (!s.fallback && want.contains(s.id) && !(s.configured && s.active)) s.name]);
        var selected = [if (want.contains('hub') && hub != null) hub, ...ready];
        if (!area.multiple && selected.length > 1) selected = [ready.isNotEmpty ? ready.first : selected.first];
        if (selected.isEmpty && hub != null) selected = [hub];
        await api.setSources(area.area, selected);
      }
      ref.invalidate(modulesProvider);
      ref.invalidate(taskAccountsProvider);
      if (missing.isNotEmpty && mounted) showInfo(context, l10n.notSetUpStaysInHub(missing.join(', ')));
      return true;
    } catch (e) {
      if (mounted) showError(context, e);
      return false;
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  /// Last step: ticked services that are switched off go on again. First run: active plugins that were not ticked
  /// and serve no area are switched off (reversible under Administration → Plugins & access). Re-runs only switch
  /// off what the admin unticked, never what was set up earlier and left alone. Fails softly: the hub works either way.
  Future<void> _applyResult() async {
    final use = _use;
    if (widget.standalone && use == null) return;
    setState(() => _saving = true);
    try {
      final api = ref.read(apiClientProvider);
      final plugins = ref.read(adminPluginsProvider).valueOrNull ?? const <AdminPlugin>[];
      final wanted = _wantedIds;
      for (final p in plugins) {
        if (use != null && use.contains(p.id) && p.disabled && p.configured) await api.setPluginEnabled(p.id, true);
        if (widget.standalone && p.active && !use!.contains(p.id) && !wanted.contains(p.id)) {
          await api.setPluginEnabled(p.id, false);
        }
      }
      if (!widget.standalone) await api.finishSetup((use ?? const <String>{}).toList());
      ref.invalidate(adminPluginsProvider);
    } catch (_) {
      if (mounted) showInfo(context, l10n.unusedNotSwitchedOff);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _finish() {
    ref.invalidate(modulesProvider);
    if (widget.standalone) {
      Navigator.of(context).pop();
    } else {
      ref.read(sessionProvider.notifier).finishOnboarding();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.setup),
        automaticallyImplyLeading: widget.standalone,
        actions: [
          if (_step < steps.length - 1)
            TextButton(key: const Key('wizard-skip'), onPressed: _finish, child: Text(l10n.later)),
        ],
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Row(children: [
            for (final (i, s) in steps.indexed)
              Expanded(
                child: Column(children: [
                  Container(
                    height: 4,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    color: i <= _step ? theme.colorScheme.primary : theme.colorScheme.surfaceContainerHighest,
                  ),
                  const SizedBox(height: 4),
                  Text(s, style: theme.textTheme.labelSmall?.copyWith(
                      fontWeight: i == _step ? FontWeight.w700 : FontWeight.w400)),
                ]),
              ),
          ]),
        ),
        Expanded(
          child: switch (_step) {
            0 => _basics(),
            1 => _AreasStep(wanted: _wanted, onChanged: (w) => setState(() => _wanted = w)),
            2 => _ServicesStep(
                wanted: _wantedIds,
                standalone: widget.standalone,
                use: _use,
                onInit: (use) => setState(() => _use ??= use),
                onToggle: (id, on) => setState(() => on ? (_use ??= {}).add(id) : _use?.remove(id)),
              ),
            3 => const _FamilyStep(),
            _ => _DoneStep(use: _use),
          },
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              if (_step > 0)
                TextButton(onPressed: () => setState(() => _step--), child: Text(l10n.back)),
              const Spacer(),
              FilledButton(
                key: const Key('wizard-next'),
                onPressed: _saving || (_step == 0 && !_loaded) ? null : _next,
                child: Text(_step == steps.length - 1 ? l10n.letsGo : l10n.next),
              ),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget _basics() => ListView(padding: const EdgeInsets.all(16), children: [
        Text(l10n.hubNameQuestion, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          key: const Key('wizard-app-name'),
          controller: _appName,
          maxLength: 40,
          decoration: InputDecoration(labelText: l10n.name, helperText: l10n.hubNameHint),
        ),
        const SizedBox(height: 16),
        Text(l10n.timeZone, style: Theme.of(context).textTheme.titleMedium),
        Text(l10n.timeZoneHint),
        const SizedBox(height: 8),
        Autocomplete<String>(
          initialValue: TextEditingValue(text: _timezone.text),
          optionsBuilder: (v) => commonTimezones.where((z) => z.toLowerCase().contains(v.text.toLowerCase())),
          onSelected: (z) => _timezone.text = z,
          fieldViewBuilder: (context, controller, focus, submit) {
            if (controller.text.isEmpty && _timezone.text.isNotEmpty) controller.text = _timezone.text;
            return TextField(
              key: const Key('wizard-timezone'),
              controller: controller,
              focusNode: focus,
              onChanged: (v) => _timezone.text = v,
              decoration: InputDecoration(labelText: l10n.timeZone, hintText: 'Europe/Berlin'),
            );
          },
        ),
      ]);
}

/// Areas: per area "in the hub" and/or services. Nothing is saved here; the services step comes next.
class _AreasStep extends ConsumerWidget {
  final Map<String, Set<String>>? wanted;
  final ValueChanged<Map<String, Set<String>>> onChanged;
  const _AreasStep({required this.wanted, required this.onChanged});

  static String _title(String area) => switch (area) {
        'tasks' => l10n.tabTasks,
        'shopping' => l10n.shoppingList,
        'calendar' => l10n.tabCalendar,
        _ => area,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(adminSourcesProvider);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return async.when(
      loading: () => const Center(child: HubLoader()),
      error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminSourcesProvider)),
      data: (areas) {
        // Start from what is configured now (also when the wizard is run again later)
        final current = wanted ??
            {for (final a in areas) a.area: {for (final s in a.sources) if (s.selected) s.fallback ? 'hub' : s.id}};
        if (wanted == null) WidgetsBinding.instance.addPostFrameCallback((_) => onChanged(current));
        void set(String area, Set<String> ids) => onChanged({...current, area: ids});
        return ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 24), children: [
          Text(l10n.areasQuestion, style: muted),
          for (final a in areas) ...[
            const SizedBox(height: 16),
            Text(_title(a.area), style: Theme.of(context).textTheme.titleMedium),
            CheckboxListTile(
              key: Key('area-${a.area}-hub'),
              contentPadding: EdgeInsets.zero,
              value: (current[a.area] ?? const {}).contains('hub'),
              title: Text(l10n.inTheHub),
              subtitle: Text(l10n.inTheHubHint),
              onChanged: (v) {
                final ids = {...?current[a.area]};
                v == true ? ids.add('hub') : ids.remove('hub');
                if (!a.multiple && v == true) ids.removeWhere((id) => id != 'hub');
                set(a.area, ids);
              },
            ),
            Text(l10n.alsoFrom, style: muted),
            const SizedBox(height: 4),
            Wrap(spacing: 8, runSpacing: 4, children: [
              for (final s in a.sources.where((s) => !s.fallback))
                FilterChip(
                  key: Key('area-${a.area}-${s.id}'),
                  label: Text(s.name),
                  selected: (current[a.area] ?? const {}).contains(s.id),
                  onSelected: (v) {
                    var ids = {...?current[a.area]};
                    if (v) {
                      if (!a.multiple) ids = {};
                      ids.add(s.id);
                    } else {
                      ids.remove(s.id);
                    }
                    if (ids.isEmpty) ids.add('hub'); // never leave an area without a source
                    set(a.area, ids);
                  },
                ),
            ]),
          ],
        ]);
      },
    );
  }
}

/// Services: the ones chosen in "areas" first, then the optional ones. The tick decides whether a service stays on;
/// tapping opens its settings. Zero-config services (weather, CalDAV) start unticked unless the admin set them up.
class _ServicesStep extends ConsumerWidget {
  final Set<String> wanted;
  final bool standalone;
  final Set<String>? use;
  final ValueChanged<Set<String>> onInit;
  final void Function(String id, bool on) onToggle;
  const _ServicesStep(
      {this.wanted = const {}, this.standalone = false, required this.use, required this.onInit, required this.onToggle});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plugins = ref.watch(adminPluginsProvider);
    return plugins.when(
      loading: () => const Center(child: HubLoader()),
      error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminPluginsProvider)),
      data: (all) {
        // Re-run: start from what is on now. First run: what was chosen in "areas" or set up already.
        final current = use ??
            {for (final p in all) if (standalone ? p.active : wanted.contains(p.id) || (p.setUp && p.active)) p.id};
        if (use == null) WidgetsBinding.instance.addPostFrameCallback((_) => onInit(current));
        final chosen = [for (final p in all) if (wanted.contains(p.id)) p];
        final others = [for (final p in all) if (!wanted.contains(p.id)) p];
        Widget header(String text) => Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4), child: Text(text, style: Theme.of(context).textTheme.titleSmall));
        return ListView(padding: const EdgeInsets.symmetric(vertical: 8), children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Text(l10n.servicesQuestion),
        ),
        if (chosen.isNotEmpty) header(l10n.forYourChoice),
        for (final p in chosen) _tile(context, ref, p, current),
        if (chosen.isNotEmpty && others.isNotEmpty) header(l10n.moreServices),
        for (final p in others) _tile(context, ref, p, current),
      ]);
      },
    );
  }

  Widget _tile(BuildContext context, WidgetRef ref, AdminPlugin p, Set<String> current) {
    Future<void> openSettings() async {
      final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => pluginSettingsPage(p)));
      if (saved == true) {
        onToggle(p.id, true);
        ref.invalidate(adminPluginsProvider);
        ref.invalidate(adminSourcesProvider);
      }
    }

    return ListTile(
      key: Key('wizard-plugin-${p.id}'),
      leading: Checkbox(
        key: Key('wizard-use-${p.id}'),
        value: current.contains(p.id),
        onChanged: (v) {
          if (v == true && !p.configured) {
            openSettings(); // ticked once it is set up
          } else {
            onToggle(p.id, v == true);
          }
        },
      ),
      title: Text(p.name),
      subtitle: Text(p.description, maxLines: 2, overflow: TextOverflow.ellipsis),
      trailing: Text(p.setUp ? l10n.configured : l10n.setUp),
      onTap: openSettings,
    );
  }
}

/// Familie: vorhandene Personen und „Person anlegen“ (bei OIDC meist unnötig).
class _FamilyStep extends ConsumerWidget {
  const _FamilyStep();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final users = ref.watch(adminUsersProvider);
    return ListView(padding: const EdgeInsets.all(16), children: [
      Text(l10n.familyQuestion),
      const SizedBox(height: 12),
      ...users.when(
        loading: () => [const Center(child: HubLoader())],
        error: (e, _) => [ErrorView(error: e, onRetry: () => ref.invalidate(adminUsersProvider))],
        data: (list) => [
          for (final u in list)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.person_outline),
              title: Text(u.displayName),
              subtitle: Text('${u.username} · ${roleLabels[u.role] ?? u.role}'),
            ),
        ],
      ),
      const SizedBox(height: 8),
      Align(
        alignment: Alignment.centerLeft,
        child: OutlinedButton.icon(
          key: const Key('wizard-add-person'),
          onPressed: () => inviteFlow(context, ref),
          icon: const Icon(Icons.mail_outline),
          label: Text(l10n.invitePerson),
        ),
      ),
    ]);
  }
}

/// Fertig: kurze Zusammenfassung, was läuft.
class _DoneStep extends ConsumerWidget {
  final Set<String>? use;
  const _DoneStep({this.use});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plugins = ref.watch(adminPluginsProvider).valueOrNull ?? const <AdminPlugin>[];
    // What stays on after "Let's go": the ticked services that are set up
    final active = [for (final p in plugins) if (p.configured && (use?.contains(p.id) ?? p.active)) p.name];
    final theme = Theme.of(context);
    return ListView(padding: const EdgeInsets.all(24), children: [
      Icon(Icons.celebration_outlined, size: 56, color: theme.colorScheme.primary),
      const SizedBox(height: 12),
      Text(l10n.setupComplete, textAlign: TextAlign.center, style: theme.textTheme.headlineSmall),
      const SizedBox(height: 12),
      Text(
        active.isEmpty
            ? l10n.noServicesYet
            : l10n.connectedList(active.join(', ')),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 12),
      Text(
        l10n.setupDoneHint,
        textAlign: TextAlign.center,
      ),
    ]);
  }
}
