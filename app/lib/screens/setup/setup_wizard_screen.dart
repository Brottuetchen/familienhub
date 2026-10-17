import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../admin/admin_users_screen.dart' show adminUsersProvider, inviteFlow;
import '../more/plugins_admin_screen.dart' show PluginSettingsScreen;

/// Häufige Zeitzonen; andere lassen sich frei eintragen.
const commonTimezones = [
  'Europe/Berlin', 'Europe/Vienna', 'Europe/Zurich', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Luxembourg',
  'Europe/Paris', 'Europe/London', 'Europe/Rome', 'Europe/Madrid', 'Europe/Warsaw', 'Europe/Stockholm',
];

/// Einrichtungs-Assistent: Grundlagen → Dienste → Familie → Fertig.
/// Nach dem ersten Admin automatisch; später unter Verwaltung erneut aufrufbar ([standalone]).
class SetupWizardScreen extends ConsumerStatefulWidget {
  final bool standalone;
  const SetupWizardScreen({super.key, this.standalone = false});

  @override
  ConsumerState<SetupWizardScreen> createState() => _SetupWizardScreenState();
}

class _SetupWizardScreenState extends ConsumerState<SetupWizardScreen> {
  static const steps = ['Grundlagen', 'Dienste', 'Familie', 'Fertig'];
  int _step = 0;
  final _appName = TextEditingController();
  final _timezone = TextEditingController();
  bool _loaded = false;
  bool _saving = false;

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
    if (_step == steps.length - 1) {
      _finish();
      return;
    }
    setState(() => _step++);
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
        title: const Text('Einrichtung'),
        automaticallyImplyLeading: widget.standalone,
        actions: [
          if (_step < steps.length - 1)
            TextButton(key: const Key('wizard-skip'), onPressed: _finish, child: const Text('Später')),
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
            1 => const _ServicesStep(),
            2 => const _FamilyStep(),
            _ => const _DoneStep(),
          },
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              if (_step > 0)
                TextButton(onPressed: () => setState(() => _step--), child: const Text('Zurück')),
              const Spacer(),
              FilledButton(
                key: const Key('wizard-next'),
                onPressed: _saving || (_step == 0 && !_loaded) ? null : _next,
                child: Text(_step == steps.length - 1 ? 'Los geht’s' : 'Weiter'),
              ),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget _basics() => ListView(padding: const EdgeInsets.all(16), children: [
        Text('Wie soll dein Hub heißen?', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          key: const Key('wizard-app-name'),
          controller: _appName,
          maxLength: 40,
          decoration: const InputDecoration(labelText: 'Name', helperText: 'z. B. „Familie Beispiel“'),
        ),
        const SizedBox(height: 16),
        Text('Zeitzone', style: Theme.of(context).textTheme.titleMedium),
        const Text('Für Erinnerungen, Fälligkeiten und „Heute“.'),
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
              decoration: const InputDecoration(labelText: 'Zeitzone', hintText: 'Europe/Berlin'),
            );
          },
        ),
      ]);
}

/// Dienste: alle Plugins mit Status; „Einrichten“ öffnet die Zugänge mit „Verbindung testen“.
class _ServicesStep extends ConsumerWidget {
  const _ServicesStep();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plugins = ref.watch(adminPluginsProvider);
    return plugins.when(
      loading: () => const Center(child: HubLoader()),
      error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminPluginsProvider)),
      data: (list) => ListView(padding: const EdgeInsets.symmetric(vertical: 8), children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Text('Welche Dienste nutzt ihr? Richte ein, was ihr habt – alles andere bleibt aus '
              'und lässt sich später unter Verwaltung → Plugins nachholen.'),
        ),
        for (final p in list)
          ListTile(
            key: Key('wizard-plugin-${p.id}'),
            leading: Icon(p.active ? Icons.check_circle : Icons.radio_button_unchecked,
                color: p.active ? Colors.green : null),
            title: Text(p.name),
            subtitle: Text(p.description, maxLines: 2, overflow: TextOverflow.ellipsis),
            trailing: Text(p.active ? 'Eingerichtet' : 'Einrichten'),
            onTap: () async {
              final saved = await Navigator.of(context)
                  .push<bool>(MaterialPageRoute(builder: (_) => PluginSettingsScreen(plugin: p)));
              if (saved == true) ref.invalidate(adminPluginsProvider);
            },
          ),
      ]),
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
      const Text('Wer gehört dazu? Lade jede Person ein: Sie bekommt einen Text mit App, Server-Adresse und einem Code, '
          'mit dem sie ihr eigenes Passwort festlegt. Mit einem Anmeldedienst wie Authentik meldet sie sich einfach mit '
          'derselben E-Mail-Adresse an.'),
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
          label: const Text('Person einladen'),
        ),
      ),
    ]);
  }
}

/// Fertig: kurze Zusammenfassung, was läuft.
class _DoneStep extends ConsumerWidget {
  const _DoneStep();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plugins = ref.watch(adminPluginsProvider).valueOrNull ?? const <AdminPlugin>[];
    final active = [for (final p in plugins) if (p.active) p.name];
    final theme = Theme.of(context);
    return ListView(padding: const EdgeInsets.all(24), children: [
      Icon(Icons.celebration_outlined, size: 56, color: theme.colorScheme.primary),
      const SizedBox(height: 12),
      Text('Fertig eingerichtet', textAlign: TextAlign.center, style: theme.textTheme.headlineSmall),
      const SizedBox(height: 12),
      Text(
        active.isEmpty
            ? 'Noch keine Dienste verbunden – Termine, Erinnerungen und Essensplan funktionieren trotzdem.'
            : 'Verbunden: ${active.join(', ')}.',
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 12),
      const Text(
        'Alles lässt sich später unter Mehr → Verwaltung ändern. Push-Mitteilungen brauchen ein Firebase-Projekt '
        '(siehe Betriebsanleitung).',
        textAlign: TextAlign.center,
      ),
    ]);
  }
}
