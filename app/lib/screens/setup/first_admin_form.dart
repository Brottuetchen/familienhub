import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Neuer Hub: erstes Admin-Konto anlegen. Der Einrichtungscode steht im Server-Log
/// (`docker compose logs familienhub`), damit nicht jeder, der den Server zuerst erreicht, Admin wird.
class FirstAdminForm extends ConsumerStatefulWidget {
  const FirstAdminForm({super.key});

  @override
  ConsumerState<FirstAdminForm> createState() => _FirstAdminFormState();
}

class _FirstAdminFormState extends ConsumerState<FirstAdminForm> {
  final _code = TextEditingController();
  final _name = TextEditingController();
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _repeat = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [_code, _name, _username, _email, _password, _repeat]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _problem() {
    if (_code.text.trim().length < 8) return l10n.enterSetupCode;
    if (!RegExp(r'^[a-z0-9._-]{2,40}$').hasMatch(_username.text.trim().toLowerCase())) {
      return l10n.usernameRule;
    }
    if (!_email.text.contains('@')) return l10n.enterEmail;
    if (_password.text.length < 10) return l10n.passwordRule;
    if (_password.text != _repeat.text) return l10n.passwordsMismatch;
    return null;
  }

  Future<void> _submit() async {
    final problem = _problem();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).createFirstAdmin(
            code: _code.text.trim(),
            username: _username.text.trim().toLowerCase(),
            email: _email.text.trim(),
            password: _password.text,
            displayName: _name.text.trim(),
          );
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(l10n.welcomeNewHub, style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
      const SizedBox(height: 8),
      Text(
        l10n.firstAdminExplain,
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 20),
      TextField(
        key: const Key('setup-code'),
        controller: _code,
        textCapitalization: TextCapitalization.characters,
        autocorrect: false,
        decoration: InputDecoration(labelText: l10n.setupCode, hintText: 'ABCD-EFGH'),
      ),
      const SizedBox(height: 12),
      TextField(key: const Key('setup-name'), controller: _name, decoration: InputDecoration(labelText: l10n.yourName)),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-username'),
        controller: _username,
        autocorrect: false,
        decoration: InputDecoration(labelText: l10n.username, helperText: l10n.usernameHint),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-email'),
        controller: _email,
        keyboardType: TextInputType.emailAddress,
        autocorrect: false,
        decoration: InputDecoration(labelText: l10n.email),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-password'),
        controller: _password,
        obscureText: true,
        decoration: InputDecoration(labelText: l10n.password, helperText: l10n.min10Chars),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-repeat'),
        controller: _repeat,
        obscureText: true,
        decoration: InputDecoration(labelText: l10n.repeatPassword),
        onSubmitted: (_) => _submit(),
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        Text(_error!, key: const Key('setup-error'), style: TextStyle(color: theme.colorScheme.error)),
      ],
      const SizedBox(height: 20),
      FilledButton(
        key: const Key('setup-submit'),
        onPressed: _busy ? null : _submit,
        child: _busy ? const HubLoader(size: 20) : Text(l10n.createAccountSetUp),
      ),
    ]);
  }
}
