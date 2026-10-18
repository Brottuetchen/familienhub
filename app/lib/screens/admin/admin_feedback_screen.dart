import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/providers.dart';
import '../../services/app_info.dart';
import '../../widgets/common.dart';

final adminFeedbackProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) => ref.watch(apiClientProvider).adminFeedback());

/// Rückmeldungen der Familie; einzelne lassen sich als GitHub-Issue an die Entwickler weitergeben.
class AdminFeedbackScreen extends ConsumerWidget {
  final Future<bool> Function(Uri uri)? openUrl;
  const AdminFeedbackScreen({super.key, this.openUrl});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final list = ref.watch(adminFeedbackProvider);
    final open = openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication);
    return Scaffold(
      appBar: AppBar(title: const Text('Feedback')),
      body: HubRefresh(
        onRefresh: () => ref.refresh(adminFeedbackProvider.future),
        child: list.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminFeedbackProvider)),
          data: (items) => items.isEmpty
              ? ListView(children: const [EmptyHint(icon: Icons.chat_bubble_outline, text: 'Noch kein Feedback')])
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final f = items[i];
                    final done = f['done'] == true;
                    final when = DateTime.tryParse(f['created_at'] as String? ?? '')?.toLocal();
                    return ListTile(
                      key: ValueKey('feedback-${f['id']}'),
                      leading: Icon(done ? Icons.check_circle : Icons.chat_bubble_outline,
                          color: done ? Colors.green : null),
                      title: Text(f['text'] as String? ?? '', maxLines: 4, overflow: TextOverflow.ellipsis),
                      subtitle: Text([
                        f['from'], f['area'], f['platform'], f['app_version'],
                        if (when != null) DateFormat('d.M. HH:mm', 'de_DE').format(when),
                      ].whereType<String>().where((s) => s.isNotEmpty).join(' · ')),
                      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                        IconButton(
                          tooltip: 'Auf GitHub melden',
                          icon: const Icon(Icons.bug_report_outlined),
                          onPressed: () => open(githubIssueUri(text: f['text'] as String? ?? '', area: f['area'] as String?)),
                        ),
                        if (!done)
                          IconButton(
                            tooltip: 'Erledigt',
                            icon: const Icon(Icons.done),
                            onPressed: () async {
                              if (await runAction(context, () => ref.read(apiClientProvider).markFeedbackDone(f['id'] as int))) {
                                ref.invalidate(adminFeedbackProvider);
                              }
                            },
                          ),
                      ]),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
