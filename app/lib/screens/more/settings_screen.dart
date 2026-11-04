import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../providers/providers.dart';
import '../../services/app_info.dart' show appVersion;
import '../../widgets/common.dart';
import 'api_tokens_screen.dart';
import 'appearance_screen.dart';
import 'caldav_account_screen.dart';
import 'connections_screen.dart';
import 'notification_settings_screen.dart';
import 'profile_screen.dart';
import 'task_lists_screen.dart';
import 'task_place_screen.dart';

/// Personal settings for everyone: profile, notifications, appearance, accounts and logout.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.logoutQuestion),
        content: ref.read(apiClientProvider).pending.isEmpty
            ? null
            : Text(l10n.logoutPendingWarning(ref.read(apiClientProvider).pending.length), key: const Key('logout-pending-warning')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.logout)),
        ],
      ),
    );
    if (ok == true) await ref.read(sessionProvider.notifier).logout();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final modules = ref.watch(appModulesProvider);
    final canAct = ref.watch(canActProvider); // own accounts and lists from the child role up
    final connections = ref.watch(personalPluginsProvider).valueOrNull ?? const [];
    final hasTaskPlace = ref.watch(taskPlaceProvider).valueOrNull != null; // hidden while the server does not answer
    void open(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.settings)),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          SectionHeader(l10n.settingsGroupMe),
          ListTile(
            key: const Key('settings-profile'),
            leading: const Icon(Icons.person_outline),
            title: Text(l10n.myProfile),
            subtitle: Text(l10n.moreProfileHint),
            onTap: () => open(const ProfileScreen()),
          ),
          SectionHeader(l10n.settingsGroupNotifications),
          ListTile(
            key: const Key('settings-notifications'),
            leading: const Icon(Icons.tune),
            title: Text(l10n.notificationsDevices),
            onTap: () => open(const NotificationSettingsScreen()),
          ),
          SectionHeader(l10n.settingsGroupAppearance),
          ListTile(
            key: const Key('settings-appearance'),
            leading: const Icon(Icons.palette_outlined),
            title: Text(l10n.appearance),
            subtitle: Text(l10n.appearanceHint),
            onTap: () => open(const AppearanceScreen()),
          ),
          SectionHeader(l10n.settingsGroupAccounts),
          if (canAct && (modules.has('tasks') || modules.has('calendar')))
            ListTile(
              key: const Key('settings-caldav'),
              leading: const Icon(Icons.cloud_outlined),
              title: Text(l10n.nextcloudAccount),
              subtitle: Text(l10n.nextcloudAccountHint),
              onTap: () => open(const CalDavAccountScreen()),
            ),
          if (canAct && modules.has('tasks'))
            ListTile(
              key: const Key('settings-task-lists'),
              leading: const Icon(Icons.list_alt),
              title: Text(l10n.taskLists),
              subtitle: Text(l10n.taskListsHint),
              onTap: () => open(const TaskListsScreen()),
            ),
          if (hasTaskPlace)
            ListTile(
              key: const Key('settings-task-place'),
              leading: const Icon(Icons.move_to_inbox_outlined),
              title: Text(l10n.taskPlaceTitle),
              onTap: () => open(const TaskPlaceScreen()),
            ),
          if (canAct && connections.isNotEmpty)
            ListTile(
              key: const Key('more-connections'),
              leading: const Icon(Icons.link),
              title: Text(l10n.myConnections),
              subtitle: Text(l10n.myConnectionsHint),
              onTap: () => open(const ConnectionsScreen()),
            ),
          ListTile(
            key: const Key('settings-api-tokens'),
            leading: const Icon(Icons.key),
            title: Text(l10n.assistantAccess),
            subtitle: Text(l10n.assistantAccessHint),
            onTap: () => open(const ApiTokensScreen()),
          ),
          const Divider(height: 32),
          ListTile(
            key: const Key('settings-logout'),
            leading: Icon(Icons.logout, color: theme.colorScheme.error),
            title: Text(l10n.logout),
            onTap: () => _logout(context, ref),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(
              l10n.appVersionLine(appVersion),
              key: const Key('settings-version'),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}
