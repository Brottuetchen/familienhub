import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../services/api_exceptions.dart';
import '../../widgets/common.dart';
import '../invite/invite_widgets.dart';
import '../setup/first_admin_form.dart';

class LoginScreen extends ConsumerStatefulWidget {
  /// Hinweis von außen, z. B. „Sitzung abgelaufen“.
  final String? message;
  const LoginScreen({super.key, this.message});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _user = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hidePassword = true;
  String? _error;
  HealthInfo? _health;
  String? _server;
  bool _needsSetup = false; // neuer Hub ohne Admin → Einrichtung statt Anmeldung

  @override
  void initState() {
    super.initState();
    _loadServer();
  }

  Future<void> _loadServer() async {
    final api = ref.read(apiClientProvider);
    final url = await api.store.baseUrl();
    if (mounted) setState(() => _server = url);
    try {
      final health = await api.health();
      if (mounted) setState(() => _health = health);
    } catch (_) {
      // Ohne Health bleibt nur die Passwort-Anmeldung sichtbar.
    }
    try {
      final setup = await api.setupStatus();
      if (mounted) setState(() => _needsSetup = setup.needsSetup);
    } catch (_) {
      // Ältere Server kennen /api/setup nicht: normale Anmeldung.
    }
  }

  @override
  void dispose() {
    _user.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (_user.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Benutzername und Passwort eingeben');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).login(_user.text.trim(), _password.text);
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 401
          ? 'Benutzername oder Passwort falsch'
          : e.statusCode == 429
              ? 'Zu viele Versuche, bitte kurz warten'
              : e.message);
    } catch (e) {
      setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Authentik im externen Browser; zurück kommt `familienhub://auth?code=…` (siehe AuthGate).
  Future<void> _loginOidc() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Web: im selben Tab, Rücksprung auf die Seite (?oidc_code=…). App: externer Browser.
      final url = await ref.read(apiClientProvider).oidcStartUrl(client: kIsWeb ? 'pwa' : 'app');
      final ok = kIsWeb
          ? await launchUrl(Uri.parse(url), webOnlyWindowName: '_self')
          : await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      if (!ok) setState(() => _error = 'Browser konnte nicht geöffnet werden');
    } catch (e) {
      setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _loginLabel() => _busy
      ? const HubLoader(size: 20)
      : const Text('Anmelden');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final oidc = _health?.oidc == true;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              padding: const EdgeInsets.all(24),
              shrinkWrap: true,
              children: [
                Icon(Icons.family_restroom, size: 56, color: theme.colorScheme.primary),
                const SizedBox(height: 12),
                Text(_needsSetup ? 'Einrichten' : 'Anmelden', textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
                if (_server != null)
                  Text(_server!, textAlign: TextAlign.center, style: theme.textTheme.bodySmall),
                if (widget.message != null) ...[
                  const SizedBox(height: 12),
                  Text(widget.message!, textAlign: TextAlign.center),
                ],
                const SizedBox(height: 28),
                if (_needsSetup) const FirstAdminForm(),
                if (!_needsSetup && oidc) ...[
                  FilledButton.icon(
                    onPressed: _busy ? null : _loginOidc,
                    icon: const Icon(Icons.verified_user),
                    label: const Text('Mit Authentik anmelden'),
                  ),
                  const SizedBox(height: 20),
                  const Row(children: [
                    Expanded(child: Divider()),
                    Padding(padding: EdgeInsets.symmetric(horizontal: 12), child: Text('oder')),
                    Expanded(child: Divider()),
                  ]),
                  const SizedBox(height: 20),
                ],
                if (!_needsSetup) ...[
                TextField(
                  controller: _user,
                  autocorrect: false,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.username],
                  decoration: const InputDecoration(labelText: 'Benutzername'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: _hidePassword,
                  autofillHints: const [AutofillHints.password],
                  onSubmitted: (_) => _login(),
                  decoration: InputDecoration(
                    labelText: 'Passwort',
                    suffixIcon: IconButton(
                      tooltip: _hidePassword ? 'Passwort zeigen' : 'Passwort verbergen',
                      icon: Icon(_hidePassword ? Icons.visibility : Icons.visibility_off),
                      onPressed: () => setState(() => _hidePassword = !_hidePassword),
                    ),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                ],
                const SizedBox(height: 20),
                if (oidc)
                  OutlinedButton(onPressed: _busy ? null : _login, child: _loginLabel())
                else
                  FilledButton(onPressed: _busy ? null : _login, child: _loginLabel()),
                const SizedBox(height: 4),
                TextButton(
                  key: const Key('login-accept-invite'),
                  onPressed: _busy ? null : () => Navigator.of(context)
                      .push(MaterialPageRoute<void>(builder: (_) => const AcceptInviteScreen())),
                  child: const Text('Einladung einlösen'),
                ),
                ],
                const SizedBox(height: 8),
                if (!kIsWeb)
                  TextButton(
                    onPressed: _busy ? null : () => ref.read(sessionProvider.notifier).changeServer(),
                    child: const Text('Anderen Server wählen'),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
