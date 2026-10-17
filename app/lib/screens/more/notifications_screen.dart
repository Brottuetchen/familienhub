import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final inboxProvider = FutureProvider.autoDispose<NotificationInbox>(
    (ref) => ref.watch(apiClientProvider).notifications());

IconData categoryIcon(String c) => switch (c) {
      'task_assigned' || 'task_due' => Icons.check_circle_outline,
      'reminder' => Icons.alarm,
      'shopping' => Icons.shopping_cart_outlined,
      'house' => Icons.home_outlined,
      'media' => Icons.auto_stories_outlined,
      'documents' => Icons.description_outlined,
      _ => Icons.notifications_none,
    };

/// Verlauf aller Mitteilungen – auch der, die wegen Ruhezeit nicht als Push kamen.
class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  bool _marked = false;

  Future<void> _markAllRead() async {
    if (_marked) return;
    _marked = true;
    try {
      await ref.read(apiClientProvider).markNotificationsRead();
    } catch (_) {
      _marked = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(inboxProvider);
    final fmt = DateFormat('EEE d.M., HH:mm', 'de_DE');
    // Beim Ansehen als gelesen markieren; die Markierung „neu“ bleibt bis zum nächsten Öffnen sichtbar.
    ref.listen(inboxProvider, (_, next) {
      if (next.valueOrNull?.unread case final n? when n > 0) _markAllRead();
    });
    return Scaffold(
      appBar: AppBar(title: const Text('Mitteilungen')),
      body: HubRefresh(
        onRefresh: () => ref.refresh(inboxProvider.future),
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(inboxProvider)),
          data: (inbox) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (inbox.items.isEmpty) const EmptyHint(icon: Icons.notifications_none, text: 'Noch keine Mitteilungen'),
              for (final n in inbox.items)
                ListTile(
                  key: ValueKey('notification-${n.id}'),
                  leading: Badge(isLabelVisible: !n.read, smallSize: 8, child: Icon(categoryIcon(n.category))),
                  title: Text(n.title, style: n.read ? null : const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text([
                    if (n.body.isNotEmpty) n.body,
                    [
                      if (n.createdAt != null) fmt.format(n.createdAt!),
                      if (n.source != 'hub') n.source,
                      if (!n.pushed) 'ohne Push',
                    ].join(' · '),
                  ].join('\n')),
                  isThreeLine: n.body.isNotEmpty,
                  onTap: n.route == null
                      ? null
                      : () {
                          Navigator.of(context).popUntil((r) => r.isFirst);
                          openRoute(ref, n.route!);
                        },
                ),
            ],
          ),
        ),
      ),
    );
  }
}
