import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Text zum Teilen (Messenger, Mail): App, Server-Adresse, Anmeldung bzw. Code.
String inviteText({required InviteInfo invite, required String server}) {
  final until = invite.expiresAt == null ? '' : l10n.validUntil(localDate('d.M.').format(invite.expiresAt!));
  return [
    l10n.inviteHello(invite.displayName),
    '',
    l10n.inviteStep1(server),
    l10n.inviteStep2(server),
    if (invite.oidc) l10n.inviteStep3Oidc(invite.email),
    if (invite.oidc && invite.code != null) l10n.inviteStep3OidcCode(invite.code!, until),
    if (!invite.oidc && invite.code != null) l10n.inviteStep3Code(invite.code!, until),
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
        title: Text(l10n.invitePerson),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(key: const Key('invite-name'), controller: _name,
                decoration: InputDecoration(labelText: l10n.name), onChanged: (_) => setState(() {})),
            TextField(key: const Key('invite-email'), controller: _email, keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(labelText: l10n.email, helperText: l10n.inviteEmailHint),
                onChanged: (_) => setState(() {})),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              key: const Key('invite-role'),
              initialValue: _role,
              decoration: InputDecoration(labelText: l10n.role),
              items: [for (final e in roleLabels.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
              onChanged: (v) => setState(() => _role = v ?? 'partner'),
            ),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
          FilledButton(key: const Key('invite-send'), onPressed: _busy || !_valid ? null : _send, child: Text(l10n.invite)),
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
          Text(l10n.inviteFor(invite.displayName), style: theme.textTheme.titleLarge),
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
              if (context.mounted) showInfo(context, l10n.inviteCopied);
            },
            icon: const Icon(Icons.copy),
            label: Text(l10n.copyText),
          ),
          const SizedBox(height: 8),
          Text(l10n.inviteCodeOnce),
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
        ? l10n.enterInviteCode
        : _password.text.length < 10
            ? l10n.passwordRule
            : _password.text != _repeat.text
                ? l10n.passwordsMismatch
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
        appBar: AppBar(title: Text(l10n.redeemInvite)),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          Text(l10n.redeemExplain),
          const SizedBox(height: 16),
          TextField(key: const Key('accept-code'), controller: _code, textCapitalization: TextCapitalization.characters,
              autocorrect: false, decoration: InputDecoration(labelText: l10n.inviteCode, hintText: 'ABCD-EFGH-JKLM')),
          const SizedBox(height: 12),
          TextField(key: const Key('accept-password'), controller: _password, obscureText: true,
              decoration: InputDecoration(labelText: l10n.newPassword, helperText: l10n.min10Chars)),
          const SizedBox(height: 12),
          TextField(key: const Key('accept-repeat'), controller: _repeat, obscureText: true,
              decoration: InputDecoration(labelText: l10n.repeatPassword), onSubmitted: (_) => _submit()),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, key: const Key('accept-error'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 20),
          FilledButton(key: const Key('accept-submit'), onPressed: _busy ? null : _submit,
              child: _busy ? const HubLoader(size: 20) : Text(l10n.redeemAndSignIn)),
        ]),
      );
}
