import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/providers.dart';
import '../../services/app_info.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

List<String> get feedbackAreas => [l10n.today, l10n.tabTasks, l10n.tabShopping, l10n.tabMeals, l10n.tabCalendar, l10n.house, l10n.reminders, l10n.books,
  l10n.moviesShows, l10n.documents, l10n.appearance, l10n.signIn, l10n.other];

/// Rückmeldung: an die Verwaltung der Familie (im Hub) oder an die Entwickler (GitHub-Issue, eigenes Konto).
class FeedbackScreen extends ConsumerStatefulWidget {
  /// Für Tests: statt Browser öffnen.
  final Future<bool> Function(Uri uri)? openUrl;
  const FeedbackScreen({super.key, this.openUrl});

  @override
  ConsumerState<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends ConsumerState<FeedbackScreen> {
  final _text = TextEditingController();
  String _area = l10n.other;
  bool _busy = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  bool get _valid => _text.text.trim().length >= 3;

  Future<void> _toFamily() async {
    setState(() => _busy = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).sendFeedback(text: _text.text.trim(), area: _area));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      showInfo(context, l10n.feedbackThanks);
      Navigator.pop(context);
    }
  }

  Future<void> _toGithub() async {
    final uri = githubIssueUri(text: _text.text, area: _area);
    final open = widget.openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication);
    if (!await open(uri) && mounted) showInfo(context, l10n.browserFailed);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.sendFeedback)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text(l10n.feedbackPrompt),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('feedback-area'),
          initialValue: _area,
          decoration: InputDecoration(labelText: l10n.area),
          items: [for (final a in feedbackAreas) DropdownMenuItem(value: a, child: Text(a))],
          onChanged: (v) => setState(() => _area = v ?? l10n.other),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('feedback-text'),
          controller: _text,
          minLines: 4,
          maxLines: 10,
          maxLength: 4000,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(labelText: l10n.yourFeedback, alignLabelWithHint: true),
          onChanged: (_) => setState(() {}),
        ),
        Text(l10n.feedbackIncludes(appVersion, appPlatform),
            style: theme.textTheme.bodySmall),
        const SizedBox(height: 16),
        FilledButton.icon(
          key: const Key('feedback-family'),
          onPressed: _busy || !_valid ? null : _toFamily,
          icon: const Icon(Icons.family_restroom),
          label: Text(l10n.toFamilyAdmins),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          key: const Key('feedback-github'),
          onPressed: !_valid ? null : _toGithub,
          icon: const Icon(Icons.bug_report_outlined),
          label: Text(l10n.toDevelopers),
        ),
        const SizedBox(height: 4),
        Text(l10n.githubIssueHint,
            style: theme.textTheme.bodySmall),
      ]),
    );
  }
}
