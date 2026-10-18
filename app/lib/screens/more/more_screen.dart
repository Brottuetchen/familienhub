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
import 'reminders_screen.dart';
import 'task_lists_screen.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final modules = ref.watch(appModulesProvider);
    final unread = ref.watch(todayProvider).valueOrNull?.data.notificationsUnread ?? 0;
    final isAdmin = session.user?.isAdmin ?? false;
    void open(Widget page) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));

    return Scaffold(
      appBar: AppBar(title: const Text('Mehr')),
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
              subtitle: const Text('Profil, Bild und Farbe'),
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
            title: const Text('Mitteilungen'),
            subtitle: Text(unread > 0 ? '$unread neu' : 'Verlauf aller Mitteilungen'),
            onTap: () => open(const NotificationsScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.notifications_active_outlined),
            title: const Text('Erinnerungen'),
            onTap: () => open(const RemindersScreen()),
          ),
          if (modules.has('documents'))
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: const Text('Dokumente'),
              subtitle: const Text('Paperless: suchen, Fristen'),
              onTap: () => open(const DocumentsScreen()),
            ),
          if (modules.has('media_requests'))
            ListTile(
              leading: const Icon(Icons.movie_outlined),
              title: const Text('Filme & Serien'),
              subtitle: const Text('Wünschen über Seerr'),
              onTap: () => open(const MediaScreen()),
            ),
          if (modules.has('books'))
            ListTile(
              leading: const Icon(Icons.auto_stories_outlined),
              title: const Text('Bücher & Hörbücher'),
              subtitle: const Text('Wünschen, auf Deutsch'),
              onTap: () => open(const BooksScreen()),
            ),
          const _Header('Einstellungen'),
          if (modules.has('tasks') || modules.has('calendar'))
            ListTile(
              leading: const Icon(Icons.cloud_outlined),
              title: const Text('Nextcloud-Konto'),
              subtitle: const Text('Für Aufgaben und eigene Termine'),
              onTap: () => open(const CalDavAccountScreen()),
            ),
          if (modules.has('tasks'))
            ListTile(
              leading: const Icon(Icons.list_alt),
              title: const Text('Aufgabenlisten'),
              subtitle: const Text('Welche Liste ist privat, welche für die Familie'),
              onTap: () => open(const TaskListsScreen()),
            ),
          ListTile(
            leading: const Icon(Icons.key),
            title: const Text('Zugänge für Assistenten'),
            subtitle: const Text('z. B. für einen Sprachassistenten'),
            onTap: () => open(const ApiTokensScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.tune),
            title: const Text('Benachrichtigungen & Geräte'),
            onTap: () => open(const NotificationSettingsScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.palette_outlined),
            title: const Text('Darstellung'),
            subtitle: const Text('Farbschema für dieses Gerät'),
            onTap: () => open(const AppearanceScreen()),
          ),
          if (isAdmin)
            ListTile(
              key: const Key('more-admin'),
              leading: const Icon(Icons.admin_panel_settings_outlined),
              title: const Text('Verwaltung'),
              subtitle: const Text('Systemzustand, Familie, Haus, Plugins, Protokoll'),
              onTap: () => open(const AdminScreen()),
            ),
          ListTile(
            key: const Key('more-feedback'),
            leading: const Icon(Icons.chat_bubble_outline),
            title: const Text('Feedback senden'),
            subtitle: const Text('Fehler, Wünsche – an die Familie oder die Entwickler'),
            onTap: () => open(const FeedbackScreen()),
          ),
          FutureBuilder<String?>(
            future: ref.read(apiClientProvider).store.baseUrl(),
            builder: (context, snap) => ListTile(
              leading: const Icon(Icons.dns_outlined),
              title: const Text('Server'),
              subtitle: Text(snap.data ?? ''),
            ),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: Theme.of(context).colorScheme.error),
            title: const Text('Abmelden'),
            onTap: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('Abmelden?'),
                  content: ref.read(apiClientProvider).pending.isEmpty
                      ? null
                      : Text('${ref.read(apiClientProvider).pending.length} Änderungen ohne Netz sind noch nicht gesendet '
                          'und gehen beim Abmelden verloren.', key: const Key('logout-pending-warning')),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
                    FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Abmelden')),
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
