import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../invite/invite_widgets.dart';
import '../today/today_widgets.dart' show PersonAvatar;
import '../../l10n/l10n.dart';

final adminUsersProvider = FutureProvider.autoDispose<List<AdminUser>>((ref) => ref.watch(apiClientProvider).adminUsers());
final adminInvitesProvider = FutureProvider.autoDispose<List<InviteInfo>>((ref) => ref.watch(apiClientProvider).invites());

/// Einladen und danach den Text zum Teilen zeigen. Gibt true zurück, wenn eingeladen wurde.
Future<bool> inviteFlow(BuildContext context, WidgetRef ref) async {
  final invite = await showDialog<InviteInfo>(context: context, builder: (_) => const InviteDialog());
  if (invite == null || !context.mounted) return false;
  ref.invalidate(adminUsersProvider);
  ref.invalidate(adminInvitesProvider);
  await showModalBottomSheet<void>(context: context, isScrollControlled: true, useSafeArea: true,
      builder: (_) => InviteResultSheet(invite: invite));
  return true;
}

/// Familie & Rollen: Rolle, aktiv/inaktiv, Verbindungen je Person (ohne Zugangsdaten).
class AdminUsersScreen extends ConsumerWidget {
  const AdminUsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final users = ref.watch(adminUsersProvider);
    final me = ref.watch(sessionProvider).user?.id;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.familyRoles), actions: [
        IconButton(
          key: const Key('admin-user-add'),
          tooltip: l10n.createWithoutInvite,
          icon: const Icon(Icons.person_add_alt),
          onPressed: () async {
            if (await showDialog<bool>(context: context, builder: (_) => const CreateUserDialog()) == true) {
              ref.invalidate(adminUsersProvider);
            }
          },
        ),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('admin-user-invite'),
        onPressed: () => inviteFlow(context, ref),
        icon: const Icon(Icons.mail_outline),
        label: Text(l10n.invitePerson),
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
              const _OpenInvites(),
              for (final u in list)
                _UserTile(key: ValueKey('admin-user-${u.id}'), user: u, isMe: u.id == me),
              Padding(
                padding: EdgeInsets.fromLTRB(16, 16, 16, 0),
                child: Text(l10n.familyRolesExplain),
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
    final last = user.lastLogin == null ? l10n.neverSignedIn : l10n.lastSignIn(localDate('d.M.yyyy').format(user.lastLogin!.toLocal()));
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
                Text(isMe ? l10n.nameYou(user.displayName) : user.displayName,
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                Text(l10n.userLine(user.username, last, user.devices), style: muted),
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

/// Person mit lokalem Konto anlegen (auch im Einrichtungs-Assistenten).
class CreateUserDialog extends ConsumerStatefulWidget {
  const CreateUserDialog({super.key});

  @override
  ConsumerState<CreateUserDialog> createState() => CreateUserDialogState();
}

class CreateUserDialogState extends ConsumerState<CreateUserDialog> {
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
      title: Text(l10n.createPerson),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(key: const Key('new-user-username'), controller: _username, autocorrect: false,
              decoration: InputDecoration(labelText: l10n.username, helperText: l10n.usernameHint),
              onChanged: (_) => setState(() {})),
          TextField(controller: _name, decoration: InputDecoration(labelText: l10n.name)),
          TextField(key: const Key('new-user-email'), controller: _email, keyboardType: TextInputType.emailAddress,
              decoration: InputDecoration(labelText: l10n.email), onChanged: (_) => setState(() {})),
          TextField(key: const Key('new-user-password'), controller: _password, obscureText: true,
              decoration: InputDecoration(labelText: l10n.initialPassword, helperText: l10n.min10Chars),
              onChanged: (_) => setState(() {})),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _role,
            decoration: InputDecoration(labelText: l10n.role),
            items: [for (final e in roleLabels.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) => setState(() => _role = v ?? 'partner'),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
        FilledButton(
          key: const Key('new-user-save'),
          onPressed: _busy || !_valid ? null : _save,
          child: Text(l10n.create),
        ),
      ],
    );
  }
}


/// Offene Einladungen: neuen Code erzeugen (alter wird ungültig) oder zurückziehen.
class _OpenInvites extends ConsumerWidget {
  const _OpenInvites();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final list = ref.watch(adminInvitesProvider).valueOrNull ?? const <InviteInfo>[];
    if (list.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
        child: Text(l10n.openInvites, style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary)),
      ),
      for (final i in list)
        ListTile(
          key: ValueKey('invite-${i.id}'),
          leading: Icon(i.expired ? Icons.timer_off_outlined : Icons.mail_outline),
          title: Text(i.displayName),
          subtitle: Text('${i.email} · ${roleLabels[i.role] ?? i.role} · '
              '${i.expired ? 'abgelaufen' : 'gültig bis ${localDate('d.M.').format(i.expiresAt!)}'}'),
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            IconButton(
              tooltip: l10n.newCode,
              icon: const Icon(Icons.refresh),
              onPressed: () async {
                try {
                  final fresh = await ref.read(apiClientProvider).renewInvite(i.id);
                  ref.invalidate(adminInvitesProvider);
                  if (context.mounted) {
                    await showModalBottomSheet<void>(context: context, isScrollControlled: true, useSafeArea: true,
                        builder: (_) => InviteResultSheet(invite: fresh));
                  }
                } catch (e) {
                  if (context.mounted) showError(context, e);
                }
              },
            ),
            IconButton(
              tooltip: l10n.withdrawInvite,
              icon: const Icon(Icons.close),
              onPressed: () async {
                if (await runAction(context, () => ref.read(apiClientProvider).revokeInvite(i.id))) {
                  ref.invalidate(adminInvitesProvider);
                  ref.invalidate(adminUsersProvider);
                }
              },
            ),
          ]),
        ),
      const Divider(),
    ]);
  }
}
