import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';

/// Text zum Teilen (Messenger, Mail): App, Server-Adresse, Anmeldung bzw. Code.
String inviteText({required InviteInfo invite, required String server}) {
  final until = invite.expiresAt == null ? '' : ' (gültig bis ${DateFormat('d.M.', 'de_DE').format(invite.expiresAt!)})';
  return [
    'Hallo ${invite.displayName}, du bist zu unserem Familienhub eingeladen!',
    '',
    '1. App holen: Android unter $server/downloads/ – iPhone: $server in Safari öffnen und „Zum Home-Bildschirm“ wählen.',
    '2. Server-Adresse in der App: $server',
    if (invite.oidc) '3. „Mit Authentik anmelden“ und mit ${invite.email} anmelden.',
    if (invite.oidc && invite.code != null) '   Ohne Authentik-Konto: „Einladung einlösen“ mit dem Code ${invite.code}$until.',
    if (!invite.oidc && invite.code != null) '3. „Einladung einlösen“ tippen, Code ${invite.code}$until eingeben und ein eigenes Passwort festlegen.',
  ].join('\n');
}

/// Person einladen: Name, E-Mail, Rolle → Einladung mit Code.
class InviteDialog extends ConsumerStatefulWidget {
  const InviteDialog({super.key});

  @override
  ConsumerState<InviteDialog> createState() => _InviteDialogState();
}

class _InviteDialogState extends ConsumerState<InviteDialog> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  String _role = 'partner';
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  bool get _valid => _name.text.trim().isNotEmpty && RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text.trim());

  Future<void> _send() async {
    setState(() => _busy = true);
    try {
      final invite = await ref.read(apiClientProvider)
          .createInvite(displayName: _name.text.trim(), email: _email.text.trim(), role: _role);
      if (mounted) Navigator.pop(context, invite);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showError(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Person einladen'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(key: const Key('invite-name'), controller: _name,
                decoration: const InputDecoration(labelText: 'Name'), onChanged: (_) => setState(() {})),
            TextField(key: const Key('invite-email'), controller: _email, keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'E-Mail', helperText: 'Bei Authentik: dieselbe Adresse wie dort'),
                onChanged: (_) => setState(() {})),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              key: const Key('invite-role'),
              initialValue: _role,
              decoration: const InputDecoration(labelText: 'Rolle'),
              items: [for (final e in roleLabels.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
              onChanged: (v) => setState(() => _role = v ?? 'partner'),
            ),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Abbrechen')),
          FilledButton(key: const Key('invite-send'), onPressed: _busy || !_valid ? null : _send, child: const Text('Einladen')),
        ],
      );
}

/// Ergebnis: Einladungstext zum Kopieren, Code groß.
class InviteResultSheet extends ConsumerWidget {
  final InviteInfo invite;
  const InviteResultSheet({super.key, required this.invite});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return FutureBuilder<String?>(
      future: ref.read(apiClientProvider).store.baseUrl(),
      builder: (context, snap) {
        final text = inviteText(invite: invite, server: snap.data ?? '');
        return ListView(shrinkWrap: true, padding: const EdgeInsets.all(20), children: [
          Text('Einladung für ${invite.displayName}', style: theme.textTheme.titleLarge),
          const SizedBox(height: 12),
          if (invite.code != null)
            SelectableText(invite.code!, key: const Key('invite-code'), textAlign: TextAlign.center,
                style: theme.textTheme.headlineSmall?.copyWith(letterSpacing: 2, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerHigh, borderRadius: BorderRadius.circular(12)),
            child: SelectableText(text, key: const Key('invite-text')),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            key: const Key('invite-copy'),
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: text));
              if (context.mounted) showInfo(context, 'Einladung kopiert – jetzt z. B. per Messenger schicken');
            },
            icon: const Icon(Icons.copy),
            label: const Text('Text kopieren'),
          ),
          const SizedBox(height: 8),
          const Text('Der Code wird nur jetzt angezeigt. Verloren? In der Familienliste einen neuen erzeugen.'),
        ]);
      },
    );
  }
}

/// Login-Seite: Einladungscode einlösen und eigenes Passwort festlegen.
class AcceptInviteScreen extends ConsumerStatefulWidget {
  const AcceptInviteScreen({super.key});

  @override
  ConsumerState<AcceptInviteScreen> createState() => _AcceptInviteScreenState();
}

class _AcceptInviteScreenState extends ConsumerState<AcceptInviteScreen> {
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _repeat = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [_code, _password, _repeat]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    final code = _code.text.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
    final problem = code.length != 12
        ? 'Den Code aus der Einladung eingeben (12 Zeichen)'
        : _password.text.length < 10
            ? 'Passwort: mindestens 10 Zeichen'
            : _password.text != _repeat.text
                ? 'Die Passwörter stimmen nicht überein'
                : null;
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).acceptInvite(code: _code.text.trim(), password: _password.text);
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Einladung einlösen')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          const Text('Gib den Code aus deiner Einladung ein und lege dein eigenes Passwort fest.'),
          const SizedBox(height: 16),
          TextField(key: const Key('accept-code'), controller: _code, textCapitalization: TextCapitalization.characters,
              autocorrect: false, decoration: const InputDecoration(labelText: 'Einladungscode', hintText: 'ABCD-EFGH-JKLM')),
          const SizedBox(height: 12),
          TextField(key: const Key('accept-password'), controller: _password, obscureText: true,
              decoration: const InputDecoration(labelText: 'Neues Passwort', helperText: 'mindestens 10 Zeichen')),
          const SizedBox(height: 12),
          TextField(key: const Key('accept-repeat'), controller: _repeat, obscureText: true,
              decoration: const InputDecoration(labelText: 'Passwort wiederholen'), onSubmitted: (_) => _submit()),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, key: const Key('accept-error'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 20),
          FilledButton(key: const Key('accept-submit'), onPressed: _busy ? null : _submit,
              child: _busy ? const HubLoader(size: 20) : const Text('Einlösen und anmelden')),
        ]),
      );
}
