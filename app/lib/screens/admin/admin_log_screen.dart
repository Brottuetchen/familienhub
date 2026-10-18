import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

final adminLogProvider = FutureProvider.autoDispose<List<LogEntry>>((ref) => ref.watch(apiClientProvider).adminLog());

/// Letzte Warnungen und Fehler seit dem Serverstart (geschwärzt).
class AdminLogScreen extends ConsumerWidget {
  const AdminLogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final log = ref.watch(adminLogProvider);
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.log)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(adminLogProvider.future),
        child: log.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminLogProvider)),
          data: (items) => items.isEmpty
              ? ListView(children: [EmptyHint(icon: Icons.check_circle_outline, text: l10n.noWarnings)])
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final e = items[i];
                    final error = e.level == 'ERROR' || e.level == 'CRITICAL';
                    return ListTile(
                      leading: Icon(error ? Icons.error_outline : Icons.warning_amber_rounded,
                          color: error ? theme.colorScheme.error : Colors.amber),
                      title: Text(e.message, maxLines: 4, overflow: TextOverflow.ellipsis),
                      subtitle: Text([
                        if (e.time != null) localDate('d.M. HH:mm:ss').format(e.time!),
                        e.source,
                      ].join(' · ')),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
