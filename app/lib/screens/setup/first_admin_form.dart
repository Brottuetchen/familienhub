import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';

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
    if (_code.text.trim().length < 8) return 'Einrichtungscode aus dem Server-Log eingeben';
    if (!RegExp(r'^[a-z0-9._-]{2,40}$').hasMatch(_username.text.trim().toLowerCase())) {
      return 'Benutzername: klein, ohne Leerzeichen (a–z, 0–9, . _ -)';
    }
    if (!_email.text.contains('@')) return 'E-Mail-Adresse eingeben';
    if (_password.text.length < 10) return 'Passwort: mindestens 10 Zeichen';
    if (_password.text != _repeat.text) return 'Die Passwörter stimmen nicht überein';
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
      Text('Willkommen! Dieser Hub ist neu.', style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
      const SizedBox(height: 8),
      const Text(
        'Lege das erste Konto an – es verwaltet den Hub. Den Einrichtungscode findest du im Server-Log, '
        'z. B. mit „docker compose logs familienhub“.',
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 20),
      TextField(
        key: const Key('setup-code'),
        controller: _code,
        textCapitalization: TextCapitalization.characters,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'Einrichtungscode', hintText: 'ABCD-EFGH'),
      ),
      const SizedBox(height: 12),
      TextField(key: const Key('setup-name'), controller: _name, decoration: const InputDecoration(labelText: 'Dein Name')),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-username'),
        controller: _username,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'Benutzername', helperText: 'klein, ohne Leerzeichen'),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-email'),
        controller: _email,
        keyboardType: TextInputType.emailAddress,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'E-Mail'),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-password'),
        controller: _password,
        obscureText: true,
        decoration: const InputDecoration(labelText: 'Passwort', helperText: 'mindestens 10 Zeichen'),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('setup-repeat'),
        controller: _repeat,
        obscureText: true,
        decoration: const InputDecoration(labelText: 'Passwort wiederholen'),
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
        child: _busy ? const HubLoader(size: 20) : const Text('Konto anlegen und einrichten'),
      ),
    ]);
  }
}
