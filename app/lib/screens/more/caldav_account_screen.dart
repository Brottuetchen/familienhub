import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// Eigenes Nextcloud-Konto (CalDAV) für Aufgaben und Termine.
class CalDavAccountScreen extends ConsumerStatefulWidget {
  const CalDavAccountScreen({super.key});

  @override
  ConsumerState<CalDavAccountScreen> createState() => _CalDavAccountScreenState();
}

class _CalDavAccountScreenState extends ConsumerState<CalDavAccountScreen> {
  final _url = TextEditingController();
  final _user = TextEditingController();
  final _password = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  bool _hasAccount = false;

  @override
  void initState() {
    super.initState();
    ref.read(apiClientProvider).caldavAccount().then((acc) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _hasAccount = acc != null;
        if (acc != null) {
          _url.text = acc.url;
          _user.text = acc.username;
        }
      });
    }).catchError((Object e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showError(context, e);
    });
  }

  @override
  void dispose() {
    _url.dispose();
    _user.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_url.text.trim().isEmpty || _user.text.trim().isEmpty || _password.text.isEmpty) {
      showInfo(context, 'Bitte Adresse, Benutzer und App-Passwort eintragen');
      return;
    }
    setState(() => _saving = true);
    final ok = await runAction(
      context,
      () => ref.read(apiClientProvider).saveCaldavAccount(_url.text.trim(), _user.text.trim(), _password.text),
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      showInfo(context, 'Gespeichert');
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nextcloud-Konto')),
      body: _loading
          ? const Center(child: HubLoader())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const Text(
                  'Aufgaben und eigene Termine laufen über dein Nextcloud-Konto. '
                  'So bleiben sie mit den Erinnerungen auf dem iPhone abgeglichen. '
                  'Lege in Nextcloud unter Einstellungen → Sicherheit ein App-Passwort an und trage es hier ein.',
                ),
                const SizedBox(height: 20),
                TextField(
                  controller: _url,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'CalDAV-Adresse',
                    hintText: 'https://cloud.example.org/remote.php/dav',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _user,
                  autocorrect: false,
                  decoration: const InputDecoration(labelText: 'Benutzername'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: true,
                  decoration: InputDecoration(
                    labelText: 'App-Passwort',
                    helperText: _hasAccount ? 'Gespeichert. Zum Ändern neu eingeben.' : null,
                  ),
                ),
                const SizedBox(height: 24),
                FilledButton(onPressed: _saving ? null : _save, child: const Text('Speichern')),
              ],
            ),
    );
  }
}
