import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../today/today_widgets.dart' show PersonAvatar;
import 'api_tokens_screen.dart';
import '../admin/admin_screen.dart';
import 'books_screen.dart';
import 'documents_screen.dart';
import 'feedback_screen.dart';
import 'media_screen.dart';
import 'notifications_screen.dart';
import 'appearance_screen.dart';
import 'profile_screen.dart';
import 'caldav_account_screen.dart';
import 'notification_settings_screen.dart';
import 'birthdays_screen.dart';
import 'reminders_screen.dart';
import '../timetable/timetable_screen.dart';
import '../stars/stars_screen.dart';
import 'task_lists_screen.dart';
import '../../l10n/l10n.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final modules = ref.watch(appModulesProvider);
    final unread = ref.watch(todayProvider).valueOrNull?.data.notificationsUnread ?? 0;
    final isAdmin = session.user?.isAdmin ?? false;
    final canAct = ref.watch(canActProvider); // eigene Konten und Listen ab Kind
    void open(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));

    return Scaffold(
      appBar: AppBar(title: Text(l10n.tabMore)),
      body: ListView(
        children: [
          if (session.user != null)
            ListTile(
              key: const Key('more-profile'),
              leading: PersonAvatar(
                name: session.user!.displayName,
                id: session.user!.id,
                size: 44,
                color: session.user!.avatarColor,
                imageUrl: session.user!.avatarUrl,
              ),
              title: Text(session.user!.displayName),
              subtitle: Text(l10n.moreProfileHint),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => open(const ProfileScreen()),
            ),
          const Divider(),
          ListTile(
            leading: Badge(
              isLabelVisible: unread > 0,
              label: Text('$unread'),
              child: const Icon(Icons.inbox_outlined),
            ),
            title: Text(l10n.notifications),
            subtitle: Text(unread > 0 ? l10n.unreadCount(unread) : l10n.notificationsHistory),
            onTap: () => open(const NotificationsScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.notifications_active_outlined),
            title: Text(l10n.reminders),
            onTap: () => open(const RemindersScreen()),
          ),
          if (canAct)
            ListTile(
              leading: const Icon(Icons.cake_outlined),
              title: Text(l10n.birthdays),
              subtitle: Text(l10n.birthdaysHint),
              onTap: () => open(const BirthdaysScreen()),
            ),
          if (canAct)
            ListTile(
              key: const Key('more-timetable'),
              leading: const Icon(Icons.calendar_view_week_outlined),
              title: Text(l10n.timetable),
              subtitle: Text(l10n.timetableHint),
              onTap: () => open(const TimetableScreen()),
            ),
          if (canAct)
            ListTile(
              key: const Key('more-stars'),
              leading: const Icon(Icons.star_outline_rounded),
              title: Text(l10n.starsTitle),
              subtitle: Text(l10n.starsHint),
              onTap: () => open(const StarsScreen()),
            ),
          if (modules.has('documents'))
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: Text(l10n.documents),
              subtitle: Text(l10n.documentsHint),
              onTap: () => open(const DocumentsScreen()),
            ),
          if (modules.has('media_requests'))
            ListTile(
              leading: const Icon(Icons.movie_outlined),
              title: Text(l10n.moviesShows),
              subtitle: Text(l10n.moviesShowsHint),
              onTap: () => open(const MediaScreen()),
            ),
          if (modules.has('books'))
            ListTile(
              leading: const Icon(Icons.auto_stories_outlined),
              title: Text(l10n.booksAudiobooks),
              subtitle: Text(l10n.booksHint),
              onTap: () => open(const BooksScreen()),
            ),
          _Header(l10n.settings),
          if (canAct && (modules.has('tasks') || modules.has('calendar')))
            ListTile(
              leading: const Icon(Icons.cloud_outlined),
              title: Text(l10n.nextcloudAccount),
              subtitle: Text(l10n.nextcloudAccountHint),
              onTap: () => open(const CalDavAccountScreen()),
            ),
          if (canAct && modules.has('tasks'))
            ListTile(
              leading: const Icon(Icons.list_alt),
              title: Text(l10n.taskLists),
              subtitle: Text(l10n.taskListsHint),
              onTap: () => open(const TaskListsScreen()),
            ),
          ListTile(
            leading: const Icon(Icons.key),
            title: Text(l10n.assistantAccess),
            subtitle: Text(l10n.assistantAccessHint),
            onTap: () => open(const ApiTokensScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.tune),
            title: Text(l10n.notificationsDevices),
            onTap: () => open(const NotificationSettingsScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.palette_outlined),
            title: Text(l10n.appearance),
            subtitle: Text(l10n.appearanceHint),
            onTap: () => open(const AppearanceScreen()),
          ),
          if (isAdmin)
            ListTile(
              key: const Key('more-admin'),
              leading: const Icon(Icons.admin_panel_settings_outlined),
              title: Text(l10n.administration),
              subtitle: Text(l10n.administrationHint),
              onTap: () => open(const AdminScreen()),
            ),
          ListTile(
            key: const Key('more-feedback'),
            leading: const Icon(Icons.chat_bubble_outline),
            title: Text(l10n.sendFeedback),
            subtitle: Text(l10n.sendFeedbackHint),
            onTap: () => open(const FeedbackScreen()),
          ),
          FutureBuilder<String?>(
            future: ref.read(apiClientProvider).store.baseUrl(),
            builder: (context, snap) => ListTile(
              leading: const Icon(Icons.dns_outlined),
              title: Text(l10n.server),
              subtitle: Text(snap.data ?? ''),
            ),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: Theme.of(context).colorScheme.error),
            title: Text(l10n.logout),
            onTap: () async {
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
            },
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final String text;
  const _Header(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Text(text,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );
}
