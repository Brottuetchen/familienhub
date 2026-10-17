import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../today/today_widgets.dart' show PersonAvatar;

final adminUsersProvider = FutureProvider.autoDispose<List<AdminUser>>((ref) => ref.watch(apiClientProvider).adminUsers());

/// Familie & Rollen: Rolle, aktiv/inaktiv, Verbindungen je Person (ohne Zugangsdaten).
class AdminUsersScreen extends ConsumerWidget {
  const AdminUsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final users = ref.watch(adminUsersProvider);
    final me = ref.watch(sessionProvider).user?.id;
    return Scaffold(
      appBar: AppBar(title: const Text('Familie & Rollen')),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('admin-user-add'),
        onPressed: () async {
          if (await showDialog<bool>(context: context, builder: (_) => const _CreateUserDialog()) == true) {
            ref.invalidate(adminUsersProvider);
          }
        },
        icon: const Icon(Icons.person_add_alt),
        label: const Text('Person anlegen'),
      ),
      body: HubRefresh(
        onRefresh: () => ref.refresh(adminUsersProvider.future),
        child: users.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminUsersProvider)),
          data: (list) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              for (final u in list)
                _UserTile(key: ValueKey('admin-user-${u.id}'), user: u, isMe: u.id == me),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 16, 16, 0),
                child: Text('Anmeldung und Passwörter laufen über die Anmeldung (z. B. Authentik). '
                    'Hier legst du fest, was jemand im Hub darf.'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _UserTile extends ConsumerWidget {
  final AdminUser user;
  final bool isMe;
  const _UserTile({super.key, required this.user, required this.isMe});

  Future<void> _update(BuildContext context, WidgetRef ref, {String? role, bool? active}) async {
    if (await runAction(context, () => ref.read(apiClientProvider).updateAdminUser(user.id, role: role, active: active))) {
      ref.invalidate(adminUsersProvider);
      ref.invalidate(peopleProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final last = user.lastLogin == null ? 'noch nie angemeldet' : 'zuletzt ${DateFormat('d.M.yyyy', 'de_DE').format(user.lastLogin!.toLocal())}';
    return Opacity(
      opacity: user.active ? 1 : 0.55,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            PersonAvatar(name: user.displayName, id: user.id, size: 44, color: user.avatarColor, imageUrl: user.avatarUrl),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(isMe ? '${user.displayName} (du)' : user.displayName,
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                Text('${user.username} · $last · ${user.devices} Geräte', style: muted),
              ]),
            ),
            Switch(
              key: ValueKey('admin-user-active-${user.id}'),
              value: user.active,
              onChanged: isMe ? null : (v) => _update(context, ref, active: v),
            ),
          ]),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            key: ValueKey('admin-user-role-${user.id}'),
            showSelectedIcon: false,
            segments: [for (final e in roleLabels.entries) ButtonSegment(value: e.key, label: Text(e.value))],
            selected: {user.role},
            onSelectionChanged: isMe || !user.active ? null : (s) => _update(context, ref, role: s.first),
          ),
          if (user.links.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final e in user.links.entries)
                Chip(
                  visualDensity: VisualDensity.compact,
                  avatar: Icon(
                    e.value == true ? Icons.check_circle : e.value == false ? Icons.radio_button_unchecked : Icons.help_outline,
                    size: 16,
                    color: e.value == true ? Colors.green : theme.colorScheme.onSurfaceVariant,
                  ),
                  label: Text(linkLabels[e.key] ?? e.key),
                ),
            ]),
          ],
          const Divider(height: 20),
        ]),
      ),
    );
  }
}

class _CreateUserDialog extends ConsumerStatefulWidget {
  const _CreateUserDialog();

  @override
  ConsumerState<_CreateUserDialog> createState() => _CreateUserDialogState();
}

class _CreateUserDialogState extends ConsumerState<_CreateUserDialog> {
  final _username = TextEditingController();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String _role = 'partner';
  bool _busy = false;

  @override
  void dispose() {
    for (final c in [_username, _name, _email, _password]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _valid =>
      RegExp(r'^[a-z0-9._-]{2,40}$').hasMatch(_username.text.trim()) &&
      _email.text.contains('@') &&
      _password.text.length >= 10;

  Future<void> _save() async {
    setState(() => _busy = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).createAdminUser(
          username: _username.text.trim(),
          email: _email.text.trim(),
          password: _password.text,
          fullName: _name.text.trim(),
          role: _role,
        ));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Person anlegen'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(key: const Key('new-user-username'), controller: _username, autocorrect: false,
              decoration: const InputDecoration(labelText: 'Benutzername', helperText: 'klein, ohne Leerzeichen'),
              onChanged: (_) => setState(() {})),
          TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name')),
          TextField(key: const Key('new-user-email'), controller: _email, keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'E-Mail'), onChanged: (_) => setState(() {})),
          TextField(key: const Key('new-user-password'), controller: _password, obscureText: true,
              decoration: const InputDecoration(labelText: 'Start-Passwort', helperText: 'mindestens 10 Zeichen'),
              onChanged: (_) => setState(() {})),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _role,
            decoration: const InputDecoration(labelText: 'Rolle'),
            items: [for (final e in roleLabels.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) => setState(() => _role = v ?? 'partner'),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Abbrechen')),
        FilledButton(
          key: const Key('new-user-save'),
          onPressed: _busy || !_valid ? null : _save,
          child: const Text('Anlegen'),
        ),
      ],
    );
  }
}
