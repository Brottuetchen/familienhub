import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/providers.dart';
import '../../widgets/common.dart' show SectionHeader;
import '../today/today_widgets.dart' show PersonAvatar;
import '../admin/admin_screen.dart';
import 'books_screen.dart';
import 'plugin_pages.dart';
import '../../models/plugin_card.dart' show pluginCardIcon;
import 'documents_screen.dart';
import 'feedback_screen.dart';
import 'media_screen.dart';
import 'notifications_screen.dart';
import 'profile_screen.dart';
import 'birthdays_screen.dart';
import 'reminders_screen.dart';
import 'settings_screen.dart';
import '../timetable/timetable_screen.dart';
import '../stars/stars_screen.dart';
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
    final pluginPages = ref.watch(pluginPagesProvider).valueOrNull ?? const [];
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
          if (pluginPages.isNotEmpty) ...[
            SectionHeader(l10n.pluginPagesHeading),
            for (final p in pluginPages)
              ListTile(
                key: Key('more-page-${p.plugin}-${p.id}'),
                leading: Icon(pluginCardIcon(p.icon)),
                title: Text(p.title),
                subtitle: Text(p.pluginName),
                onTap: () => openPluginPage(context, ref, p.plugin, p.id),
              ),
          ],
          const Divider(),
          ListTile(
            key: const Key('more-settings'),
            leading: const Icon(Icons.settings_outlined),
            title: Text(l10n.settings),
            subtitle: Text(l10n.settingsHint),
            onTap: () => open(const SettingsScreen()),
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
        ],
      ),
    );
  }
}
