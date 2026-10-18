import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../../services/session_store.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Erster Start: Adresse des eigenen Familienhub-Servers eintragen.
class ServerSetupScreen extends ConsumerStatefulWidget {
  const ServerSetupScreen({super.key});

  @override
  ConsumerState<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends ConsumerState<ServerSetupScreen> {
  final _url = TextEditingController();
  bool _checking = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    ref.read(apiClientProvider).store.baseUrl().then((u) {
      if (u != null && mounted) _url.text = u;
    });
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    final url = normalizeBaseUrl(_url.text);
    if (url.isEmpty) {
      setState(() => _error = l10n.enterServerAddress);
      return;
    }
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final health = await ref.read(apiClientProvider).health(baseUrl: url);
      if (!health.online) throw Exception(l10n.serverNotRunning);
      await ref.read(sessionProvider.notifier).setServer(url);
    } catch (e) {
      setState(() => _error = l10n.noHubAt(url, errorText(e)));
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
                Text('Familienhub', textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
                const SizedBox(height: 4),
                Text(l10n.whichServer, textAlign: TextAlign.center),
                const SizedBox(height: 32),
                TextField(
                  controller: _url,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: InputDecoration(
                    labelText: l10n.serverAddress,
                    hintText: 'https://hub.example.org',
                    errorText: _error,
                    errorMaxLines: 3,
                  ),
                  onSubmitted: (_) => _check(),
                ),
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: _checking ? null : _check,
                  child: _checking
                      ? const HubLoader(size: 20)
                      : Text(l10n.connect),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
